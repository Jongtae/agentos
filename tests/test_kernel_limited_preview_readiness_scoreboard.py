from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_limited_preview_readiness_scoreboard import (
    build_limited_preview_readiness_scoreboard,
    validate_limited_preview_readiness_scoreboard,
)


class KernelLimitedPreviewReadinessScoreboardTests(unittest.TestCase):
    def test_build_scoreboard_writes_expected_layout(self) -> None:
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
                        "name": "limited-preview-scoreboard-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (workspace / "artifacts" / "runtime_trace.jsonl").write_text(json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "event": "run_start", "payload": {}}) + "\n", encoding="utf-8")
            (workspace / "artifacts" / "os_events.jsonl").write_text(json.dumps({"timestamp_utc": "2026-04-14T00:00:00+00:00", "source": "journald", "kind": "session.login", "actor": {"uid": 1000}, "object": {"session_id": "agentos:tty1"}, "action": "login", "decision": {"state": "observed"}, "correlation": {"session_id": "agentos:tty1", "session_origin": "live_appliance_boot", "next_managed_entry": "ai_shell"}, "raw_ref": {"collector": "journald"}}) + "\n", encoding="utf-8")
            (policy_dir / "profile-lifecycle.json").write_text(json.dumps({"bridge_state": "reloaded", "reload_state": "applied", "disable_state": "inactive", "operator_state": "ready"}) + "\n", encoding="utf-8")
            (policy_dir / "enforced-pilot.json").write_text(json.dumps({"enabled": True, "policy_target": "destructive_action_approval"}) + "\n", encoding="utf-8")
            (policy_dir / "shadow-report.json").write_text(json.dumps({"summary": {"policies_total": 1}, "policy_targets": [{"target": "fs_workspace_boundary", "readiness_score": 85, "false_positive_count": 0, "false_deny_count": 0, "lifecycle_state": "shadow", "recommended_next_state": "guarded_enforce"}]}) + "\n", encoding="utf-8")
            (policy_dir / "bridge-state.json").write_text(json.dumps({"effective_state": "enabled"}), encoding="utf-8")
            (history / "window-1.json").write_text(json.dumps({"schema_version": "agentos-validation-window.v1", "label": "window-1", "generated_at_utc": "2026-04-13T00:00:00Z", "summary": {"runtime_ok": True, "session_phase": "ai_shell", "session_origin": "live_appliance_boot", "install_validation_ok": True, "audit_ok": True, "diagnostics_ok": True, "diagnostics_readiness_status": "ready", "approval_forensic_status": "requested", "policy_targets": {"destructive_action_approval": "candidate"}, "overall_state": "ready"}}) + "\n", encoding="utf-8")
            feedback_file = root / "feedback.json"
            feedback_file.write_text(json.dumps({"evaluator_id": "reviewer-1", "channel": "guided_eval", "session_label": "session-a", "recommendation": "hold", "summary": "Need a bit more limited preview time.", "findings": [{"title": "Recovery wording needs one more pass", "severity": "medium", "area": "recovery", "detail": "Recovery copy should be clearer.", "artifact_ref": "artifacts.evaluator_guide_markdown"}]}), encoding="utf-8")

            payload = build_limited_preview_readiness_scoreboard(
                workspace=str(workspace),
                report_dir=str(report_dir),
                history_dir=str(history),
                snapshot_label="scoreboard",
                session_id="agentos:tty1",
                feedback_file=str(feedback_file),
            )
            self.assertEqual(payload["schema_version"], "agentos-limited-preview-readiness-scoreboard.v1")
            self.assertTrue(Path(payload["artifacts"]["limited_preview_readiness_scoreboard_json"]).exists())
            self.assertEqual(payload["summary"]["limited_preview_decision"], "extend_limited_preview")
            self.assertEqual(payload["summary"]["recovery_confidence"], "watch")
            self.assertEqual(payload["summary"]["triage_state"], "watch")
            self.assertEqual(validate_limited_preview_readiness_scoreboard(payload), [])


if __name__ == "__main__":
    unittest.main()
