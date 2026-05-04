from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.event_fabric.collectors import append_events_jsonl, process_exec_exit_events, ProcessSnapshot
from kernel.event_fabric.report import query_events, query_process_lineage, query_session_timeline
from kernel.event_fabric.schema import build_os_event_record


class EventFabricReportTests(unittest.TestCase):
    def test_query_events_returns_recent_records(self):
        events = process_exec_exit_events(
            {10: ProcessSnapshot(pid=10, ppid=1, comm="old", exe="/usr/bin/old")},
            {
                11: ProcessSnapshot(pid=11, ppid=1, comm="bash", exe="/bin/bash"),
            },
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_events(workspace, limit=1)

            self.assertTrue(report["ok"])
            self.assertEqual(report["total_events"], 2)
            self.assertEqual(report["returned_events"], 1)
            self.assertEqual(report["events"][0]["kind"], "process.exit")

    def test_query_events_filters_by_kind(self):
        events = process_exec_exit_events(
            {},
            {12: ProcessSnapshot(pid=12, ppid=1, comm="python3", exe="/usr/bin/python3")},
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_events(workspace, kind="process.exec", limit=5)

            self.assertEqual(report["matched_events"], 1)
            self.assertEqual(report["events"][0]["kind"], "process.exec")

    def test_query_events_filters_by_systemd_unit(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            events = [
                build_os_event_record(
                    source="journald",
                    kind="systemd.unit_state",
                    action="state_change",
                    object={"unit": "agentos-kernel.service", "state": "started", "state_family": "active"},
                    timestamp_utc="2026-04-14T00:00:01+00:00",
                ),
                build_os_event_record(
                    source="journald",
                    kind="systemd.unit_state",
                    action="state_change",
                    object={"unit": "agentos-eventd.service", "state": "failed", "state_family": "failed"},
                    timestamp_utc="2026-04-14T00:00:02+00:00",
                ),
            ]
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_events(workspace, kind="systemd.unit_state", unit="agentos-eventd.service", limit=10)

            self.assertEqual(report["matched_events"], 1)
            self.assertEqual(report["filter"]["unit"], "agentos-eventd.service")
            self.assertEqual(report["events"][0]["object"]["unit"], "agentos-eventd.service")

    def test_query_events_filters_by_source_and_reports_retention(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            events = [
                build_os_event_record(
                    source="journald",
                    kind="systemd.unit_state",
                    action="state_change",
                    object={"unit": "agentos-kernel.service", "state": "started"},
                    timestamp_utc="2026-04-14T00:00:01+00:00",
                ),
                build_os_event_record(
                    source="dbus",
                    kind="dbus.message",
                    action="message",
                    object={"path": "/org/freedesktop/login1", "interface": "org.freedesktop.login1.Manager", "member": "SessionNew"},
                    timestamp_utc="2026-04-14T00:00:02+00:00",
                ),
            ]
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_events(workspace, source="dbus", limit=10)

            self.assertEqual(report["matched_events"], 1)
            self.assertEqual(report["events"][0]["source"], "dbus")
            self.assertEqual(report["filter"]["source"], "dbus")
            self.assertGreater(report["retention"]["rotation_max_bytes"], 0)
            self.assertGreaterEqual(report["retention"]["active_bytes_remaining"], 0)

    def test_query_events_handles_missing_event_file(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()

            report = query_events(workspace, limit=5)

            self.assertTrue(report["ok"])
            self.assertFalse(report["event_file_exists"])
            self.assertEqual(report["events"], [])

    def test_query_process_lineage_reconstructs_parent_child_relationships(self):
        events = process_exec_exit_events(
            {10: ProcessSnapshot(pid=10, ppid=1, comm="root", exe="/sbin/init")},
            {
                11: ProcessSnapshot(pid=11, ppid=1, comm="bash", exe="/bin/bash"),
                12: ProcessSnapshot(pid=12, ppid=11, comm="python3", exe="/usr/bin/python3"),
            },
            correlation={"request_id": "req-1"},
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_process_lineage(
                workspace,
                correlation_key="request_id",
                correlation_value="req-1",
                limit=10,
            )

            self.assertTrue(report["ok"])
            self.assertEqual(report["matched_process_events"], 3)
            self.assertEqual(report["root_pids"], [11])
            nodes = {node["pid"]: node for node in report["nodes"]}
            self.assertEqual(nodes[11]["children"], [12])
            self.assertEqual(nodes[12]["ppid"], 11)

    def test_query_session_timeline_returns_ordered_session_events(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            events = [
                build_os_event_record(
                    source="journald",
                    kind="session.login",
                    action="login",
                    object={"session_id": "8", "user_name": "agentos"},
                    correlation={"session_id": "8", "boot_id": "boot-1", "session_origin": "local_managed_tty1"},
                    timestamp_utc="2026-04-14T00:00:01+00:00",
                ),
                build_os_event_record(
                    source="journald",
                    kind="systemd.unit_state",
                    action="state_change",
                    object={
                        "unit": "agentos-kernel.service",
                        "state": "started",
                        "state_family": "active",
                        "session_id": "8",
                    },
                    correlation={"session_id": "8", "boot_id": "boot-1", "next_managed_entry": "ai_shell", "banner_version": "phase49-v1"},
                    timestamp_utc="2026-04-14T00:00:02+00:00",
                ),
                build_os_event_record(
                    source="journald",
                    kind="session.logout",
                    action="logout",
                    object={"session_id": "8"},
                    correlation={"session_id": "8"},
                    timestamp_utc="2026-04-14T00:00:03+00:00",
                ),
            ]
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)

            report = query_session_timeline(workspace, session_id="8", limit=10)

            self.assertTrue(report["ok"])
            self.assertEqual(report["matched_events"], 3)
            self.assertEqual(
                [item["kind"] for item in report["timeline"]],
                ["session.login", "systemd.unit_state", "session.logout"],
            )
            self.assertEqual(report["timeline"][1]["summary"], "agentos-kernel.service started [active]")
            self.assertEqual(report["ownership_summary"]["session_phase"], "ai_shell")
            self.assertEqual(report["ownership_summary"]["session_origin"], "local_managed_tty1")
            self.assertEqual(report["ownership_summary"]["boot_id"], "boot-1")
            self.assertEqual(report["correlation_evidence"]["boot_ids"], ["boot-1"])


if __name__ == "__main__":
    unittest.main()
