from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kernel.event_fabric.collectors import (
    ProcessSnapshot,
    append_events_jsonl,
    dbus_message_event,
    file_access_candidate_event,
    is_allowlisted_host,
    is_outside_workspace,
    journald_systemd_logind_event,
    network_connect_candidate_event,
    process_exec_exit_events,
)
from kernel.event_fabric.schema import validate_os_event_payload


class EventFabricCollectorTests(unittest.TestCase):
    def test_process_exec_exit_events_emit_expected_kinds(self):
        previous = {
            10: ProcessSnapshot(pid=10, ppid=1, comm="old", exe="/usr/bin/old"),
            20: ProcessSnapshot(pid=20, ppid=1, comm="stay", exe="/usr/bin/stay"),
        }
        current = {
            20: ProcessSnapshot(pid=20, ppid=1, comm="stay", exe="/usr/bin/stay"),
            30: ProcessSnapshot(pid=30, ppid=20, comm="new", exe="/usr/bin/new"),
        }

        events = process_exec_exit_events(previous, current, correlation={"session_id": "s1"})
        self.assertEqual([item.kind for item in events], ["process.exec", "process.exit"])
        self.assertEqual(events[0].actor["pid"], 30)
        self.assertEqual(events[1].actor["pid"], 10)

    def test_process_exec_exit_events_validate_against_schema(self):
        previous = {}
        current = {
            42: ProcessSnapshot(pid=42, ppid=1, comm="python3", exe="/usr/bin/python3"),
        }
        events = process_exec_exit_events(previous, current)
        ok, reason = validate_os_event_payload(events[0].to_dict())
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_append_events_jsonl_writes_records(self):
        events = process_exec_exit_events(
            {},
            {7: ProcessSnapshot(pid=7, ppid=1, comm="bash", exe="/bin/bash")},
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "artifacts" / "os_events.jsonl"
            written = append_events_jsonl(out, events)
            self.assertEqual(written, 1)
            payload = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["kind"], "process.exec")
            self.assertEqual(payload["action"], "exec")

    def test_append_events_jsonl_rotates_existing_log_when_threshold_is_exceeded(self):
        events = process_exec_exit_events(
            {},
            {7: ProcessSnapshot(pid=7, ppid=1, comm="bash", exe="/bin/bash")},
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "artifacts" / "os_events.jsonl"
            archive = Path(td) / "artifacts" / "os_events.jsonl.1"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text('{"kind":"legacy"}\n', encoding="utf-8")

            written = append_events_jsonl(out, events, max_bytes=20, archive_path=archive)

            self.assertEqual(written, 1)
            self.assertTrue(archive.exists())
            self.assertIn('"kind":"legacy"', archive.read_text(encoding="utf-8"))
            payload = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["kind"], "process.exec")

    def test_is_outside_workspace_detects_escape_path(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "ws"
            workspace.mkdir()
            self.assertTrue(is_outside_workspace("../outside.txt", str(workspace)))
            self.assertFalse(is_outside_workspace("./inside.txt", str(workspace)))

    def test_file_access_candidate_event_returns_normalized_event_for_escape(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "ws"
            workspace.mkdir()
            event = file_access_candidate_event(
                candidate_path="../outside.txt",
                action="read",
                workspace_root=str(workspace),
                actor={"pid": 55, "comm": "cat"},
                correlation={"session_id": "s2"},
            )
            self.assertIsNotNone(event)
            payload = event.to_dict()
            self.assertEqual(payload["kind"], "file.outside_workspace_candidate")
            self.assertEqual(payload["decision"]["policy_target"], "fs_workspace_boundary")
            ok, reason = validate_os_event_payload(payload)
            self.assertTrue(ok)
            self.assertEqual(reason, "ok")

    def test_file_access_candidate_event_ignores_inside_workspace_paths(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "ws"
            workspace.mkdir()
            event = file_access_candidate_event(
                candidate_path="./inside.txt",
                action="read",
                workspace_root=str(workspace),
            )
            self.assertIsNone(event)

    def test_is_allowlisted_host_supports_exact_and_subdomain_matches(self):
        allowlist = ["openai.com", "github.com"]
        self.assertTrue(is_allowlisted_host("openai.com", allowlist))
        self.assertTrue(is_allowlisted_host("api.openai.com", allowlist))
        self.assertFalse(is_allowlisted_host("evil.com", allowlist))

    def test_network_connect_candidate_event_returns_normalized_event_when_outside_allowlist(self):
        event = network_connect_candidate_event(
            host="evil.com",
            port=443,
            allowlist=["openai.com", "github.com"],
            actor={"pid": 88, "comm": "curl"},
            correlation={"session_id": "s3"},
        )
        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "network.connect_candidate")
        self.assertEqual(payload["decision"]["policy_target"], "network_allowlist")
        ok, reason = validate_os_event_payload(payload)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_network_connect_candidate_event_ignores_allowlisted_host(self):
        event = network_connect_candidate_event(
            host="api.openai.com",
            port=443,
            allowlist=["openai.com"],
        )
        self.assertIsNone(event)

    def test_journald_systemd_logind_event_normalizes_systemd_unit_state(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:systemd:1",
                "_PID": "1",
                "_UID": "0",
                "_COMM": "systemd",
                "_EXE": "/usr/lib/systemd/systemd",
                "_SYSTEMD_UNIT": "nginx.service",
                "MESSAGE": "Started nginx.service - A high performance web server.",
            }
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "systemd.unit_state")
        self.assertEqual(payload["action"], "state_change")
        self.assertEqual(payload["object"]["unit"], "nginx.service")
        self.assertEqual(payload["object"]["state"], "started")
        self.assertEqual(payload["object"]["state_family"], "active")
        self.assertEqual(payload["object"]["unit_type"], "service")
        self.assertEqual(payload["raw_ref"]["cursor"], "cursor:systemd:1")

    def test_journald_systemd_logind_event_extracts_unit_name_and_reloading_state_from_message(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:systemd:reload",
                "_PID": "1",
                "_UID": "0",
                "_COMM": "systemd",
                "_EXE": "/usr/lib/systemd/systemd",
                "MESSAGE": "Reloading agentos-kernel.service - AgentOS Managed Shell Bootstrap Service.",
            }
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "systemd.unit_state")
        self.assertEqual(payload["object"]["unit"], "agentos-kernel.service")
        self.assertEqual(payload["object"]["state"], "reloading")
        self.assertEqual(payload["object"]["state_family"], "transitional")
        self.assertEqual(payload["object"]["unit_type"], "service")

    def test_journald_systemd_logind_event_normalizes_dependency_failure(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:systemd:dependency",
                "_PID": "1",
                "_UID": "0",
                "_COMM": "systemd",
                "_EXE": "/usr/lib/systemd/systemd",
                "MESSAGE": "Dependency failed for agentos-eventd.service - AgentOS Event Fabric.",
            }
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["object"]["unit"], "agentos-eventd.service")
        self.assertEqual(payload["object"]["state"], "dependency_failed")
        self.assertEqual(payload["object"]["state_family"], "failed")

    def test_journald_systemd_logind_event_normalizes_session_login(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:logind:login",
                "SYSLOG_IDENTIFIER": "systemd-logind",
                "_PID": "777",
                "_UID": "0",
                "_COMM": "systemd-logind",
                "SESSION_ID": "8",
                "USER_ID": "1000",
                "USER_NAME": "agentos",
                "MESSAGE": "New session 8 of user agentos.",
            }
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "session.login")
        self.assertEqual(payload["action"], "login")
        self.assertEqual(payload["object"]["session_id"], "8")
        self.assertEqual(payload["object"]["user_name"], "agentos")

    def test_journald_systemd_logind_event_normalizes_session_logout(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:logind:logout",
                "SYSLOG_IDENTIFIER": "systemd-logind",
                "_PID": "777",
                "_UID": "0",
                "_COMM": "systemd-logind",
                "MESSAGE": "Removed session 8.",
            }
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "session.logout")
        self.assertEqual(payload["action"], "logout")
        self.assertEqual(payload["object"]["session_id"], "8")

    def test_journald_systemd_logind_event_ignores_unmapped_entries(self):
        event = journald_systemd_logind_event(
            {
                "__CURSOR": "cursor:noop",
                "SYSLOG_IDENTIFIER": "unrelated-daemon",
                "MESSAGE": "Background task completed.",
            }
        )
        self.assertIsNone(event)

    def test_dbus_message_event_normalizes_message_observation(self):
        event = dbus_message_event(
            bus="system",
            path="/org/freedesktop/login1",
            interface="org.freedesktop.login1.Manager",
            member="SessionNew",
            message_type="signal",
            sender="org.freedesktop.login1",
            destination="",
            body={"session_id": "8", "user_id": 1000},
            raw_ref={"message_index": 1},
            correlation={"session_id": "8"},
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["kind"], "dbus.message")
        self.assertEqual(payload["action"], "message")
        self.assertEqual(payload["object"]["interface"], "org.freedesktop.login1.Manager")
        self.assertEqual(payload["object"]["member"], "SessionNew")
        self.assertEqual(payload["object"]["message_type"], "signal")
        self.assertEqual(payload["object"]["message_class"], "logind.session_lifecycle")
        self.assertEqual(payload["raw_ref"]["collector"], "dbus_monitor")
        ok, reason = validate_os_event_payload(payload)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_dbus_message_event_classifies_systemd_unit_lifecycle_messages(self):
        event = dbus_message_event(
            bus="system",
            path="/org/freedesktop/systemd1/unit/agentos_2deventd_2eservice",
            interface="org.freedesktop.systemd1.Unit",
            member="PropertiesChanged",
            message_type="signal",
            sender="org.freedesktop.systemd1",
        )

        self.assertIsNotNone(event)
        payload = event.to_dict()
        self.assertEqual(payload["object"]["message_class"], "systemd.unit_lifecycle")

    def test_dbus_message_event_rejects_missing_identity_fields(self):
        event = dbus_message_event(
            bus="system",
            path="",
            interface="org.freedesktop.systemd1.Manager",
            member="JobRemoved",
            message_type="signal",
        )
        self.assertIsNone(event)


if __name__ == "__main__":
    unittest.main()
