from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_validation_window import build_validation_window


class KernelValidationWindowTests(unittest.TestCase):
    def test_build_validation_window_compares_history_against_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            history = root / "history"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            history.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "validation-window-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (artifacts / "runtime_trace.jsonl").write_text(
                json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "event": "run_start", "payload": {}}) + "\n",
                encoding="utf-8",
            )
            (artifacts / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-14T00:00:00+00:00",
                                "source": "journald",
                                "kind": "session.login",
                                "actor": {"uid": 1000},
                                "object": {"session_id": "agentos:tty1"},
                                "action": "login",
                                "decision": {"state": "observed"},
                                "correlation": {
                                    "session_id": "agentos:tty1",
                                    "boot_id": "boot-1",
                                    "session_origin": "local_managed_tty1",
                                    "next_managed_entry": "ai_shell",
                                },
                                "raw_ref": {"collector": "journald"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-14T00:00:01+00:00",
                                "source": "broker",
                                "kind": "broker.approval_request",
                                "actor": {"component": "agentos-runtime"},
                                "object": {"tool_name": "bash", "policy_target": "destructive_action_approval"},
                                "action": "approval_gate",
                                "decision": {"state": "requested", "request_kind": "approval"},
                                "correlation": {"approval_id": "approval:req-1", "request_id": "req-1", "session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (history / "window-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-validation-window.v1",
                        "label": "window-1",
                        "generated_at_utc": "2026-04-13T00:00:00Z",
                        "summary": {
                            "runtime_ok": True,
                            "session_phase": "setup_session",
                            "session_origin": "local_managed_tty1",
                            "install_validation_ok": False,
                            "audit_ok": None,
                            "diagnostics_ok": None,
                            "diagnostics_readiness_status": "",
                            "approval_forensic_status": "pending",
                            "policy_targets": {"destructive_action_approval": "candidate"},
                            "overall_state": "policy_drift",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_validation_window(
                workspace=str(workspace),
                history_dir=str(history),
                snapshot_label="window-2",
            )
            self.assertEqual(payload["schema_version"], "agentos-validation-window.v1")
            self.assertEqual(payload["summary"]["history_count"], 1)
            self.assertFalse(payload["summary"]["stable"])
            self.assertIn("session_phase", payload["summary"]["changed_fields"])
            self.assertIn("policy_targets", payload["summary"]["changed_fields"])


if __name__ == "__main__":
    unittest.main()
