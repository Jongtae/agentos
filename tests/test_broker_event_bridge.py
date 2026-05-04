from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.broker import (
    append_broker_events,
    append_broker_transition,
    broker_decision_event,
    broker_request_event,
)
from kernel.broker.schema import build_broker_decision, build_broker_request
from kernel.event_fabric.report import query_events


class BrokerEventBridgeTests(unittest.TestCase):
    def test_broker_request_event_maps_exec_kind(self):
        request = build_broker_request(kind="exec", action="managed_exec", actor={"component": "test"})
        event = broker_request_event(request)
        self.assertEqual(event.kind, "broker.exec_request")
        self.assertEqual(event.source, "broker")

    def test_broker_decision_event_maps_approval_kind(self):
        decision = build_broker_decision(state="denied", reason="no", actor={"component": "test"})
        event = broker_decision_event(decision, request_kind="approval")
        self.assertEqual(event.kind, "broker.approval_decision")
        self.assertEqual(event.decision["state"], "denied")

    def test_append_broker_events_writes_queryable_os_events(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            request = build_broker_request(
                kind="approval",
                action="approval_gate",
                actor={"component": "test"},
                correlation={"request_id": "req-1", "approval_id": "ap-1"},
            )
            decision = build_broker_decision(
                state="approved",
                reason="ok",
                actor={"component": "test"},
                correlation=request.correlation,
            )
            written = append_broker_events(workspace, request=request, decision=decision, request_kind="approval")
            self.assertEqual(written, 2)
            report = query_events(workspace, kind="broker.approval_decision", limit=5)
            self.assertEqual(report["returned_events"], 1)

    def test_append_broker_transition_supports_session_entry(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            written = append_broker_transition(
                workspace,
                kind="session_entry",
                action="tty1_autostart",
                state="allowed",
                reason="managed tty1 session entry",
                actor={"component": "agentos-profile"},
                object={"tty": "/dev/tty1"},
                correlation={"session_id": "user:tty1"},
            )
            self.assertEqual(written, 2)
            report = query_events(workspace, kind="broker.exec_request", limit=5)
            self.assertEqual(report["returned_events"], 1)

    def test_append_broker_transition_supports_override_kind(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            written = append_broker_transition(
                workspace,
                kind="override",
                action="emergency_recovery",
                state="override",
                reason="operator forced bypass",
                actor={"component": "agentos-profile"},
                object={"status": "override_active"},
            )
            self.assertEqual(written, 2)
            report = query_events(workspace, kind="broker.exec_decision", limit=5)
            self.assertEqual(report["returned_events"], 1)
            self.assertEqual(report["events"][0]["decision"]["request_kind"], "override")


if __name__ == "__main__":
    unittest.main()
