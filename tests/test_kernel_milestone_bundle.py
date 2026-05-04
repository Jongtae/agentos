from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_milestone_bundle import build_milestone_bundle


class KernelMilestoneBundleTests(unittest.TestCase):
    def test_build_milestone_bundle_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            report_dir = root / "reports"
            history = root / "history"
            policy_dir = workspace / "artifacts" / "kernel-policy"
            policy_dir.mkdir(parents=True, exist_ok=True)
            history.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "milestone-bundle-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (workspace / "artifacts" / "runtime_trace.jsonl").write_text(
                json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "event": "run_start", "payload": {}}) + "\n",
                encoding="utf-8",
            )
            (workspace / "artifacts" / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "source": "journald", "kind": "session.login", "actor": {"uid": 1000}, "object": {"session_id": "agentos:tty1"}, "action": "login", "decision": {"state": "observed"}, "correlation": {"session_id": "agentos:tty1", "session_origin": "local_managed_tty1", "next_managed_entry": "ai_shell"}, "raw_ref": {"collector": "journald"}}),
                        json.dumps({"timestamp_utc": "2026-04-14T00:00:01+00:00", "source": "broker", "kind": "broker.approval_request", "actor": {"component": "agentos-runtime"}, "object": {"tool_name": "bash", "policy_target": "destructive_action_approval"}, "action": "approval_gate", "decision": {"state": "requested", "request_kind": "approval"}, "correlation": {"approval_id": "approval:req-1", "request_id": "req-1", "session_id": "agentos:tty1"}, "raw_ref": {"component": "broker"}}),
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
                json.dumps({"enabled": True, "policy_target": "destructive_action_approval"}) + "\n",
                encoding="utf-8",
            )
            (history / "window-1.json").write_text(
                json.dumps({"schema_version": "agentos-validation-window.v1", "label": "window-1", "generated_at_utc": "2026-04-13T00:00:00Z", "summary": {"runtime_ok": True, "session_phase": "ai_shell", "session_origin": "local_managed_tty1", "install_validation_ok": True, "audit_ok": True, "diagnostics_ok": True, "diagnostics_readiness_status": "ready", "approval_forensic_status": "requested", "policy_targets": {"destructive_action_approval": "candidate"}, "overall_state": "ready"}}) + "\n",
                encoding="utf-8",
            )

            payload = build_milestone_bundle(
                workspace=str(workspace),
                report_dir=str(report_dir),
                history_dir=str(history),
                snapshot_label="preview",
                session_id="agentos:tty1",
            )
            self.assertEqual(payload["schema_version"], "agentos-public-milestone-bundle.v1")
            milestone_dir = Path(payload["milestone_dir"])
            self.assertTrue((milestone_dir / "milestone-note.md").exists())
            self.assertTrue((milestone_dir / "milestone-manifest.json").exists())
            self.assertTrue((milestone_dir / "references").exists())
            self.assertTrue((Path(payload["artifacts"]["review_bundle_dir"]) / "review-pack.json").exists())
            self.assertTrue((Path(payload["milestone_root"]) / "latest-milestone-manifest.json").exists())
            self.assertGreaterEqual(len(payload["references"]), 4)


if __name__ == "__main__":
    unittest.main()
