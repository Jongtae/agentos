import tempfile
import unittest
from pathlib import Path
import shutil
import hashlib
import json
import threading

from personal_agent.calendar import (
    CALENDAR_CONNECTOR_ID,
    CALENDAR_SPEC,
    CALENDAR_WRITE_CONNECTOR_ID,
    CALENDAR_WRITE_SPEC,
    CalendarConnector,
    CalendarCreate,
    CalendarError,
)
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.google_calendar import (
    CALENDAR_READ_SCOPE,
    CALENDAR_WRITE_SCOPE,
    GoogleCalendarError,
)
from personal_agent.quickstart_store import QuickStore
from personal_agent.portable_state import export_owner_state, restore_owner_state


EVENT = {
    "summary": "review",
    "start": "2026-09-22T10:00:00+09:00",
    "end": "2026-09-22T11:00:00+09:00",
    "timezone": "Asia/Seoul",
    "description": "private agenda",
}


class Provider:
    def __init__(self):
        self.calls = []
        self.error = None

    def _result(self, name, *args):
        self.calls.append((name, *args))
        if self.error:
            raise self.error
        return {"id": args[0] if name != "create" else "new-event", "etag": '"v2"'}

    def query(self, *args):
        self.calls.append(("query", *args))
        if self.error:
            raise self.error
        return [{"id": "event-1", "etag": '"v1"', "summary": "review", "start": EVENT["start"], "end": EVENT["end"], "location": "", "status": "confirmed"}]

    def create(self, payload, key):
        return self._result("create", payload, key)

    def update(self, event_id, etag, payload):
        return self._result("update", event_id, etag, payload)

    def cancel(self, event_id, etag):
        result = self._result("cancel", event_id, etag)
        result["cancelled"] = True
        return result


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.provider = Provider()
        self.registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC))
        self.calendar = CalendarConnector(self.store, self.provider, registry=self.registry)
        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE,),
        )
        self.registry.transition(
            "owner",
            CALENDAR_WRITE_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_WRITE_SCOPE,),
        )

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, draft):
        return self.calendar.approve(draft["id"], "owner")["approval_id"]

    def test_query_requires_explicit_bounded_window_and_read_authority(self):
        result = self.calendar.query(
            "owner",
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
            max_results=25,
        )
        self.assertEqual(result["events"][0]["id"], "event-1")
        self.assertEqual(
            self.provider.calls,
            [("query", "2026-09-21T00:00:00+09:00", "2026-09-28T00:00:00+09:00", "Asia/Seoul", 25)],
        )
        self.assertNotIn("private agenda", str(result["evidence"]))
        with self.assertRaises(CalendarError):
            self.calendar.query("owner", "2026-01-01T00:00:00Z", "2028-01-01T00:00:00Z", "UTC")
        with self.assertRaises(CalendarError):
            self.calendar.query("owner", "2026-01-01T00:00:00", "2026-01-02T00:00:00", "UTC")

        disconnected = CalendarConnector(
            QuickStore(self.temp.name + "-other"),
            Provider(),
            registry=ConnectorRegistry(QuickStore(self.temp.name + "-other-registry"), (CALENDAR_SPEC,)),
        )
        with self.assertRaises(CalendarError) as denied:
            disconnected.query("owner", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "UTC")
        self.assertEqual(denied.exception.reason, "scope-denied")
        self.assertFalse(disconnected.provider.calls)

    def test_read_only_connection_can_query_but_cannot_mutate(self):
        store = QuickStore(self.temp.name + "-read-only")
        registry = ConnectorRegistry(store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC))
        provider = Provider()
        calendar = CalendarConnector(store, provider, registry=registry)
        registry.transition(
            "reader",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE,),
        )

        result = calendar.query(
            "reader",
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
        )
        self.assertEqual(result["evidence"]["result_count"], 1)
        draft = calendar.draft_create(EVENT, "reader")
        approval = calendar.approve(draft["id"], "reader")["approval_id"]
        with self.assertRaises(CalendarError) as denied:
            calendar.create(draft["id"], approval, "reader")
        self.assertEqual(
            (denied.exception.reason, denied.exception.effect, denied.exception.recovery),
            ("scope-denied", "none", "reconnect-and-request-new-draft"),
        )
        self.assertEqual(
            calendar.status(draft["id"], "reader")["recovery"],
            "reconnect-and-request-new-draft",
        )
        with self.assertRaises(CalendarError):
            calendar.approve(draft["id"], "reader")
        self.assertEqual(
            registry.status("reader", CALENDAR_WRITE_CONNECTOR_ID).state,
            ConnectorState.DISCONNECTED,
        )
        registry.transition(
            "reader",
            CALENDAR_WRITE_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_WRITE_SCOPE,),
        )
        replacement = calendar.draft_create(EVENT, "reader")
        replacement_approval = calendar.approve(replacement["id"], "reader")["approval_id"]
        self.assertEqual(calendar.create(replacement["id"], replacement_approval, "reader")["id"], "new-event")
        self.assertEqual([call[0] for call in provider.calls], ["query", "create"])
        self.assertEqual(
            registry.status("reader", CALENDAR_WRITE_CONNECTOR_ID).state,
            ConnectorState.CONNECTED,
        )

    def test_query_releases_global_authority_lock_during_provider_dispatch(self):
        observed = []
        original_query = self.provider.query

        def guarded_query(*args):
            observed.append(self.registry._lock._is_owned())
            return original_query(*args)

        self.provider.query = guarded_query
        self.calendar.query(
            "owner",
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
        )
        self.assertEqual(observed, [False])

    def test_query_discards_result_if_authority_changes_during_provider_call(self):
        original_query = self.provider.query

        def revoke_then_return(*args):
            self.registry.transition("owner", CALENDAR_CONNECTOR_ID, ConnectorState.DISCONNECTED)
            return original_query(*args)

        self.provider.query = revoke_then_return
        with self.assertRaises(CalendarError) as changed:
            self.calendar.query(
                "owner",
                "2026-09-21T00:00:00+09:00",
                "2026-09-28T00:00:00+09:00",
                "Asia/Seoul",
            )
        self.assertEqual(changed.exception.reason,"scope-denied")
        self.assertEqual(changed.exception.recovery,"reconnect")

    def test_query_dispatch_is_ordered_before_concurrent_revocation(self):
        authority_checked=threading.Event()
        allow_dispatch=threading.Event()
        transition_finished=threading.Event()
        original_authorize=self.calendar._authorize

        def paused_authorize(*args):
            snapshot=original_authorize(*args)
            authority_checked.set()
            self.assertTrue(allow_dispatch.wait(1))
            return snapshot

        self.calendar._authorize=paused_authorize
        query=threading.Thread(target=lambda:self.calendar.query(
            "owner","2026-09-21T00:00:00+09:00","2026-09-28T00:00:00+09:00","Asia/Seoul"))
        query.start();self.assertTrue(authority_checked.wait(1))

        def revoke():
            self.registry.transition("owner",CALENDAR_CONNECTOR_ID,ConnectorState.DISCONNECTED)
            transition_finished.set()

        revocation=threading.Thread(target=revoke);revocation.start()
        self.assertFalse(transition_finished.wait(.05))
        allow_dispatch.set();query.join(1);revocation.join(1)
        self.assertFalse(query.is_alive());self.assertFalse(revocation.is_alive())
        self.assertEqual([call[0] for call in self.provider.calls],["query"])
        self.assertTrue(transition_finished.is_set())

    def test_query_does_not_lease_unneeded_write_authority(self):
        provider_started=threading.Event();allow_provider=threading.Event()
        transition_finished=threading.Event();errors=[]
        original_query=self.provider.query

        def paused_query(*args):
            provider_started.set()
            if not allow_provider.wait(1): raise AssertionError("provider wait timed out")
            return original_query(*args)

        self.provider.query=paused_query
        query=threading.Thread(target=lambda:self.calendar.query(
            "owner","2026-09-21T00:00:00+09:00","2026-09-28T00:00:00+09:00","Asia/Seoul"))

        def disconnect_write():
            try:self.registry.transition("owner",CALENDAR_WRITE_CONNECTOR_ID,ConnectorState.DISCONNECTED)
            except Exception as error:errors.append(error)
            finally:transition_finished.set()

        query.start();self.assertTrue(provider_started.wait(1))
        transition=threading.Thread(target=disconnect_write);transition.start()
        self.assertTrue(transition_finished.wait(1))
        allow_provider.set();query.join(1);transition.join(1)
        self.assertFalse(query.is_alive());self.assertFalse(errors)
        self.assertEqual(self.registry.status("owner",CALENDAR_WRITE_CONNECTOR_ID).state,
                         ConnectorState.DISCONNECTED)

    def test_dispatch_locks_do_not_cross_owner_store_namespaces(self):
        other_store=QuickStore(self.temp.name+"-independent-runtime")
        other_registry=ConnectorRegistry(other_store,(CALENDAR_SPEC,CALENDAR_WRITE_SPEC))
        other_registry.transition("owner",CALENDAR_CONNECTOR_ID,ConnectorState.CONNECTED,
                                  granted_scopes=(CALENDAR_READ_SCOPE,))
        lease_started=threading.Event();release_lease=threading.Event();transition_finished=threading.Event()

        def hold_lease():
            with self.registry._dispatch_guard("owner",(CALENDAR_CONNECTOR_ID,)):
                lease_started.set();release_lease.wait(1)

        lease=threading.Thread(target=hold_lease);lease.start();self.assertTrue(lease_started.wait(1))
        transition=threading.Thread(target=lambda:(
            other_registry.transition("owner",CALENDAR_CONNECTOR_ID,ConnectorState.DISCONNECTED),
            transition_finished.set()))
        transition.start();self.assertTrue(transition_finished.wait(1))
        release_lease.set();lease.join(1);transition.join(1)
        self.assertFalse(lease.is_alive());self.assertFalse(transition.is_alive())

    def test_query_and_concurrent_scope_expiry_use_one_lock_order(self):
        provider_started=threading.Event();allow_provider=threading.Event()
        marker_finished=threading.Event();errors=[]
        original_query=self.provider.query

        def paused_query(*args):
            provider_started.set()
            if not allow_provider.wait(1): raise AssertionError("provider wait timed out")
            return original_query(*args)

        self.provider.query=paused_query
        snapshot=tuple(
            (connector_id,self.registry.status("owner",connector_id).connection_revision)
            for connector_id in (CALENDAR_CONNECTOR_ID,CALENDAR_WRITE_CONNECTOR_ID)
        )
        query=threading.Thread(target=lambda:self.calendar.query(
            "owner","2026-09-21T00:00:00+09:00","2026-09-28T00:00:00+09:00","Asia/Seoul"))

        def expire():
            try:self.calendar._mark_scope_expired("owner",snapshot)
            except Exception as error:errors.append(error)
            finally:marker_finished.set()

        query.start();self.assertTrue(provider_started.wait(1))
        marker=threading.Thread(target=expire);marker.start()
        self.assertFalse(marker_finished.wait(.05))
        allow_provider.set();query.join(1);marker.join(1)
        self.assertFalse(query.is_alive());self.assertFalse(marker.is_alive())
        self.assertFalse(errors);self.assertTrue(marker_finished.is_set())

    def test_create_exact_preview_one_time_approval_and_idempotency(self):
        draft = self.calendar.draft_create(EVENT, "owner")
        self.assertEqual(draft["action"], "create")
        self.assertEqual(draft["payload"], EVENT)
        self.assertFalse(self.provider.calls)
        with self.assertRaises(CalendarError):
            self.calendar.create(draft["id"], "not-approved", "owner")
        with self.assertRaises(CalendarError) as non_ascii:
            self.calendar.create(draft["id"], "승인", "owner")
        self.assertEqual(non_ascii.exception.reason, "exact-approval-required")
        self.assertFalse(self.provider.calls)

        approval = self.approve(draft)
        created = self.calendar.create(draft["id"], approval, "owner")
        self.assertEqual(created, {"id": "new-event", "summary": "review"})
        self.assertEqual(self.calendar.create(draft["id"], approval, "owner"), created)
        self.assertEqual(len(self.provider.calls), 1)

    def test_update_and_cancel_bind_exact_event_version_action_and_owner(self):
        update = self.calendar.draft_update("event/1", '"v1"', {"summary": "new title"}, "owner")
        cancel = self.calendar.draft_cancel("event-2", '"v7"', "owner")
        self.assertFalse(self.provider.calls)
        with self.assertRaises(CalendarError):
            self.calendar.preview(update["id"], "other")
        with self.assertRaises(CalendarError):
            self.calendar.cancel(update["id"], self.approve(update), "owner")
        self.assertFalse(self.provider.calls)

        # A new update draft is used because an approval is action-bound and
        # cannot be repurposed after the rejected action mismatch.
        update = self.calendar.draft_update("event/1", '"v1"', {"summary": "new title"}, "owner")
        updated = self.calendar.update(update["id"], self.approve(update), "owner")
        cancelled = self.calendar.cancel(cancel["id"], self.approve(cancel), "owner")
        self.assertEqual(updated, {"id": "event/1", "updated": True})
        self.assertEqual(cancelled, {"id": "event-2", "cancelled": True})
        self.assertEqual(self.provider.calls[0], ("update", "event/1", '"v1"', {"summary": "new title"}))
        self.assertEqual(self.provider.calls[1], ("cancel", "event-2", '"v7"'))

    def test_changed_payload_event_identity_and_foreign_owner_fail_before_call(self):
        draft = self.calendar.draft_update("event-1", '"v1"', {"summary": "new"}, "owner")
        approval = self.approve(draft)
        rows = self.calendar._rows()
        rows[draft["id"]]["event_id"] = "event-2"
        self.calendar._put(rows)
        with self.assertRaises(CalendarError) as changed:
            self.calendar.update(draft["id"], approval, "owner")
        self.assertEqual(
            (changed.exception.reason, changed.exception.recovery),
            ("payload-changed", "request-new-draft"),
        )
        self.assertEqual(self.calendar.status(draft["id"], "owner")["recovery"], "request-new-draft")
        self.assertFalse(self.provider.calls)

        foreign = self.calendar.draft_cancel("event-3", '"v1"', "owner")
        with self.assertRaises(CalendarError):
            self.calendar.approve(foreign["id"], "other")
        self.assertFalse(self.provider.calls)

    def test_attendees_recurrence_and_partial_time_changes_are_not_authorized(self):
        for payload in (
            {**EVENT, "attendees": [{"email": "person@example.test"}]},
            {**EVENT, "recurrence": ["RRULE:FREQ=DAILY"]},
            {**EVENT, "timezone": "Not/A-Timezone"},
            {"start": EVENT["start"]},
        ):
            with self.assertRaises(CalendarError):
                if "summary" in payload:
                    self.calendar.draft_create(payload, "owner")
                else:
                    self.calendar.draft_update("event", '"v1"', payload, "owner")
        self.assertFalse(self.provider.calls)

        with self.assertRaises(CalendarError):
            self.calendar.draft_create(
                {**EVENT, "start": "2026-09-22", "end": "2026-09-23"},
                "owner",
            )
        local = self.calendar.draft_create(
            {
                **EVENT,
                "start": "2026-09-22T10:00:00",
                "end": "2026-09-22T11:00:00",
            },
            "owner",
        )
        self.assertEqual(local["payload"]["start"], "2026-09-22T10:00:00")

    def test_expired_approval_scope_expiry_and_unknown_effect_are_truthful(self):
        clock = [0.0]
        calendar = CalendarConnector(
            self.store,
            self.provider,
            authority=lambda _owner, _scope: True,
            now=lambda: clock[0],
        )
        draft = calendar.draft_create(EVENT, "owner")
        approval = calendar.approve(draft["id"], "owner")["approval_id"]
        status_draft = calendar.draft_create(EVENT, "owner")
        calendar.approve(status_draft["id"], "owner")
        clock[0] = 900
        status = calendar.status(status_draft["id"], "owner")
        self.assertEqual((status["state"], status["recovery"]), ("expired", "request-new-draft"))
        with self.assertRaises(CalendarError) as expired:
            calendar.create(draft["id"], approval, "owner")
        self.assertEqual(expired.exception.reason, "approval-expired")
        self.assertEqual(calendar.status(draft["id"], "owner")["recovery"], "request-new-draft")
        self.assertFalse(self.provider.calls)

        self.provider.error = GoogleCalendarError("scope-expired")
        stale_scope = self.calendar.draft_cancel("event", '"v1"', "owner")
        with self.assertRaises(CalendarError) as scope:
            self.calendar.cancel(stale_scope["id"], self.approve(stale_scope), "owner")
        self.assertEqual(
            (scope.exception.reason, scope.exception.effect, scope.exception.recovery),
            ("scope-expired", "none", "reconnect-and-request-new-draft"),
        )
        self.assertEqual(
            (self.calendar.status(stale_scope["id"], "owner")["state"],
             self.calendar.status(stale_scope["id"], "owner")["recovery"]),
            ("failed", "reconnect-and-request-new-draft"),
        )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_WRITE_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )

        self.registry.transition(
            "owner",
            CALENDAR_WRITE_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_WRITE_SCOPE,),
        )
        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE,),
        )
        with self.assertRaises(CalendarError):
            self.calendar.query(
                "owner",
                "2026-09-21T00:00:00+09:00",
                "2026-09-28T00:00:00+09:00",
                "Asia/Seoul",
            )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_WRITE_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )
        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE,),
        )
        self.registry.transition(
            "owner",
            CALENDAR_WRITE_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_WRITE_SCOPE,),
        )
        self.provider.error = GoogleCalendarError("provider-timeout", "unknown")
        uncertain = self.calendar.draft_create(EVENT, "owner")
        uncertain_approval = self.approve(uncertain)
        with self.assertRaises(CalendarError) as timeout:
            self.calendar.create(uncertain["id"], uncertain_approval, "owner")
        status = self.calendar.status(uncertain["id"], "owner")
        self.assertEqual((timeout.exception.reason, status["state"], status["effect"]), ("provider-timeout", "outcome-unknown", "unknown"))
        with self.assertRaises(CalendarError):
            self.calendar.create(uncertain["id"], uncertain_approval, "owner")
        self.assertEqual(len([call for call in self.provider.calls if call[0] == "create"]), 1)

    def test_scope_expiry_does_not_revoke_a_newer_sibling_reconnect(self):
        read_before = self.registry.status("owner", CALENDAR_CONNECTOR_ID).connection_revision
        draft = self.calendar.draft_create(EVENT, "owner")
        approval = self.approve(draft)

        def rejected_after_read_reconnect(_payload, _key):
            self.registry.transition("owner", CALENDAR_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED)
            reconnected = self.registry.transition(
                "owner",
                CALENDAR_CONNECTOR_ID,
                ConnectorState.CONNECTED,
                granted_scopes=(CALENDAR_READ_SCOPE,),
            )
            self.assertNotEqual(reconnected.connection_revision, read_before)
            raise GoogleCalendarError("scope-expired")

        self.provider.create = rejected_after_read_reconnect
        with self.assertRaises(CalendarError) as rejected:
            self.calendar.create(draft["id"], approval, "owner")
        self.assertEqual(rejected.exception.reason, "scope-expired")
        self.assertEqual(
            self.registry.status("owner", CALENDAR_CONNECTOR_ID).state,
            ConnectorState.CONNECTED,
        )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_WRITE_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )

    def test_read_credential_rejection_blocks_later_write_before_provider_call(self):
        self.provider.error = GoogleCalendarError("scope-expired")
        with self.assertRaises(CalendarError):
            self.calendar.query(
                "owner",
                "2026-09-21T00:00:00+09:00",
                "2026-09-28T00:00:00+09:00",
                "Asia/Seoul",
            )
        draft = self.calendar.draft_cancel("event", '"v1"', "owner")
        approval = self.approve(draft)
        with self.assertRaises(CalendarError) as denied:
            self.calendar.cancel(draft["id"], approval, "owner")
        self.assertEqual(denied.exception.reason, "scope-expired")
        self.assertEqual([call[0] for call in self.provider.calls], ["query"])

    def test_event_version_rejects_header_controls_before_approval(self):
        for version in ('"v1"\r\nX-Injected: yes', '"v1"\x00', '"버전"', '*', '"v1", "v2"', 'unquoted', 'W/"v1"'):
            with self.subTest(version=version):
                with self.assertRaises(CalendarError) as rejected:
                    self.calendar.draft_cancel("event", version, "owner")
                self.assertEqual(rejected.exception.reason, "invalid-event-version")
        self.assertFalse(self.provider.calls)

    def test_portable_export_preserves_action_and_safe_failure_recovery(self):
        self.store.put(
            "calendar_create",
            {
                "completed-update": {
                    "id": "completed-update",
                    "state": "completed",
                    "hash": "redacted-hash",
                    "action": "update",
                    "result": {"id": "event-1", "updated": True},
                },
                "failed-scope": {
                    "id": "failed-scope",
                    "state": "failed",
                    "hash": "redacted-hash",
                    "action": "cancel",
                    "error_class": "scope-expired",
                    "recovery": "reconnect-and-request-new-draft",
                },
            },
        )
        root = Path(self.temp.name)
        archive = export_owner_state(root, root.with_name(root.name + "-calendar-owner.tar.gz"))
        restored_root = root.with_name(root.name + "-calendar-restored")
        self.addCleanup(shutil.rmtree, restored_root, True)
        self.addCleanup(lambda: archive.unlink(missing_ok=True))
        restored_store = QuickStore(restore_owner_state(archive, restored_root))
        restored = CalendarConnector(restored_store, self.provider, authority=lambda *_: False)
        completed = restored.status("completed-update", "restored-owner")
        failed = restored.status("failed-scope", "restored-owner")
        self.assertEqual((completed["state"], completed["action"]), ("completed", "update"))
        self.assertEqual(
            (failed["state"], failed["action"], failed["recovery"]),
            ("failed", "cancel", "reconnect-and-request-new-draft"),
        )

    def test_approval_expiring_while_waiting_for_authority_is_not_dispatched(self):
        clock = [1000.0]
        calendar = CalendarConnector(
            self.store,
            self.provider,
            registry=self.registry,
            now=lambda: clock[0],
            approval_ttl=1,
        )
        draft = calendar.draft_create(EVENT, "owner")
        approval = calendar.approve(draft["id"], "owner")["approval_id"]
        clock[0] = 1000.5
        original_authorize = calendar._authorize

        def delayed_authorize(owner, scope):
            result = original_authorize(owner, scope)
            clock[0] = 1001.0
            return result

        calendar._authorize = delayed_authorize
        with self.assertRaises(CalendarError) as expired:
            calendar.create(draft["id"], approval, "owner")
        self.assertEqual(
            (expired.exception.reason, expired.exception.recovery),
            ("approval-expired", "request-new-draft"),
        )
        self.assertEqual(
            (calendar.status(draft["id"], "owner")["state"],
             calendar.status(draft["id"], "owner")["recovery"]),
            ("expired", "request-new-draft"),
        )
        self.assertFalse(self.provider.calls)

    def test_status_and_stored_owner_are_redacted(self):
        draft = self.calendar.draft_create(EVENT, "owner-secret-id")
        status = self.calendar.status(draft["id"], "owner-secret-id")
        self.assertNotIn("private agenda", str(status))
        self.assertNotIn("owner-secret-id", str(self.calendar._rows()))
        self.assertNotIn("event_id", status)

        self.registry.transition(
            "owner-secret-id",
            CALENDAR_WRITE_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_WRITE_SCOPE,),
        )
        approval = self.calendar.approve(draft["id"], "owner-secret-id")["approval_id"]
        self.calendar.create(draft["id"], approval, "owner-secret-id")
        completed = self.calendar.status(draft["id"], "owner-secret-id")
        self.assertEqual(completed["result"], {"id": "new-event"})
        self.assertNotIn(EVENT["summary"], str(completed))
        self.assertNotIn(EVENT["description"], str(completed))

    def test_legacy_rows_migrate_raw_or_unbound_owner_without_losing_retry(self):
        for legacy_owner in ("owner", None):
            with self.subTest(legacy_owner=legacy_owner):
                ident = "legacy-" + (legacy_owner or "unbound")
                legacy_hash = "legacy-content-hash"
                self.store.put(
                    "calendar_create",
                    {
                        ident: {
                            "id": ident,
                            "payload": dict(EVENT),
                            "hash": legacy_hash,
                            "owner": legacy_owner,
                            "state": "created",
                            "approval": "legacy-approval",
                            "approval_hash": legacy_hash,
                            "expires": 9999999999,
                            "result": {"id": "legacy-event", "summary": EVENT["summary"]},
                        }
                    },
                )
                legacy = CalendarCreate(self.store, lambda *_: self.fail("legacy retry dispatched"))
                self.assertEqual(
                    legacy.create(ident, "legacy-approval", "owner"),
                    {"id": "legacy-event", "summary": EVENT["summary"]},
                )
                migrated = legacy._rows()[ident]
                self.assertNotEqual(migrated["owner"], "owner")
                self.assertEqual(migrated["action"], "create")
                self.assertEqual(legacy.status(ident, "owner")["result"], {"id": "legacy-event"})

        calls = []
        legacy_event_hash = hashlib.sha256(json.dumps(EVENT, sort_keys=True).encode()).hexdigest()
        self.store.put(
            "calendar_create",
            {
                "legacy-approved": {
                    "id": "legacy-approved",
                    "payload": dict(EVENT),
                    "hash": legacy_event_hash,
                    "owner": "owner",
                    "state": "approved",
                    "approval": "legacy-approval",
                    "approval_hash": legacy_event_hash,
                    "expires": 9999999999,
                }
            },
        )
        legacy = CalendarCreate(
            self.store,
            lambda *_: calls.append("create") or {"id": "migrated-event"},
        )
        self.assertEqual(
            legacy.create("legacy-approved", "legacy-approval", "owner")["id"],
            "migrated-event",
        )
        self.assertEqual(calls, ["create"])

        self.store.put(
            "calendar_create",
            {
                "legacy-unicode": {
                    "id": "legacy-unicode",
                    "payload": dict(EVENT),
                    "hash": "legacy-content-hash",
                    "owner": "소유자",
                    "state": "awaiting-approval",
                }
            },
        )
        unicode_legacy = CalendarCreate(self.store, lambda *_: {"id": "unused"})
        preview = unicode_legacy.preview("legacy-unicode", "소유자")
        self.assertEqual(preview["action"], "create")
        self.assertNotEqual(unicode_legacy._rows()["legacy-unicode"]["owner"], "소유자")

    def test_invalid_legacy_approved_payload_is_quarantined_before_provider_dispatch(self):
        for invalid_payload in (
            {**EVENT, "start": "a", "end": "b"},
            {**EVENT, "start": "2026-10-01", "end": "2026-10-02"},
        ):
            with self.subTest(payload=invalid_payload):
                self.store.put(
                    "calendar_create",
                    {
                        "legacy-invalid": {
                            "id": "legacy-invalid",
                            "payload": invalid_payload,
                            "hash": "legacy-content-hash",
                            "owner": "owner",
                            "state": "approved",
                            "approval": "legacy-approval",
                            "approval_hash": "legacy-content-hash",
                            "expires": 9999999999,
                        }
                    },
                )
                calls = []
                legacy = CalendarCreate(
                    self.store,
                    lambda *_: calls.append("create") or {"id": "must-not-dispatch"},
                )
                with self.assertRaises(CalendarError) as rejected:
                    legacy.create("legacy-invalid", "legacy-approval", "owner")
                self.assertEqual(rejected.exception.reason, "exact-approval-required")
                migrated = legacy._rows()["legacy-invalid"]
                self.assertEqual(migrated["state"], "expired")
                self.assertEqual(migrated["error_class"], "legacy-payload-invalid")
                self.assertEqual(migrated["recovery"], "request-new-draft")
                self.assertNotIn("approval", migrated)
                self.assertNotIn("approval_hash", migrated)
                self.assertEqual(calls, [])

    def test_changed_legacy_approved_payload_or_hash_is_quarantined_before_dispatch(self):
        original_hash = hashlib.sha256(json.dumps(EVENT, sort_keys=True).encode()).hexdigest()
        changed = {**EVENT, "summary": "changed after approval"}
        changed_hash = hashlib.sha256(json.dumps(changed, sort_keys=True).encode()).hexdigest()
        cases = (
            (changed, original_hash, original_hash),
            (dict(EVENT), original_hash, changed_hash),
        )
        for payload, stored_hash, approval_hash in cases:
            with self.subTest(payload=payload["summary"], approval_hash=approval_hash):
                self.store.put(
                    "calendar_create",
                    {
                        "legacy-changed": {
                            "id": "legacy-changed",
                            "payload": payload,
                            "hash": stored_hash,
                            "owner": "owner",
                            "state": "approved",
                            "approval": "legacy-approval",
                            "approval_hash": approval_hash,
                            "expires": 9999999999,
                        }
                    },
                )
                calls = []
                legacy = CalendarCreate(
                    self.store,
                    lambda *_: calls.append("create") or {"id": "must-not-dispatch"},
                )
                with self.assertRaises(CalendarError) as rejected:
                    legacy.create("legacy-changed", "legacy-approval", "owner")
                self.assertEqual(rejected.exception.reason, "exact-approval-required")
                migrated = legacy._rows()["legacy-changed"]
                self.assertEqual(
                    (migrated["state"], migrated["error_class"], migrated["recovery"]),
                    ("expired", "legacy-approval-mismatch", "request-new-draft"),
                )
                self.assertNotIn("approval", migrated)
                self.assertNotIn("approval_hash", migrated)
                self.assertEqual(calls, [])

    def test_legacy_scope_failure_without_recovery_reconstructs_actionable_path(self):
        self.store.put(
            "calendar_create",
            {
                "legacy-scope-denied": {
                    "id": "legacy-scope-denied",
                    "payload": dict(EVENT),
                    "hash": "legacy-content-hash",
                    "owner": "owner",
                    "state": "failed",
                    "error_class": "scope-denied",
                }
            },
        )
        legacy = CalendarCreate(self.store, lambda *_: self.fail("failed work must not dispatch"))
        status = legacy.status("legacy-scope-denied", "owner")
        self.assertEqual(
            (status["state"], status["effect"], status["recovery"]),
            ("failed", "none", "reconnect-and-request-new-draft"),
        )

    def test_legacy_post_dispatch_failures_migrate_to_unknown_effect(self):
        for error_class in ("transport-error", "malformed-response", "provider-timeout"):
            with self.subTest(error_class=error_class):
                self.store.put(
                    "calendar_create",
                    {
                        "legacy-failed": {
                            "id": "legacy-failed",
                            "payload": dict(EVENT),
                            "hash": "legacy-content-hash",
                            "owner": "owner",
                            "state": "failed",
                            "error_class": error_class,
                        }
                    },
                )
                legacy = CalendarCreate(self.store, lambda *_: self.fail("must not retry"))
                status = legacy.status("legacy-failed", "owner")
                self.assertEqual(status["state"], "outcome-unknown")
                self.assertEqual(status["effect"], "unknown")
                self.assertEqual(status["recovery"], "inspect-calendar-before-retry")

    def test_portable_terminal_calendar_evidence_remains_readable(self):
        self.store.put(
            "calendar_create",
            {
                "portable": {
                    "id": "portable",
                    "state": "created",
                    "hash": "redacted-hash",
                    "result": {"id": "event-1"},
                }
            },
        )
        restored = CalendarCreate(self.store, lambda *_: self.fail("portable evidence dispatched"))
        status = restored.status("portable", "restored-owner")
        self.assertEqual(status["state"], "created")
        self.assertEqual(status["action"], "unknown")
        self.assertEqual(status["result"], {"id": "event-1"})
        self.assertNotIn("restored-owner", str(restored._rows()))

        self.store.put(
            "calendar_create",
            {
                "in-flight": {
                    "id": "in-flight",
                    "state": "executing",
                    "hash": "redacted-hash",
                }
            },
        )
        uncertain = restored.status("in-flight", "restored-owner")
        self.assertEqual(uncertain["state"], "outcome-unknown")
        self.assertEqual(uncertain["effect"], "unknown")
        self.assertEqual(uncertain["recovery"], "inspect-calendar-before-retry")

        for error_class in ("transport-error", "malformed-response", "provider-timeout"):
            with self.subTest(portable_error=error_class):
                ident = "failed-" + error_class
                self.store.put(
                    "calendar_create",
                    {ident: {"id": ident, "state": "failed", "hash": "redacted-hash", "error_class": error_class}},
                )
                failed = restored.status(ident, "restored-owner")
                self.assertEqual(failed["state"], "outcome-unknown")
                self.assertEqual(failed["effect"], "unknown")
                self.assertEqual(failed["recovery"], "inspect-calendar-before-retry")

        for pending_state in ("awaiting-approval", "approved"):
            with self.subTest(pending_state=pending_state):
                ident = "pending-" + pending_state
                self.store.put(
                    "calendar_create",
                    {
                        ident: {
                            "id": ident,
                            "state": pending_state,
                            "hash": "redacted-hash",
                        }
                    },
                )
                quarantined = restored.status(ident, "restored-owner")
                self.assertEqual(quarantined["state"], "expired")
                self.assertEqual(quarantined["action"], "unknown")
                self.assertEqual(quarantined["error_class"], "restored-approval-quarantined")
                self.assertEqual(quarantined["recovery"], "request-new-draft")

    def test_write_authority_check_and_executing_commit_share_registry_guard(self):
        draft = self.calendar.draft_create(EVENT, "owner")
        approval = self.approve(draft)
        observations = []
        original_authorize = self.calendar._authorize

        def observed_authorize(owner, scope):
            observations.append(self.registry._lock._is_owned())
            return original_authorize(owner, scope)

        self.calendar._authorize = observed_authorize
        self.calendar.create(draft["id"], approval, "owner")
        self.assertEqual(observations, [True])

    def test_legacy_create_surface_remains_idempotent(self):
        calls = []
        legacy = CalendarCreate(
            self.store,
            lambda url, body, headers: calls.append((url, body, headers)) or {"id": "legacy-event"},
        )
        draft = legacy.draft(EVENT, "owner")
        approval = legacy.approve(draft["id"], "owner")
        self.assertEqual(legacy.create(draft["id"], approval["approval_id"], "owner")["id"], "legacy-event")
        legacy.create(draft["id"], approval["approval_id"], "owner")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
