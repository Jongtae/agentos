from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_control_history import build_control_history


class KernelControlHistoryTests(unittest.TestCase):
    def test_build_control_history_tracks_bridge_enforce_and_override_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            policy_dir = artifacts / "kernel-policy"
            policy_dir.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "control-history-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
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
                                "correlation": {"session_id": "agentos:tty1", "session_origin": "local_managed_tty1", "next_managed_entry": "ai_shell"},
                                "raw_ref": {"collector": "journald"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-14T00:00:01+00:00",
                                "source": "broker",
                                "kind": "broker.exec_decision",
                                "actor": {"component": "kernel_policy_bridge.py"},
                                "object": {"workspace_root": "./"},
                                "action": "policy_bridge_reload",
                                "decision": {"state": "allowed", "request_kind": "operator_control", "reason": "profile reload succeeded"},
                                "correlation": {"session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-14T00:00:02+00:00",
                                "source": "broker",
                                "kind": "broker.exec_decision",
                                "actor": {"component": "kernel_policy_enforced_pilot.py"},
                                "object": {"policy_target": "network_allowlist"},
                                "action": "policy_enforce_enable",
                                "decision": {"state": "allowed", "request_kind": "operator_control", "reason": "kernel ready"},
                                "correlation": {"session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-14T00:00:03+00:00",
                                "source": "broker",
                                "kind": "broker.exec_decision",
                                "actor": {"component": "install_kernel_boot_integration.sh"},
                                "object": {"status": "override_active"},
                                "action": "emergency_recovery",
                                "decision": {"state": "override", "request_kind": "override", "reason": "operator forced recovery bypass"},
                                "correlation": {"session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (policy_dir / "profile-lifecycle.json").write_text(
                json.dumps({"bridge_state": "reloaded", "reload_state": "applied", "disable_state": "inactive", "operator_state": "ready"}) + "\n",
                encoding="utf-8",
            )
            (policy_dir / "enforced-pilot.json").write_text(
                json.dumps({"enabled": True, "policy_target": "network_allowlist"}) + "\n",
                encoding="utf-8",
            )

            payload = build_control_history(workspace=str(workspace), limit=20)
            self.assertEqual(payload["schema_version"], "agentos-control-history.v1")
            self.assertIn("bridge", payload["summary"]["categories"])
            self.assertIn("override", payload["summary"]["categories"])
            self.assertEqual(payload["current_state"]["bridge_state"], "reloaded")
            self.assertEqual(payload["current_state"]["enforce_policy_target"], "network_allowlist")
            self.assertEqual(len(payload["timeline"]), 4)


if __name__ == "__main__":
    unittest.main()
