from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_evaluator_feedback_intake import build_feedback_intake, validate_feedback_intake


class KernelEvaluatorFeedbackIntakeTests(unittest.TestCase):
    def test_build_feedback_intake_writes_expected_layout(self) -> None:
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
                        "name": "feedback-intake-test",
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
                json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "source": "journald", "kind": "session.login", "actor": {"uid": 1000}, "object": {"session_id": "agentos:tty1"}, "action": "login", "decision": {"state": "observed"}, "correlation": {"session_id": "agentos:tty1", "session_origin": "local_managed_tty1", "next_managed_entry": "ai_shell"}, "raw_ref": {"collector": "journald"}}) + "\n",
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
            feedback_file = root / "feedback.json"
            feedback_file.write_text(
                json.dumps(
                    {
                        "evaluator_id": "reviewer-1",
                        "channel": "internal_preview",
                        "session_label": "session-a",
                        "recommendation": "advance",
                        "summary": "Preview baseline looks coherent.",
                        "findings": [
                            {
                                "title": "Identity path is clear",
                                "severity": "low",
                                "area": "install_identity",
                                "detail": "The setup-first path is understandable.",
                                "artifact_ref": "artifacts.evaluator_guide_markdown",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_feedback_intake(
                workspace=str(workspace),
                report_dir=str(report_dir),
                history_dir=str(history),
                snapshot_label="preview",
                session_id="agentos:tty1",
                feedback_file=str(feedback_file),
            )
            self.assertEqual(payload["schema_version"], "agentos-evaluator-feedback-intake.v1")
            intake_dir = Path(payload["intake_dir"])
            self.assertTrue((intake_dir / "feedback-intake-manifest.json").exists())
            self.assertTrue((intake_dir / "feedback-template.json").exists())
            self.assertEqual(payload["feedback_packet"]["recommendation"], "advance")
            self.assertEqual(validate_feedback_intake(payload), [])


if __name__ == "__main__":
    unittest.main()
