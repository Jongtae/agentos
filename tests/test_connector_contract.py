import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import tempfile
import threading
import time
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
    HealthState,
    PendingWorkRegistry,
    RecoveryAction,
)
from personal_agent.quickstart_store import QuickStore


GMAIL = ConnectorSpec("google-gmail-read", ("gmail.readonly",))
CALENDAR = ConnectorSpec(
    "google-calendar-owner",
    ("calendar.events.read", "calendar.events.write"),
)
MULTI_SCOPE = ConnectorSpec("mail-owner", ("mail.read", "mail.write"))
WORK_1 = "11111111-1111-4111-8111-111111111111"
WORK_2 = "22222222-2222-4222-8222-222222222222"
WORK_3 = "33333333-3333-4333-8333-333333333333"
WORK_4 = "44444444-4444-4444-8444-444444444444"
HANDOFF_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HANDOFF_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
REVISION_1 = "AQEBAQEBAQEBAQEBAQEBAQ"


def work_id(number):
    return f"{number:08x}-0000-4000-8000-{number:012x}"


class ConnectorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.now = [1000.0]
        self.revision_number = [0]

        def revision_factory():
            self.revision_number[0] += 1
            raw = self.revision_number[0].to_bytes(16, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        self.registry = ConnectorRegistry(
            self.store,
            (GMAIL, CALENDAR),
            clock=lambda: self.now[0],
            revision_factory=revision_factory,
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
        self.assertEqual(reauth.health.state, HealthState.UNKNOWN)
        required = self.registry.required_result("owner-a", GMAIL.connector_id)
        self.assertEqual(required.kind, ConnectorResultKind.REAUTH_REQUIRED)
        self.assertEqual(required.recovery, RecoveryAction.REAUTHENTICATE)
        blocked = self.registry.transition(
            "owner-a", GMAIL.connector_id, ConnectorState.BLOCKED
        )
        self.assertEqual(blocked.health.state, HealthState.UNKNOWN)
        self.assertIsNone(blocked.health.recovery)

    def test_connected_does_not_imply_health_until_observed(self):
        connected = self.connect()
        self.assertEqual(connected.health.state, HealthState.UNKNOWN)
        self.assertIsNone(connected.health.checked_at)
        self.assertIsNotNone(connected.connection_revision)
        healthy = self.registry.record_health(
            "owner-a",
            GMAIL.connector_id,
            HealthState.HEALTHY,
            expected_revision=connected.connection_revision,
        )
        self.assertEqual(healthy.state, ConnectorState.CONNECTED)
        self.assertEqual(healthy.health.state, HealthState.HEALTHY)
        self.assertEqual(healthy.health.checked_at, self.now[0])
        unavailable = self.registry.record_health(
            "owner-a",
            GMAIL.connector_id,
            HealthState.UNAVAILABLE,
            expected_revision=connected.connection_revision,
            recovery=RecoveryAction.REAUTHENTICATE,
        )
        self.assertEqual(unavailable.health.state, HealthState.UNAVAILABLE)
        self.assertEqual(unavailable.health.recovery, RecoveryAction.REAUTHENTICATE)
        transitioned = self.registry.transition(
            "owner-a",
            GMAIL.connector_id,
            ConnectorState.CONNECTED,
            granted_scopes=GMAIL.required_scopes,
        )
        self.assertEqual(transitioned.health.state, HealthState.UNKNOWN)
        self.assertIsNone(transitioned.health.checked_at)
        self.assertNotEqual(transitioned.connection_revision, connected.connection_revision)
        with self.assertRaises(ConnectorContractError):
            self.registry.record_health(
                "owner-a",
                GMAIL.connector_id,
                HealthState.UNKNOWN,
                expected_revision=transitioned.connection_revision,
            )

    def test_health_observation_is_bound_to_connection_revision(self):
        connection_a = self.connect()
        revision_a = connection_a.connection_revision
        self.registry.transition("owner-a", GMAIL.connector_id, ConnectorState.DISCONNECTED)
        connection_b = self.connect()
        self.assertNotEqual(connection_b.connection_revision, revision_a)

        with self.assertRaises(ConnectorContractError) as stale:
            self.registry.record_health(
                "owner-a",
                GMAIL.connector_id,
                HealthState.HEALTHY,
                expected_revision=revision_a,
            )
        self.assertEqual(stale.exception.reason, "stale_connection_revision")
        current = self.registry.status("owner-a", GMAIL.connector_id)
        self.assertEqual(current.connection_revision, connection_b.connection_revision)
        self.assertEqual(current.health.state, HealthState.UNKNOWN)

        observed = self.registry.record_health(
            "owner-a",
            GMAIL.connector_id,
            HealthState.HEALTHY,
            expected_revision=connection_b.connection_revision,
        )
        self.assertEqual(observed.health.state, HealthState.HEALTHY)

    def test_concurrent_stale_health_result_cannot_mark_reconnected_lifecycle(self):
        connection_a = self.connect()
        observation_started = threading.Barrier(2)
        release_result = threading.Event()

        def finish_observation():
            observation_started.wait(timeout=5)
            if not release_result.wait(timeout=5):
                raise RuntimeError("health observation test barrier timed out")
            return self.registry.record_health(
                "owner-a",
                GMAIL.connector_id,
                HealthState.HEALTHY,
                expected_revision=connection_a.connection_revision,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(finish_observation)
            observation_started.wait(timeout=5)
            self.registry.transition("owner-a", GMAIL.connector_id, ConnectorState.DISCONNECTED)
            connection_b = self.connect()
            release_result.set()
            with self.assertRaises(ConnectorContractError) as stale:
                future.result(timeout=5)
        self.assertEqual(stale.exception.reason, "stale_connection_revision")
        current = self.registry.status("owner-a", GMAIL.connector_id)
        self.assertEqual(current.connection_revision, connection_b.connection_revision)
        self.assertEqual(current.health.state, HealthState.UNKNOWN)

    def test_connection_revision_is_strict_opaque_and_owner_safe(self):
        disconnected = self.registry.status("owner-a", GMAIL.connector_id)
        self.assertIsNone(disconnected.connection_revision)
        connected = self.connect()
        rendered = json.dumps(connected.as_dict())
        self.assertIn(connected.connection_revision, rendered)
        self.assertNotIn("owner-a", rendered)

        rows = self.store.config(CONNECTOR_STATE_KEY)
        owner_rows = next(iter(rows.values()))
        for malformed in (None, "", "private connection secret", "!" * 22, "A" * 200):
            with self.subTest(malformed=malformed):
                owner_rows[GMAIL.connector_id]["connection_revision"] = malformed
                self.store.put(CONNECTOR_STATE_KEY, rows)
                operations = (
                    lambda: self.registry.status("owner-a", GMAIL.connector_id),
                    lambda: self.registry.transition(
                        "owner-a",
                        GMAIL.connector_id,
                        ConnectorState.CONNECTED,
                        granted_scopes=GMAIL.required_scopes,
                    ),
                    lambda: self.registry.record_health(
                        "owner-a",
                        GMAIL.connector_id,
                        HealthState.HEALTHY,
                        expected_revision=REVISION_1,
                    ),
                    lambda: self.registry.require_connected(
                        "owner-a", GMAIL.connector_id, GMAIL.required_scopes
                    ),
                )
                for operation in operations:
                    with self.assertRaises(ConnectorContractError) as rejected:
                        operation()
                    self.assertEqual(rejected.exception.reason, "invalid_stored_state")
                    stored = self.store.config(CONNECTOR_STATE_KEY)
                    stored_owner = next(iter(stored.values()))
                    self.assertEqual(
                        stored_owner[GMAIL.connector_id]["connection_revision"], malformed
                    )

        with tempfile.TemporaryDirectory() as root:
            rejecting = ConnectorRegistry(
                QuickStore(root),
                (GMAIL,),
                clock=lambda: self.now[0],
                revision_factory=lambda: "private connection secret",
            )
            with self.assertRaises(ConnectorContractError) as invalid:
                rejecting.transition(
                    "owner-a",
                    GMAIL.connector_id,
                    ConnectorState.CONNECTED,
                    granted_scopes=GMAIL.required_scopes,
                )
            self.assertEqual(invalid.exception.reason, "invalid_revision")

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

    def test_resume_claim_is_recoverable_and_complete_is_terminal(self):
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
            {
                "owner", "work_id", "connector_id", "required_scopes", "expires_at",
                "state", "claim_digest", "claimed_at", "completed_at", "terminal_at", "sequence",
            },
        )
        self.connect()
        reference = self.pending.claim(
            handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
        )
        self.assertEqual(reference.work_id, WORK_1)
        recovered = PendingWorkRegistry(
            self.store, self.registry, clock=lambda: self.now[0]
        ).claim(handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1)
        self.assertEqual(recovered, reference)
        completed = self.pending.complete(
            handle.token, "owner-a", GMAIL.connector_id, HANDOFF_1
        )
        self.assertEqual(completed, reference)
        for operation in (
            lambda: self.pending.claim(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            ),
            lambda: self.pending.complete(
                handle.token, "owner-a", GMAIL.connector_id, HANDOFF_1
            ),
        ):
            with self.assertRaises(ConnectorContractError) as replayed:
                operation()
            self.assertEqual(replayed.exception.reason, "replayed_resume")

        unclaimed = self.pending.issue(
            "owner-a", WORK_2, GMAIL.connector_id, GMAIL.required_scopes
        )
        with self.assertRaises(ConnectorContractError) as early:
            self.pending.complete(
                unclaimed.token, "owner-a", GMAIL.connector_id, HANDOFF_1
            )
        self.assertEqual(early.exception.reason, "unclaimed_resume")

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

    def test_wrong_owner_scope_and_connector_are_rejected_and_superseded(self):
        self.connect()
        cases = (
            (WORK_2, ("owner-b", GMAIL.connector_id, GMAIL.required_scopes), "invalid_resume"),
            (WORK_3, ("owner-a", GMAIL.connector_id, ("gmail.modify",)), "scope_mismatch"),
            (WORK_4, ("owner-a", CALENDAR.connector_id, GMAIL.required_scopes), "invalid_resume"),
        )
        for current_work, arguments, reason in cases:
            with self.subTest(current_work):
                handle = self.pending.issue(
                    "owner-a", current_work, GMAIL.connector_id, GMAIL.required_scopes
                )
                with self.assertRaises(ConnectorContractError) as rejected:
                    self.pending.claim(handle.token, *arguments, HANDOFF_1)
                self.assertEqual(rejected.exception.reason, reason)
                with self.assertRaises(ConnectorContractError) as replayed:
                    self.pending.claim(
                        handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
                    )
                self.assertEqual(replayed.exception.reason, "superseded_resume")

        expired = self.pending.issue(
            "owner-a", work_id(5), GMAIL.connector_id, GMAIL.required_scopes, ttl_seconds=1
        )
        self.now[0] += 1
        with self.assertRaises(ConnectorContractError) as rejected:
            self.pending.claim(
                expired.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            )
        self.assertEqual(rejected.exception.reason, "expired_resume")

    def test_pending_time_is_sampled_after_waiting_for_serialization_lock(self):
        class WaitingLock:
            def __init__(self):
                self.underlying = threading.RLock()
                self.attempted = threading.Event()

            def __enter__(self):
                self.attempted.set()
                self.underlying.acquire()
                return self

            def __exit__(self, _kind, _value, _traceback):
                self.underlying.release()

        self.connect()
        expiring = self.pending.issue(
            "owner-a",
            WORK_1,
            GMAIL.connector_id,
            GMAIL.required_scopes,
            ttl_seconds=1,
        )
        claim_gate = WaitingLock()
        self.pending._lock = claim_gate
        claim_gate.underlying.acquire()
        claim_lock_held = True
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            claim_future = pool.submit(
                self.pending.claim,
                expiring.token,
                "owner-a",
                GMAIL.connector_id,
                GMAIL.required_scopes,
                HANDOFF_1,
            )
            self.assertTrue(claim_gate.attempted.wait(timeout=5))
            self.now[0] = expiring.expires_at
            claim_gate.underlying.release()
            claim_lock_held = False
            with self.assertRaises(ConnectorContractError) as expired:
                claim_future.result(timeout=5)
        finally:
            if claim_lock_held:
                claim_gate.underlying.release()
            pool.shutdown(wait=True)
        self.assertEqual(expired.exception.reason, "expired_resume")

        pending = PendingWorkRegistry(
            self.store, self.registry, clock=lambda: self.now[0]
        )
        handle = pending.issue(
            "owner-a", WORK_2, GMAIL.connector_id, GMAIL.required_scopes
        )
        pending.claim(
            handle.token,
            "owner-a",
            GMAIL.connector_id,
            GMAIL.required_scopes,
            HANDOFF_2,
        )
        complete_gate = WaitingLock()
        pending._lock = complete_gate
        complete_gate.underlying.acquire()
        complete_lock_held = True
        completed_at = self.now[0] + 10
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            complete_future = pool.submit(
                pending.complete,
                handle.token,
                "owner-a",
                GMAIL.connector_id,
                HANDOFF_2,
            )
            self.assertTrue(complete_gate.attempted.wait(timeout=5))
            self.now[0] = completed_at
            complete_gate.underlying.release()
            complete_lock_held = False
            self.assertEqual(complete_future.result(timeout=5).work_id, WORK_2)
        finally:
            if complete_lock_held:
                complete_gate.underlying.release()
            pool.shutdown(wait=True)
        row = self.store.config(PENDING_WORK_KEY)[
            hashlib.sha256(handle.token.encode()).hexdigest()
        ]
        self.assertEqual(row["completed_at"], completed_at)

    def test_competing_claims_are_serialized_but_same_claim_is_recoverable(self):
        self.connect()
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )

        def claim(handoff_id):
            try:
                return self.pending.claim(
                    handle.token,
                    "owner-a",
                    GMAIL.connector_id,
                    GMAIL.required_scopes,
                    handoff_id,
                ).work_id
            except ConnectorContractError as exc:
                return exc.reason

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, (HANDOFF_1, HANDOFF_2)))
        self.assertIn(WORK_1, results)
        self.assertIn("resume_claimed", results)
        winner = HANDOFF_1 if results[0] == WORK_1 else HANDOFF_2
        loser = HANDOFF_2 if winner == HANDOFF_1 else HANDOFF_1
        self.assertEqual(claim(winner), WORK_1)
        with self.assertRaises(ConnectorContractError) as competing_complete:
            self.pending.complete(
                handle.token, "owner-a", GMAIL.connector_id, loser
            )
        self.assertEqual(competing_complete.exception.reason, "invalid_resume")

    def test_initial_claim_and_connector_revocation_commit_in_one_serial_order(self):
        class ClaimWinsRegistry(ConnectorRegistry):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.checked = threading.Barrier(2)
                self.release = threading.Event()
                self.revoke_attempted = threading.Event()

            def require_connected(self, *args, **kwargs):
                result = super().require_connected(*args, **kwargs)
                self.checked.wait(timeout=5)
                if not self.release.wait(timeout=5):
                    raise RuntimeError("claim test barrier timed out")
                return result

            def transition(self, owner_id, connector_id, state, **kwargs):
                if state is ConnectorState.DISCONNECTED:
                    self.revoke_attempted.set()
                return super().transition(owner_id, connector_id, state, **kwargs)

        with tempfile.TemporaryDirectory() as root:
            store = QuickStore(root)
            registry = ClaimWinsRegistry(store, (GMAIL,), clock=lambda: self.now[0])
            pending = PendingWorkRegistry(store, registry, clock=lambda: self.now[0])
            registry.transition(
                "owner-a", GMAIL.connector_id, ConnectorState.CONNECTED,
                granted_scopes=GMAIL.required_scopes,
            )
            handle = pending.issue("owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes)
            with ThreadPoolExecutor(max_workers=2) as pool:
                claim_future = pool.submit(
                    pending.claim,
                    handle.token,
                    "owner-a",
                    GMAIL.connector_id,
                    GMAIL.required_scopes,
                    HANDOFF_1,
                )
                registry.checked.wait(timeout=5)
                revoke_future = pool.submit(
                    registry.transition,
                    "owner-a",
                    GMAIL.connector_id,
                    ConnectorState.DISCONNECTED,
                )
                self.assertTrue(registry.revoke_attempted.wait(timeout=5))
                self.assertFalse(revoke_future.done())
                registry.release.set()
                self.assertEqual(claim_future.result(timeout=5).work_id, WORK_1)
                self.assertEqual(
                    revoke_future.result(timeout=5).state, ConnectorState.DISCONNECTED
                )

        class RevokeWinsRegistry(ConnectorRegistry):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.revoke_locked = threading.Barrier(2)
                self.release = threading.Event()

            def transition(self, owner_id, connector_id, state, **kwargs):
                if state is ConnectorState.DISCONNECTED:
                    with self._authority_guard():
                        self.revoke_locked.wait(timeout=5)
                        if not self.release.wait(timeout=5):
                            raise RuntimeError("revoke test barrier timed out")
                        return super().transition(owner_id, connector_id, state, **kwargs)
                return super().transition(owner_id, connector_id, state, **kwargs)

        with tempfile.TemporaryDirectory() as root:
            store = QuickStore(root)
            registry = RevokeWinsRegistry(store, (GMAIL,), clock=lambda: self.now[0])
            pending = PendingWorkRegistry(store, registry, clock=lambda: self.now[0])
            registry.transition(
                "owner-a", GMAIL.connector_id, ConnectorState.CONNECTED,
                granted_scopes=GMAIL.required_scopes,
            )
            handle = pending.issue("owner-a", WORK_2, GMAIL.connector_id, GMAIL.required_scopes)
            with ThreadPoolExecutor(max_workers=2) as pool:
                revoke_future = pool.submit(
                    registry.transition,
                    "owner-a",
                    GMAIL.connector_id,
                    ConnectorState.DISCONNECTED,
                )
                registry.revoke_locked.wait(timeout=5)
                claim_future = pool.submit(
                    pending.claim,
                    handle.token,
                    "owner-a",
                    GMAIL.connector_id,
                    GMAIL.required_scopes,
                    HANDOFF_2,
                )
                registry.release.set()
                self.assertEqual(
                    revoke_future.result(timeout=5).state, ConnectorState.DISCONNECTED
                )
                with self.assertRaises(ConnectorContractError) as rejected:
                    claim_future.result(timeout=5)
                self.assertEqual(rejected.exception.reason, ConnectorState.DISCONNECTED.value)

    def test_work_deduplication_does_not_partition_by_scope_subset(self):
        registry = ConnectorRegistry(self.store, (MULTI_SCOPE,), clock=lambda: self.now[0])
        pending = PendingWorkRegistry(self.store, registry, clock=lambda: self.now[0])
        registry.transition(
            "owner-a",
            MULTI_SCOPE.connector_id,
            ConnectorState.CONNECTED,
            granted_scopes=MULTI_SCOPE.required_scopes,
        )

        read_offer = pending.issue(
            "owner-a", WORK_1, MULTI_SCOPE.connector_id, ("mail.read",)
        )
        write_offer = pending.issue(
            "owner-a", WORK_1, MULTI_SCOPE.connector_id, ("mail.write",)
        )
        with self.assertRaises(ConnectorContractError) as superseded:
            pending.claim(
                read_offer.token,
                "owner-a",
                MULTI_SCOPE.connector_id,
                ("mail.read",),
                HANDOFF_1,
            )
        self.assertEqual(superseded.exception.reason, "superseded_resume")
        pending.claim(
            write_offer.token,
            "owner-a",
            MULTI_SCOPE.connector_id,
            ("mail.write",),
            HANDOFF_2,
        )
        with self.assertRaises(ConnectorContractError) as claimed:
            pending.issue(
                "owner-a", WORK_1, MULTI_SCOPE.connector_id, ("mail.read",)
            )
        self.assertEqual(claimed.exception.reason, "work_already_claimed")
        pending.complete(
            write_offer.token, "owner-a", MULTI_SCOPE.connector_id, HANDOFF_2
        )
        with self.assertRaises(ConnectorContractError) as completed:
            pending.issue(
                "owner-a", WORK_1, MULTI_SCOPE.connector_id, ("mail.read",)
            )
        self.assertEqual(completed.exception.reason, "work_already_completed")

    def test_reissue_rejects_claimed_and_completed_work_but_claimant_recovers(self):
        self.connect()
        first = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        self.pending.claim(
            first.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
        )
        self.now[0] += 901
        with self.assertRaises(ConnectorContractError) as duplicate_claimed:
            self.pending.issue(
                "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
            )
        self.assertEqual(duplicate_claimed.exception.reason, "work_already_claimed")
        self.assertEqual(
            self.pending.claim(
                first.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            ).work_id,
            WORK_1,
        )
        self.pending.complete(first.token, "owner-a", GMAIL.connector_id, HANDOFF_1)
        with self.assertRaises(ConnectorContractError) as duplicate_completed:
            self.pending.issue(
                "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
            )
        self.assertEqual(duplicate_completed.exception.reason, "work_already_completed")
        rows = self.store.config(PENDING_WORK_KEY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(next(iter(rows.values()))["state"], "completed")

    def test_claim_remains_authoritative_after_disconnect_until_complete(self):
        self.connect()
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        claimed = self.pending.claim(
            handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
        )
        self.registry.transition("owner-a", GMAIL.connector_id, ConnectorState.DISCONNECTED)
        recovered = self.pending.claim(
            handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
        )
        self.assertEqual(recovered, claimed)
        with self.assertRaises(ConnectorContractError) as competitor:
            self.pending.claim(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_2
            )
        self.assertEqual(competitor.exception.reason, "resume_claimed")
        self.assertEqual(
            self.pending.complete(
                handle.token, "owner-a", GMAIL.connector_id, HANDOFF_1
            ),
            claimed,
        )
        self.connect()
        with self.assertRaises(ConnectorContractError) as duplicate:
            self.pending.issue(
                "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
            )
        self.assertEqual(duplicate.exception.reason, "work_already_completed")
        self.assertEqual(len(self.store.config(PENDING_WORK_KEY)), 1)

    def test_pending_offer_is_superseded_when_initial_connection_check_fails(self):
        self.connect()
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        self.registry.transition("owner-a", GMAIL.connector_id, ConnectorState.REAUTH_REQUIRED)
        with self.assertRaises(ConnectorContractError) as rejected:
            self.pending.claim(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            )
        self.assertEqual(rejected.exception.reason, ConnectorState.REAUTH_REQUIRED.value)
        self.connect()
        with self.assertRaises(ConnectorContractError) as terminal:
            self.pending.claim(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            )
        self.assertEqual(terminal.exception.reason, "superseded_resume")

    def test_reissue_supersedes_only_unclaimed_pending_handle(self):
        self.connect()
        first = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        second = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        with self.assertRaises(ConnectorContractError) as old:
            self.pending.claim(
                first.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
            )
        self.assertEqual(old.exception.reason, "superseded_resume")
        self.assertEqual(
            self.pending.claim(
                second.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_2
            ).work_id,
            WORK_1,
        )

    def test_completed_tombstone_is_bounded_not_an_indefinite_execution_claim(self):
        self.connect()
        pending = PendingWorkRegistry(
            self.store,
            self.registry,
            clock=lambda: self.now[0],
            terminal_retention_seconds=2,
        )
        first = pending.issue("owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes)
        pending.claim(first.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1)
        pending.complete(first.token, "owner-a", GMAIL.connector_id, HANDOFF_1)
        with self.assertRaises(ConnectorContractError) as retained:
            pending.issue("owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes)
        self.assertEqual(retained.exception.reason, "work_already_completed")
        self.now[0] += 2
        replacement = pending.issue("owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes)
        self.assertNotEqual(replacement.token, first.token)

    def test_terminal_and_expired_retention_is_bounded_and_pruned(self):
        self.connect()
        token_counter = [0]

        def deterministic_token():
            token_counter[0] += 1
            raw = token_counter[0].to_bytes(32, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        pending = PendingWorkRegistry(
            self.store,
            self.registry,
            clock=lambda: self.now[0],
            max_records=3,
            terminal_retention_seconds=2,
            token_factory=deterministic_token,
        )
        handles = []
        for number in range(10, 15):
            handle = pending.issue(
                "owner-a", work_id(number), GMAIL.connector_id, GMAIL.required_scopes
            )
            handoff = work_id(number + 100)
            pending.claim(
                handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, handoff
            )
            pending.complete(handle.token, "owner-a", GMAIL.connector_id, handoff)
            handles.append(handle)
            self.assertLessEqual(len(self.store.config(PENDING_WORK_KEY)), 3)
        with self.assertRaises(ConnectorContractError) as pruned:
            pending.claim(
                handles[0].token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, work_id(110)
            )
        self.assertEqual(pruned.exception.reason, "invalid_resume")

        expiring = pending.issue(
            "owner-a", work_id(20), GMAIL.connector_id, GMAIL.required_scopes, ttl_seconds=1
        )
        self.now[0] += 1
        with self.assertRaises(ConnectorContractError) as expired:
            pending.claim(
                expiring.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, work_id(120)
            )
        self.assertEqual(expired.exception.reason, "expired_resume")
        self.now[0] += 2
        pending.issue("owner-a", work_id(21), GMAIL.connector_id, GMAIL.required_scopes)
        self.assertNotIn(hashlib.sha256(expiring.token.encode()).hexdigest(), self.store.config(PENDING_WORK_KEY))

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
        owner_rows[GMAIL.connector_id]["changed_at"] = math.nan
        self.store.put(CONNECTOR_STATE_KEY, rows)
        with self.assertRaises(ConnectorContractError) as rejected:
            self.registry.require_connected("owner-a", GMAIL.connector_id, GMAIL.required_scopes)
        self.assertEqual(rejected.exception.reason, "invalid_stored_state")

        owner_rows[GMAIL.connector_id]["changed_at"] = self.now[0]
    def test_all_nonconnected_observed_health_pairs_fail_closed(self):
        observed = (
            {"state": "healthy", "checked_at": self.now[0], "recovery": None},
            {"state": "unavailable", "checked_at": self.now[0], "recovery": "review_access"},
        )
        for lifecycle in (
            ConnectorState.DISCONNECTED,
            ConnectorState.REAUTH_REQUIRED,
            ConnectorState.BLOCKED,
        ):
            for health in observed:
                with self.subTest(lifecycle=lifecycle, health=health["state"]):
                    self.registry.transition("owner-a", GMAIL.connector_id, lifecycle)
                    rows = self.store.config(CONNECTOR_STATE_KEY)
                    owner_rows = next(iter(rows.values()))
                    owner_rows[GMAIL.connector_id]["health"] = health
                    self.store.put(CONNECTOR_STATE_KEY, rows)
                    with self.assertRaises(ConnectorContractError) as rejected:
                        self.registry.status("owner-a", GMAIL.connector_id)
                    self.assertEqual(rejected.exception.reason, "invalid_stored_state")

    def test_connector_updates_are_serialized_across_registry_instances(self):
        class ProbeStore:
            def __init__(self):
                self.values = {}
                self.guard = threading.Lock()
                self.active = 0
                self.overlap = False

            def _enter(self):
                with self.guard:
                    self.active += 1
                    self.overlap = self.overlap or self.active > 1
                time.sleep(0.001)

            def _leave(self):
                with self.guard:
                    self.active -= 1

            def config(self, key, default=None):
                self._enter()
                try:
                    return copy.deepcopy(self.values[key]) if key in self.values else default
                finally:
                    self._leave()

            def put(self, key, value):
                self._enter()
                try:
                    self.values[key] = copy.deepcopy(value)
                finally:
                    self._leave()

        store = ProbeStore()
        first = ConnectorRegistry(store, (GMAIL, CALENDAR), clock=lambda: self.now[0])
        second = ConnectorRegistry(store, (GMAIL, CALENDAR), clock=lambda: self.now[0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(
                pool.map(
                    lambda operation: operation(),
                    (
                        lambda: first.transition(
                            "owner-a", GMAIL.connector_id, ConnectorState.CONNECTED,
                            granted_scopes=GMAIL.required_scopes,
                        ),
                        lambda: second.transition(
                            "owner-a", CALENDAR.connector_id, ConnectorState.CONNECTED,
                            granted_scopes=CALENDAR.required_scopes,
                        ),
                    ),
                )
            )
        self.assertFalse(store.overlap)
        self.assertEqual(first.status("owner-a", GMAIL.connector_id).state, ConnectorState.CONNECTED)
        self.assertEqual(second.status("owner-a", CALENDAR.connector_id).state, ConnectorState.CONNECTED)

    def test_malformed_top_level_connector_state_fails_closed_without_overwrite(self):
        for malformed in (None, [], "corrupt", 42, True):
            with self.subTest(malformed=malformed):
                self.store.put(CONNECTOR_STATE_KEY, malformed)
                operations = (
                    lambda: self.registry.status("owner-a", GMAIL.connector_id),
                    lambda: self.registry.transition(
                        "owner-a",
                        GMAIL.connector_id,
                        ConnectorState.CONNECTED,
                        granted_scopes=GMAIL.required_scopes,
                    ),
                    lambda: self.registry.record_health(
                        "owner-a",
                        GMAIL.connector_id,
                        HealthState.HEALTHY,
                        expected_revision=REVISION_1,
                    ),
                    lambda: self.registry.require_connected(
                        "owner-a", GMAIL.connector_id, GMAIL.required_scopes
                    ),
                )
                for operation in operations:
                    with self.assertRaises(ConnectorContractError) as rejected:
                        operation()
                    self.assertEqual(rejected.exception.reason, "invalid_stored_state")
                    self.assertEqual(self.store.config(CONNECTOR_STATE_KEY), malformed)

    def test_corrupt_pending_schema_work_reference_and_expiry_fail_closed(self):
        self.connect()
        corruptions = (
            ("work_id", "PRIVATE_PAYLOAD_WITH_UNDERSCORES"),
            ("work_id", "cHJpdmF0ZV9tYWlsX3JlcXVlc3Q"),
            ("expires_at", True),
            ("expires_at", math.nan),
            ("expires_at", math.inf),
            ("expires_at", "tomorrow"),
            ("state", "invented"),
            ("required_scopes", "gmail.readonly"),
            ("claimed_at", 1000.0),
            ("extra", "private"),
            ("sequence", 0),
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
                    self.pending.claim(
                        handle.token, "owner-a", GMAIL.connector_id, GMAIL.required_scopes, HANDOFF_1
                    )
                self.assertEqual(rejected.exception.reason, "invalid_resume")
                rows.pop(key)
                self.store.put(PENDING_WORK_KEY, rows)

    def test_malformed_top_level_pending_state_never_becomes_an_empty_registry(self):
        handle = self.pending.issue(
            "owner-a", WORK_1, GMAIL.connector_id, GMAIL.required_scopes
        )
        self.connect()
        for malformed in (None, [], "corrupt"):
            with self.subTest(malformed=malformed):
                self.store.put(PENDING_WORK_KEY, malformed)
                operations = (
                    lambda: self.pending.issue(
                        "owner-a", WORK_2, GMAIL.connector_id, GMAIL.required_scopes
                    ),
                    lambda: self.pending.claim(
                        handle.token,
                        "owner-a",
                        GMAIL.connector_id,
                        GMAIL.required_scopes,
                        HANDOFF_1,
                    ),
                    lambda: self.pending.complete(
                        handle.token, "owner-a", GMAIL.connector_id, HANDOFF_1
                    ),
                )
                for operation in operations:
                    with self.assertRaises(ConnectorContractError) as rejected:
                        operation()
                    self.assertEqual(rejected.exception.reason, "invalid_resume")
                    self.assertEqual(self.store.config(PENDING_WORK_KEY), malformed)

    def test_capability_compatibility_is_deterministic_and_disconnect_revokes(self):
        registry = CapabilityRegistry(self.store)
        ids = [item["id"] for item in registry.list()]
        self.assertEqual(ids, [item["id"] for item in registry.list()])
        self.assertTrue(all(item["grant"] == [] for item in registry.list()))
        registry.transition("google-drive-read", "enabled", ("read",))
        self.assertEqual(registry.transition("google-drive-read", "paused")["grant"], ["read"])
        self.assertEqual(registry.transition("google-drive-read", "disconnected")["grant"], [])

if __name__ == "__main__":
    unittest.main()
