from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.event_fabric.schema import (
    DEFAULT_OS_EVENT_LOG_FILENAME,
    DEFAULT_OS_EVENT_LOG_MAX_BYTES,
    OS_EVENT_REQUIRED_FIELDS,
    build_os_event_record,
    os_event_archive_path,
    os_event_log_path,
    os_event_storage_contract,
    validate_os_event_payload,
)


class EventFabricSchemaTests(unittest.TestCase):
    def test_build_os_event_record_contains_required_fields(self):
        event = build_os_event_record(
            source="runtime",
            kind="process.exec",
            actor={"pid": 1234, "exe": "/usr/bin/python3"},
            object={"path": "/tmp/example.txt"},
            action="exec",
            decision={"state": "observed"},
            correlation={"session_id": "s1"},
            raw_ref={"collector": "unit-test"},
        ).to_dict()

        for key in OS_EVENT_REQUIRED_FIELDS:
            self.assertIn(key, event)

    def test_validate_os_event_payload_accepts_complete_payload(self):
        event = build_os_event_record(
            source="ebpf",
            kind="network.connect_candidate",
            actor={"pid": 222, "comm": "curl"},
            object={"host": "example.com", "port": 443},
            action="connect",
            decision={"state": "candidate"},
            correlation={"request_id": "req-1"},
            raw_ref={"collector": "ebpf-tracepoint", "offset": 1},
        ).to_dict()
        ok, reason = validate_os_event_payload(event)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_validate_os_event_payload_rejects_missing_required_field(self):
        event = build_os_event_record(
            source="journald",
            kind="systemd.unit_state",
            actor={"unit": "agentos-eventd.service"},
            object={"state": "active"},
            action="state_change",
            decision={"state": "observed"},
            correlation={},
            raw_ref={"cursor": "abc"},
        ).to_dict()
        del event["raw_ref"]

        ok, reason = validate_os_event_payload(event)
        self.assertFalse(ok)
        self.assertIn("missing required field: raw_ref", reason)

    def test_storage_contract_uses_workspace_artifacts_path(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            active = os_event_log_path(workspace)
            archive = os_event_archive_path(workspace)
            contract = os_event_storage_contract(workspace)

            self.assertEqual(active, workspace / "artifacts" / DEFAULT_OS_EVENT_LOG_FILENAME)
            self.assertEqual(archive, workspace / "artifacts" / f"{DEFAULT_OS_EVENT_LOG_FILENAME}.1")
            self.assertEqual(contract["format"], "jsonl")
            self.assertEqual(contract["rotation_trigger"]["max_bytes"], DEFAULT_OS_EVENT_LOG_MAX_BYTES)
            self.assertEqual(contract["archive_retention"]["keep_archives"], 1)


if __name__ == "__main__":
    unittest.main()
