"""J4: the model may read the calendar and propose a change, never apply one.

EPIC-PA1 J4 asks to "ask what is scheduled, create a new event with exact
preview/approval, and support bounded update/cancel behavior with truthful
result/recovery state".

`CalendarConnector` has implemented all of that since #390 and was reachable
from no channel: `query`, `draft_update` and `draft_cancel` had no intent, no
route and no worker branch, so a fully tested policy core sat behind a clean
"not configured locally" refusal.  An earlier audit concluded the gap was
deterministic Korean prose-to-event extraction.  It is not: the model supplies
structured tool arguments, exactly as it does for `bounded_public_research`,
and the prose problem disappears.  The intent classifier is forbidden a model
(`conversation_handoff.py:105-110`); tool arguments never were.

The authority split this file pins is the load-bearing part.  A draft is a
proposal carrying an exact preview.  Applying it needs a one-time approval
token bound to this owner, this draft, this payload hash and the write
connector's `connection_revision` -- and the model has no tool that mints one.
"""
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import Capabilities, MEMORY_OWNER
from personal_agent.calendar import (CALENDAR_SPEC, CALENDAR_WRITE_SPEC,
                                     CalendarConnector)
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.google_calendar import CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE
from personal_agent.quickstart_store import QuickStore

CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'm'}
EVENT = {'id': 'ev1', 'summary': '팀 회의', 'version': '"etag1"'}


class Provider:
    """Stands in for GoogleCalendar and records what the policy layer asked."""

    def __init__(self):
        self.calls = []

    def query(self, start, end, timezone, max_results):
        self.calls.append(('query', start, end, timezone))
        return [{**EVENT, 'start': start, 'end': end}]

    def create(self, payload, idempotency_key):
        self.calls.append(('create', payload, idempotency_key))
        return {'id': 'new1', 'version': '"etag2"'}

    def update(self, event_id, event_version, changes):
        self.calls.append(('update', event_id, event_version, changes))
        return {'id': event_id, 'version': '"etag3"'}

    def cancel(self, event_id, event_version):
        self.calls.append(('cancel', event_id, event_version))
        return {'id': event_id, 'status': 'cancelled'}


class Egress:
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        return {'tool': plan['tool'], 'results': [], 'sources': [], 'retrieved_at': 1}


class CalendarToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC))
        self.provider = Provider()
        self.calendar = CalendarConnector(self.store, self.provider, registry=self.registry)
        self.egress = Egress()

    def caps(self, calendar=True, **kwargs):
        return Capabilities(self.store, None, CFG, '', 'job', lambda *a: None,
                            network=self.egress,
                            calendar=self.calendar if calendar else None, **kwargs)

    def connect(self, read=True, write=False):
        if read:
            self.registry.transition(MEMORY_OWNER, CALENDAR_SPEC.connector_id,
                                     ConnectorState.CONNECTED,
                                     granted_scopes=(CALENDAR_READ_SCOPE,))
        if write:
            self.registry.transition(MEMORY_OWNER, CALENDAR_WRITE_SPEC.connector_id,
                                     ConnectorState.CONNECTED,
                                     granted_scopes=(CALENDAR_WRITE_SCOPE,))

    def query(self, caps):
        return caps.execute('calendar_query', {'start': '2026-09-23T00:00:00+09:00',
                                               'end': '2026-09-24T00:00:00+09:00',
                                               'timezone': 'Asia/Seoul'})

    def draft(self, caps):
        return caps.execute('calendar_draft_create',
                            {'summary': '치과', 'start': '2026-09-25T10:00:00+09:00',
                             'end': '2026-09-25T11:00:00+09:00', 'timezone': 'Asia/Seoul'})

    # -- reachability, which is the whole defect --------------------------

    def test_the_tools_exist_and_are_declared(self):
        from personal_agent.agent_runtime import DEFINITIONS
        declared = {tool['function']['name'] for tool in DEFINITIONS}
        for name in ('calendar_query', 'calendar_draft_create',
                     'calendar_draft_update', 'calendar_draft_cancel'):
            with self.subTest(tool=name):
                self.assertIn(name, declared)

    def test_asking_what_is_scheduled_reaches_the_provider(self):
        self.connect()
        result = self.query(self.caps())
        self.assertEqual(result['events'][0]['summary'], '팀 회의')
        self.assertEqual(self.provider.calls[0][0], 'query')

    def test_the_read_returns_what_update_and_cancel_need(self):
        """Without id and version, bounded update/cancel is unreachable."""
        self.connect()
        event = self.query(self.caps())['events'][0]
        self.assertTrue(event['id'])
        self.assertTrue(event['version'])

    # -- the authority split ----------------------------------------------

    def test_the_model_has_no_tool_that_applies_a_change(self):
        """The load-bearing assertion. Drafting is proposing, not doing."""
        caps = self.caps()
        for forbidden in ('approve', 'execute', 'create_calendar', 'calendar_apply'):
            with self.subTest(tool=forbidden):
                self.assertNotIn(forbidden, caps.tools)
        self.assertEqual(
            sorted(name for name in caps.tools if name.startswith('calendar_')),
            ['calendar_draft_cancel', 'calendar_draft_create',
             'calendar_draft_update', 'calendar_query'])

    def test_a_draft_is_not_applied_and_says_so(self):
        self.connect(write=True)
        draft = self.draft(self.caps())
        self.assertFalse(draft['applied'])
        self.assertTrue(draft['requires_owner_approval'])
        self.assertTrue(draft['preview']['payload'])
        # Nothing reached the provider: drafting is local.
        self.assertEqual([call[0] for call in self.provider.calls], [])

    def test_an_approval_is_refused_without_the_write_grant(self):
        """A read grant never becomes a write grant.

        The draft is allowed without it -- a proposal costs nothing -- but the
        owner's approval step is where the write connector is checked, and it
        refuses.
        """
        self.connect(read=True, write=False)
        draft = self.draft(self.caps())
        with self.assertRaises(ValueError):
            self.calendar.approve(draft['draft_id'], MEMORY_OWNER)
        self.assertEqual([call[0] for call in self.provider.calls], [])

    def test_the_owner_can_approve_once_the_write_grant_exists(self):
        """The opposing pin: refused by authority, not broken."""
        self.connect(write=True)
        draft = self.draft(self.caps())
        approval = self.calendar.approve(draft['draft_id'], MEMORY_OWNER)
        self.assertTrue(approval['approval_id'])

    def test_the_preview_is_the_exact_payload_that_would_be_sent(self):
        self.connect(write=True)
        draft = self.draft(self.caps())
        payload = draft['preview']['payload']
        self.assertEqual(payload['summary'], '치과')
        self.assertEqual(payload['start'], '2026-09-25T10:00:00+09:00')
        self.assertTrue(draft['preview']['payload_hash'])

    def test_update_and_cancel_require_an_exact_event_version(self):
        self.connect(write=True)
        caps = self.caps()
        for tool, args in (
                ('calendar_draft_update', {'event_id': 'ev1', 'event_version': '*'}),
                ('calendar_draft_cancel', {'event_id': 'ev1', 'event_version': '*'})):
            with self.subTest(tool=tool):
                with self.assertRaises(ValueError):
                    caps.execute(tool, args)

    def test_update_and_cancel_draft_with_a_real_version(self):
        self.connect(write=True)
        caps = self.caps()
        update = caps.execute('calendar_draft_update',
                              {'event_id': 'ev1', 'event_version': '"etag1"',
                               'summary': '팀 회의 (변경)'})
        cancel = caps.execute('calendar_draft_cancel',
                              {'event_id': 'ev1', 'event_version': '"etag1"'})
        self.assertFalse(update['applied'])
        self.assertFalse(cancel['applied'])
        self.assertEqual([call[0] for call in self.provider.calls], [])

    # -- boundaries --------------------------------------------------------

    def test_an_unconfigured_calendar_refuses_cleanly(self):
        """The honest state before this work, preserved for that case."""
        caps = self.caps(calendar=False)
        with self.assertRaises(ValueError) as refused:
            self.query(caps)
        self.assertIn('구성되어 있지 않습니다', str(refused.exception))

    def test_reading_the_calendar_closes_public_destinations(self):
        """Calendar contents are owner-private.

        Event titles are among the most sensitive things the owner owns, and
        this is a read that puts them in the model's context.
        """
        self.connect()
        caps = self.caps()
        self.query(caps)
        self.assertEqual(caps.private_egress_provenance(), ['owner-calendar'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': 'unrelated public question'})
        self.assertEqual(self.egress.plans, [])

    def test_attendees_and_recurrence_are_refused(self):
        """J4 excludes attendee invitation; `_CONTENT_FIELDS` is an allowlist."""
        self.connect(write=True)
        with self.assertRaises(ValueError):
            self.calendar.draft_create(
                {'summary': '회의', 'start': '2026-09-25T10:00:00+09:00',
                 'end': '2026-09-25T11:00:00+09:00', 'timezone': 'Asia/Seoul',
                 'attendees': ['someone@example.com']}, MEMORY_OWNER)

    def test_the_specialist_roles_do_not_get_calendar(self):
        from personal_agent.manifests import BUILTIN_MANIFEST
        for role in BUILTIN_MANIFEST['roles']:
            with self.subTest(role=role['id']):
                self.assertEqual([t for t in role['tools'] if t.startswith('calendar_')], [])


if __name__ == '__main__':
    unittest.main()
