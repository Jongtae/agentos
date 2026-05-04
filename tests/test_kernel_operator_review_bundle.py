from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_operator_review_bundle import build_review_bundle


class KernelOperatorReviewBundleTests(unittest.TestCase):
    def test_build_review_bundle_writes_expected_bundle_layout(self) -> None:
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
                        "name": "review-bundle-test",
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

            payload = build_review_bundle(
                workspace=str(workspace),
                report_dir=str(report_dir),
                history_dir=str(history),
                snapshot_label="smoke",
                session_id="agentos:tty1",
            )
            self.assertEqual(payload["schema_version"], "agentos-operator-review-bundle.v1")
            self.assertEqual(Path(payload["bundle_root"]), (report_dir / "review-bundles").resolve())
            bundle_dir = Path(payload["bundle_dir"])
            self.assertTrue((bundle_dir / "review-pack.json").exists())
            self.assertTrue((bundle_dir / "review-packet.md").exists())
            self.assertTrue((bundle_dir / "bundle-manifest.json").exists())
            self.assertTrue((report_dir / "review-bundles" / "latest-bundle-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
