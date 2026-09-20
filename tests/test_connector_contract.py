import hashlib
import json
import math
import tempfile
import unittest

from personal_agent.capabilities import CapabilityRegistry
from personal_agent.connector_contract import (
    CONNECTOR_STATE_KEY,
    PENDING_WORK_KEY,
    ConnectorContractError,
    ConnectorRegistry,
    ConnectorResultKind,
    ConnectorSpec,
    ConnectorState,
    PendingWorkRegistry,
    WorktreeDelegationRecord,
)
from personal_agent.quickstart_store import QuickStore


GMAIL = ConnectorSpec("google-gmail-read", ("gmail.readonly",))
CALENDAR = ConnectorSpec(
    "google-calendar-owner",
    ("calendar.events.read", "calendar.events.write"),
)
WORK_1 = "11111111-1111-4111-8111-111111111111"
WORK_2 = "22222222-2222-4222-8222-222222222222"
WORK_3 = "33333333-3333-4333-8333-333333333333"
WORK_4 = "44444444-4444-4444-8444-444444444444"


class ConnectorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.now = [1000.0]
        self.registry = ConnectorRegistry(
            self.store,
            (GMAIL, CALENDAR),
            clock=lambda: self.now[0],
        )
        self.pending = PendingWorkRegistry(
            self.store,
            self.registry,
            clock=lambda: self.now[0],
        )

    def tearDown(self):
        self.temp.cleanup()

    def connect(self, connector=GMAIL):
        return self.registry.transition(
            "owner-a",
            connector.connector_id,
            ConnectorState.CONNECTED,
            granted_scopes=connector.required_scopes,
        )

    def test_registration_is_sorted_idempotent_and_never_grants_scopes(self):
        registry = ConnectorRegistry(self.store, (GMAIL, CALENDAR))
        self.assertEqual(
            [item.connector_id for item in registry.definitions()],
            ["google-calendar-owner", "google-gmail-read"],
        )
        self.assertEqual(registry.register(GMAIL), GMAIL)
        status = registry.status("owner-a", GMAIL.connector_id)
        self.assertEqual(status.state, ConnectorState.DISCONNECTED)
        self.assertEqual(status.granted_scopes, ())
        self.assertNotIn("owner-a", json.dumps(self.store.config(CONNECTOR_STATE_KEY, {})))

    def test_typed_states_health_and_redacted_required_results(self):
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        result = self.registry.required_result(
            "owner-a", GMAIL.connector_id, resume_token=handle.token
        )
        self.assertEqual(result.kind, ConnectorResultKind.CONNECTION_REQUIRED)
        self.assertEqual(result.as_dict()["recovery"], "connect")
        rendered = json.dumps(result.as_dict())
        self.assertNotIn("owner-a", rendered)
        self.assertNotIn(WORK_1, rendered)

        reauth = self.registry.transition(
            "owner-a", GMAIL.connector_id, ConnectorState.REAUTH_REQUIRED
        )
        self.assertEqual(reauth.health.recovery.value, "reauthenticate")
        self.assertEqual(
            self.registry.required_result("owner-a", GMAIL.connector_id).kind,
            ConnectorResultKind.REAUTH_REQUIRED,
        )
        blocked = self.registry.transition(
            "owner-a", GMAIL.connector_id, ConnectorState.BLOCKED
        )
        self.assertEqual(blocked.health.recovery.value, "review_access")

    def test_unknown_connector_and_scope_mismatch_fail_closed(self):
        with self.assertRaisesRegex(ConnectorContractError, "connector contract rejected") as unknown:
            self.registry.status("owner-a", "unknown")
        self.assertEqual(unknown.exception.reason, "unknown_connector")
        with self.assertRaises(ConnectorContractError):
            self.registry.transition(
                "owner-a",
                GMAIL.connector_id,
                ConnectorState.CONNECTED,
                granted_scopes=(),
            )
        with self.assertRaises(ConnectorContractError):
            self.pending.issue(
                "owner-a", "work-1", GMAIL.connector_id, ("gmail.modify",)
            )
        self.assertEqual(
            self.registry.status("owner-a", GMAIL.connector_id).state,
            ConnectorState.DISCONNECTED,
        )

    def test_resume_is_owner_bound_opaque_minimal_and_exactly_once(self):
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        stored = json.dumps(self.store.config(PENDING_WORK_KEY))
        self.assertNotIn(handle.token, stored)
        self.assertNotIn("owner-a", stored)
        self.assertNotIn("private request body", stored)
        row = next(iter(self.store.config(PENDING_WORK_KEY).values()))
        self.assertEqual(
            set(row),
            {"owner", "work_id", "connector_id", "required_scopes", "expires_at", "used"},
        )
        self.connect()
        reference = self.pending.consume(
            handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes
        )
        self.assertEqual(reference.work_id, WORK_1)
        with self.assertRaises(ConnectorContractError) as replayed:
            self.pending.consume(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes
            )
        self.assertEqual(replayed.exception.reason, "replayed_resume")

        for unsafe in (
            "show my full private mail request",
            "show_my_full_private_mail_request",
            "c2hvdyBteSBmdWxsIHByaXZhdGUgbWFpbCByZXF1ZXN0",
            "x" * 161,
            "11111111-1111-1111-8111-111111111111",
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                self.pending.issue(
                    "owner-a", unsafe, GMAIL.connector_id, GMAIL.required_scopes
                )

    def test_wrong_owner_expiry_and_scope_mismatch_are_rejected_and_consumed(self):
        self.connect()
        cases = (
            (WORK_2, lambda handle: ("owner-b", GMAIL.connector_id, GMAIL.required_scopes), "invalid_resume"),
            (WORK_3, lambda handle: ("owner-a", GMAIL.connector_id, ("gmail.modify",)), "scope_mismatch"),
        )
        for work_id, arguments, reason in cases:
            with self.subTest(work_id):
                handle = self.pending.issue(
                    "owner-a", work_id, GMAIL.connector_id, GMAIL.required_scopes
                )
                with self.assertRaises(ConnectorContractError) as rejected:
                    self.pending.consume(handle.token, *arguments(handle))
                self.assertEqual(rejected.exception.reason, reason)
                with self.assertRaises(ConnectorContractError) as replayed:
                    self.pending.consume(
                        handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes
                    )
                self.assertEqual(replayed.exception.reason, "replayed_resume")

        expired = self.pending.issue(
            "owner-a", WORK_4, GMAIL.connector_id, GMAIL.required_scopes, ttl_seconds=1
        )
        self.now[0] += 1
        with self.assertRaises(ConnectorContractError) as rejected:
            self.pending.consume(
                expired.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes
            )
        self.assertEqual(rejected.exception.reason, "expired_resume")

    def test_corrupt_connected_grants_and_health_timestamp_fail_closed(self):
        self.connect()
        rows = self.store.config(CONNECTOR_STATE_KEY)
        owner_rows = next(iter(rows.values()))
        for grants in ([], ["gmail.readonly", "gmail.modify"]):
            with self.subTest(grants=grants):
                owner_rows[GMAIL.connector_id]["granted_scopes"] = grants
                self.store.put(CONNECTOR_STATE_KEY, rows)
                with self.assertRaises(ConnectorContractError) as rejected:
                    self.registry.status("owner-a", GMAIL.connector_id)
                self.assertEqual(rejected.exception.reason, "invalid_stored_state")

        owner_rows[GMAIL.connector_id]["granted_scopes"] = list(GMAIL.required_scopes)
        owner_rows[GMAIL.connector_id]["checked_at"] = math.nan
        self.store.put(CONNECTOR_STATE_KEY, rows)
        with self.assertRaises(ConnectorContractError) as rejected:
            self.registry.require_connected("owner-a", GMAIL.connector_id, GMAIL.required_scopes)
        self.assertEqual(rejected.exception.reason, "invalid_stored_state")

    def test_corrupt_pending_schema_work_reference_and_expiry_fail_closed(self):
        self.connect()
        corruptions = (
            ("work_id", "PRIVATE_PAYLOAD_WITH_UNDERSCORES"),
            ("work_id", "cHJpdmF0ZV9tYWlsX3JlcXVlc3Q"),
            ("expires_at", True),
            ("expires_at", math.nan),
            ("expires_at", math.inf),
            ("expires_at", "tomorrow"),
            ("used", "false"),
            ("required_scopes", "gmail.readonly"),
        )
        work_ids = (WORK_1, WORK_2, WORK_3, WORK_4)
        for index, (field, value) in enumerate(corruptions):
            with self.subTest(field=field, value=value):
                work_id = work_ids[index % len(work_ids)]
                handle = self.pending.issue(
                    "owner-a", work_id, GMAIL.connector_id, GMAIL.required_scopes
                )
                rows = self.store.config(PENDING_WORK_KEY)
                key = hashlib.sha256(handle.token.encode()).hexdigest()
                rows[key][field] = value
                self.store.put(PENDING_WORK_KEY, rows)
                with self.assertRaises(ConnectorContractError) as rejected:
                    self.pending.consume(
                        handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes
                    )
                self.assertEqual(rejected.exception.reason, "invalid_resume")

    def test_capability_compatibility_is_deterministic_and_disconnect_revokes(self):
        registry = CapabilityRegistry(self.store)
        ids = [item["id"] for item in registry.list()]
        self.assertEqual(ids, [item["id"] for item in registry.list()])
        self.assertTrue(all(item["grant"] == [] for item in registry.list()))
        registry.transition("google-drive-read", "enabled", ("read",))
        self.assertEqual(registry.transition("google-drive-read", "paused")["grant"], ["read"])
        self.assertEqual(registry.transition("google-drive-read", "disconnected")["grant"], [])

    def test_delegation_record_is_deterministic_and_does_not_grant_authority(self):
        record = WorktreeDelegationRecord(
            issue=387,
            branch="codex/387-pa1-connector-foundation",
            base_sha="a09f6c3bcc00170a50531ba9b1da265dd559d2e2",
            owned_files=("tests/test_connector_contract.py", "src/personal_agent/connector_contract.py"),
            requested_profile="critical",
            tool_accepted_setting="gpt-5.6-sol/high",
        )
        value = record.as_dict()
        self.assertEqual(value["observed_execution_setting"], "unknown")
        self.assertEqual(value["owned_files"], sorted(value["owned_files"]))
        self.assertNotIn("grant", value)


if __name__ == "__main__":
    unittest.main()
