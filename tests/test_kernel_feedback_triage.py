from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_feedback_triage import build_feedback_triage, validate_feedback_triage


class KernelFeedbackTriageTests(unittest.TestCase):
    def test_build_feedback_triage_writes_expected_layout(self) -> None:
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
                        "name": "feedback-triage-test",
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
                json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "source": "journald", "kind": "session.login", "actor": {"uid": 1000}, "object": {"session_id": "agentos:tty1"}, "action": "login", "decision": {"state": "observed"}, "correlation": {"session_id": "agentos:tty1", "session_origin": "live_appliance_boot", "next_managed_entry": "ai_shell"}, "raw_ref": {"collector": "journald"}})
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
                json.dumps({"schema_version": "agentos-validation-window.v1", "label": "window-1", "generated_at_utc": "2026-04-13T00:00:00Z", "summary": {"runtime_ok": True, "session_phase": "ai_shell", "session_origin": "live_appliance_boot", "install_validation_ok": True, "audit_ok": True, "diagnostics_ok": True, "diagnostics_readiness_status": "ready", "approval_forensic_status": "requested", "policy_targets": {"destructive_action_approval": "candidate"}, "overall_state": "ready"}})
                + "\n",
                encoding="utf-8",
            )
            feedback_file = root / "feedback.json"
            feedback_file.write_text(
                json.dumps(
                    {
                        "evaluator_id": "reviewer-1",
                        "channel": "guided_eval",
                        "session_label": "session-a",
                        "recommendation": "hold",
                        "summary": "Preview baseline is usable but not yet broader-preview ready.",
                        "findings": [
                            {"title": "Boot wording is confusing", "severity": "high", "area": "boot", "detail": "Boot story still needs tightening.", "artifact_ref": "artifacts.evaluator_guide_markdown"},
                            {"title": "Recovery wording needs one more pass", "severity": "medium", "area": "recovery", "detail": "Recovery copy should be clearer.", "artifact_ref": "artifacts.evaluator_guide_markdown"},
                            {"title": "Export naming can improve later", "severity": "low", "area": "artifact_packaging", "detail": "Can wait until after broader preview.", "artifact_ref": "artifacts.preview_kit_manifest_json"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_feedback_triage(
                workspace=str(workspace),
                report_dir=str(report_dir),
                history_dir=str(history),
                snapshot_label="triage",
                session_id="agentos:tty1",
                feedback_file=str(feedback_file),
            )
            self.assertEqual(payload["schema_version"], "agentos-feedback-triage.v1")
            triage_dir = Path(payload["triage_dir"])
            self.assertTrue((triage_dir / "feedback-triage.json").exists())
            self.assertTrue((triage_dir / "feedback-triage.md").exists())
            self.assertEqual(payload["summary"]["blocker_count"], 1)
            self.assertEqual(payload["summary"]["watch_count"], 1)
            self.assertEqual(payload["summary"]["polish_count"], 1)
            self.assertEqual(payload["summary"]["promotion_state"], "blocked")
            self.assertEqual(
                payload["summary"]["must_fix_before_broader_preview"],
                ["Boot wording is confusing", "Recovery wording needs one more pass"],
            )
            self.assertEqual(
                payload["summary"]["can_wait_until_after_broader_preview"],
                ["Export naming can improve later"],
            )
            self.assertEqual(validate_feedback_triage(payload), [])


if __name__ == "__main__":
    unittest.main()
