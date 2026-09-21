"""PA1-CONV-01 / #393: the Drive `.read()` gap carried from REUSE-R1c / #442.

#393 resolved that gap by declaring the orchestrator's Drive read seam
unsatisfiable rather than adapting the shipped Picker connector into it.  These
cases pin that decision from both sides: the shipped connector is genuinely
refused at the seam instead of crashing on it, and the Picker selection gate
that made adapting unsafe is shown to be the thing doing the refusing.

The point of pinning a decision is that a later change cannot quietly reverse
it.  Wiring `drive=` into `AgentService`, or relaxing the per-call-site shape
check, fails cases here rather than silently reopening the gap.
"""
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent.capabilities import CapabilityRegistry
from personal_agent.drive_web_oauth import (DRIVE_FILE, DriveWebOAuthError, DriveWebOAuthHandoff,
                                            EncryptedDriveSecretStore)
from personal_agent.personal_assistant import PersonalAssistantOrchestrator
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


PICKER_CHAT_ID = 42
SECRET_BYTES = b'private selected Drive bytes'


class ReadableDrive:
    """The shape the seam asks for, which nothing in the package provides.

    This exists only as a positive control.  Without it, a `blocked` result
    could just as easily come from the capability registry or from the excerpt
    range validation, and the cases below would pass while proving nothing
    about the missing `.read`.
    """

    def __init__(self): self.reads = []

    def read(self, file_id):
        self.reads.append(file_id)
        return SECRET_BYTES.decode()


class DriveSeamResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.registry = CapabilityRegistry(self.store)
        self.transport_calls = []
        encrypted = EncryptedDriveSecretStore(self.store, Fernet.generate_key())
        self.flow = DriveWebOAuthHandoff(encrypted, 'web-client',
                                         'https://connect.example.test/oauth/callback',
                                         'https://connect.example.test', now=lambda: 1000)

    def tearDown(self):
        self.temp.cleanup()

    def connect_and_select(self):
        """Put the shipped connector in its most permissive real state.

        Connected, scoped and with a Picker selection already made, so a
        refusal below cannot be blamed on an unconnected connector.
        """
        offer = self.flow.begin(PICKER_CHAT_ID)
        state = parse_qs(urlparse(offer['button']['url']).query)['state'][0]
        self.flow.complete({'state': state, 'code': 'short-code'}, PICKER_CHAT_ID,
                           lambda request: {'access_token': 'access-secret', 'refresh_token': 'refresh-secret',
                                            'scope': DRIVE_FILE, 'expires_in': 60})
        self.flow.select_files(PICKER_CHAT_ID, [{'id': 'file-1', 'name': 'plan', 'mime_type': 'text/plain'}])
        self.assertEqual(self.flow.status()['state'], 'connected')

    def transport(self, url, body, headers):
        self.transport_calls.append(url)
        return SECRET_BYTES

    def orchestrator(self, drive):
        self.registry.transition('google-drive-read', 'enabled', ('read',))
        return PersonalAssistantOrchestrator(self.store, drive=drive, now=lambda: 1)

    @staticmethod
    def excerpt_request(**extra):
        return {'message': 'Drive 발췌문: 선택', 'owner_id': 'local-owner', 'file_id': 'file-1', 'length': 8, **extra}

    def test_the_shipped_picker_connector_cannot_satisfy_the_excerpt_read_seam(self):
        """Option 2 was rejected; this is what rejecting it has to look like.

        `DriveWebOAuthHandoff` has `read_selected`, not `read`.  Before #393
        that call site raised `AttributeError`, which is neither a `ValueError`
        nor an `AssistantRequestError`, so it escaped the handler's owner-safe
        envelope entirely.  Now the absent shape is named and refused.
        """
        self.connect_and_select()
        self.assertFalse(hasattr(self.flow, 'read'))

        result = self.orchestrator(self.flow).draft_drive_excerpt(self.excerpt_request())

        self.assertEqual(result['state'], 'blocked')
        self.assertIn('Picker', result['response'])
        self.assertEqual(self.store.config('drive_excerpt_approvals', {}), {})
        # Positive control: with the shape the seam actually asks for, the very
        # same request succeeds.  So `blocked` above is attributable to the
        # missing `.read` and not to the registry or the excerpt range.
        readable = ReadableDrive()
        allowed = self.orchestrator(readable).draft_drive_excerpt(self.excerpt_request())
        self.assertEqual(allowed['state'], 'awaiting-approval')
        self.assertEqual(readable.reads, ['file-1'])

    def test_picker_selection_remains_the_authority_gate_and_the_seam_cannot_pass_it(self):
        """The security-relevant half: why the adapter was not written.

        `select_files_for_grant` accepts a selection owner only when it is an
        `int` Telegram chat id, and `PersonalAssistantOrchestrator._request`
        rejects any owner that is not a non-empty `str`.  The gate therefore
        refuses every identity the seam could supply, and the only way to get
        one through is to read the owner back out of the selection record the
        gate is checking -- the bypass #393 forbids.
        """
        self.connect_and_select()

        # The gate, exercised directly on the identity the seam would have had.
        with self.assertRaises(DriveWebOAuthError) as refused:
            self.flow.assert_selected('local-owner', 'file-1')
        self.assertIn('another Telegram owner', str(refused.exception))
        # Nor does coercing the chat id to text get past it, so "just pass the
        # owner string through" is not an available shortcut either.
        with self.assertRaises(DriveWebOAuthError):
            self.flow.assert_selected(str(PICKER_CHAT_ID), 'file-1')
        # The gate does open, for the identity the Picker actually recorded.
        self.assertTrue(self.flow.assert_selected(PICKER_CHAT_ID, 'file-1'))
        # And it is the gate, not an absent credential, that is deciding: the
        # authorized owner reaches the transport for this same file.
        self.assertEqual(self.flow.read_selected(PICKER_CHAT_ID, 'file-1', self.transport), SECRET_BYTES)
        self.assertEqual(len(self.transport_calls), 1)

        # The seam reaches none of it.  No transport call is added, and no
        # selected byte is retained anywhere the orchestrator writes.
        result = self.orchestrator(self.flow).draft_drive_excerpt(self.excerpt_request())

        self.assertEqual(result['state'], 'blocked')
        # Specifically the seam's own refusal.  Asserting only `blocked` here
        # would survive a bypass adapter whose `read` returned bytes, because
        # the excerpt slicing rejects a non-`str` a few lines later and blocks
        # for an unrelated reason.
        self.assertIn('이 동작을 제공하지 않습니다', result['response'])
        self.assertEqual(len(self.transport_calls), 1)
        self.assertNotIn(SECRET_BYTES.decode(), str(self.store.config('drive_excerpt_approvals', {})))
        self.assertNotIn(SECRET_BYTES.decode(), str(self.store.config('personal_assistant_evidence', [])))
        self.assertNotIn(SECRET_BYTES.decode(), str(result))

    def test_read_selected_refuses_a_file_the_requesting_owner_did_not_pick(self):
        """The gate this resolution rests on, pinned rather than assumed.

        #393 declines to adapt `read_selected` because its Picker selection
        check is the authority gate.  That argument is only as good as the
        check, and the check was unguarded: removing `assert_selected` from
        `read_selected` leaves `tests/test_drive_web_oauth.py` fully green,
        because the credential check beside it survives and the remaining
        lookup only happens to fail -- by `StopIteration` -- for an unselected
        file, and does not fail at all for the wrong owner.

        `drive_web_oauth.py` belongs to no iteration this issue owns, so the
        module is untouched and the case is recorded here instead.
        """
        self.connect_and_select()

        # Wrong owner, file genuinely selected by someone else.
        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(PICKER_CHAT_ID + 1, 'file-1', self.transport)
        # Right owner, file never picked.
        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(PICKER_CHAT_ID, 'file-2', self.transport)
        self.assertEqual(self.transport_calls, [])
        # The gate opens for the exact owner/file pair the Picker recorded, so
        # the two refusals above are the check firing, not a broken fixture.
        self.assertEqual(self.flow.read_selected(PICKER_CHAT_ID, 'file-1', self.transport), SECRET_BYTES)
        self.assertEqual(len(self.transport_calls), 1)

    def test_the_default_service_leaves_the_drive_seam_unpopulated(self):
        """`quickstart_service.py` is where wiring `drive=` would happen.

        #393 owns that file and declined to populate the seam.  Silently wiring
        it is the one outcome the carried criterion rejects, so the absence is
        asserted rather than assumed.
        """
        # The connector must be injected.  With the default `AgentService`
        # there is no connector to wire, so wiring one would pass `None` and
        # this case would assert nothing.
        self.connect_and_select()
        service = AgentService(self.store, drive_web_oauth=self.flow)
        self.assertIsNotNone(service.drive_web_oauth)
        self.assertIsNone(service.assistant_orchestrator.drive)

        self.registry.transition('google-drive-read', 'enabled', ('read',))
        result = service.personal_assistant_request({'action': 'drive-excerpt-draft', 'message': 'Drive 발췌문: 선택',
                                                     'file_id': 'file-1', 'length': 8})

        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(self.store.config('drive_excerpt_approvals', {}), {})

    def test_the_unwired_drive_message_names_a_route_the_owner_can_actually_take(self):
        """The carried criterion's other half: leave that message true.

        The prior text told the owner to set up the Drive connection first,
        while no owner-reachable route could populate this seam at all.  The
        replacement has to point at the capability that does exist.
        """
        unwired = self.orchestrator(None).draft_drive_excerpt(self.excerpt_request())

        self.assertEqual(unwired['state'], 'blocked')
        self.assertNotIn('연결을 먼저 설정하세요', unwired['response'])
        self.assertIn('Picker', unwired['response'])
        self.assertIn('Telegram', unwired['response'])
        # And that is the message the owner actually receives, not one only
        # reachable by constructing the orchestrator directly.
        service = AgentService(self.store)
        delivered = service.personal_assistant_request({'action': 'drive-excerpt-draft', 'message': 'Drive 발췌문: 선택',
                                                        'file_id': 'file-1', 'length': 8})
        self.assertEqual(delivered['response'], unwired['response'])

    def test_the_shipped_connectors_own_search_refusal_still_reaches_the_owner(self):
        """Naming the shape per call site, rather than requiring `.read` always.

        REUSE-R1c's decisive finding was that `DriveWebOAuthHandoff.search`
        exists only to be a seam-compatible refusal.  A blanket `.read`
        requirement on `_drive_adapter` would replace that specific refusal
        with a generic one and lose it.
        """
        self.connect_and_select()

        result = self.orchestrator(self.flow).handle({'message': 'Drive 검색: plan', 'owner_id': 'local-owner',
                                                      'query': 'plan'})

        self.assertEqual(result['state'], 'blocked')
        self.assertIn('drive.file', result['response'])
        self.assertNotIn('이 동작을 제공하지 않습니다', result['response'])


if __name__ == '__main__':
    unittest.main()
