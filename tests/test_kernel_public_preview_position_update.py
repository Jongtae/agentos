from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_public_preview_position_update import (
    build_public_preview_position_update,
    validate_public_preview_position_update,
)


class KernelPublicPreviewPositionUpdateTests(unittest.TestCase):
    def test_build_public_preview_position_update_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)
            (workspace / "spec.yaml").write_text("name: smoke\n", encoding="utf-8")
            (artifacts / "runtime_trace.jsonl").write_text("", encoding="utf-8")
            (artifacts / "os_events.jsonl").write_text(
                json.dumps({
                    "timestamp_utc": "2026-04-14T00:00:00+00:00",
                    "source": "journald",
                    "kind": "session.login",
                    "actor": {"uid": 1000},
                    "object": {"session_id": "agentos:tty1"},
                    "action": "login",
                    "decision": {"state": "observed"},
                    "correlation": {"session_id": "agentos:tty1", "session_origin": "live_appliance_boot", "next_managed_entry": "ai_shell"},
                    "raw_ref": {"collector": "journald"},
                }) + "\n",
                encoding="utf-8",
            )
            (artifacts / "feedback.json").write_text(
                json.dumps({
                    "findings": [
                        {"title": "Boot wording", "severity": "high", "area": "boot"},
                        {"title": "Packaging polish", "severity": "low", "area": "general"},
                    ],
                    "recommendation": "hold",
                }),
                encoding="utf-8",
            )
            policy_dir = artifacts / "kernel-policy"
            policy_dir.mkdir(parents=True)
            (policy_dir / "shadow-report.json").write_text(json.dumps({"summary": {"policies_total": 1}, "policy_targets": [{"target": "fs_workspace_boundary", "readiness_score": 85, "false_positive_count": 0, "false_deny_count": 0, "lifecycle_state": "shadow", "recommended_next_state": "guarded_enforce"}]}), encoding="utf-8")
            (policy_dir / "bridge-state.json").write_text(json.dumps({"effective_state": "enabled"}), encoding="utf-8")
            history = artifacts / "validation-history"
            history.mkdir(parents=True)
            (history / "window-1.json").write_text(json.dumps({"schema_version": "agentos-validation-window.v1", "label": "window-1", "generated_at_utc": "2026-04-13T00:00:00Z", "summary": {"runtime_ok": True, "session_phase": "ai_shell", "session_origin": "live_appliance_boot", "install_validation_ok": True, "audit_ok": True, "diagnostics_ok": True, "diagnostics_readiness_status": "ready", "approval_forensic_status": "requested", "policy_targets": {"destructive_action_approval": "candidate"}, "overall_state": "ready"}}), encoding="utf-8")

            payload = build_public_preview_position_update(
                workspace=str(workspace),
                report_dir=str(artifacts),
                feedback_file=str(artifacts / "feedback.json"),
                snapshot_label="ops",
            )

            self.assertEqual(payload["schema_version"], "agentos-public-preview-position-update.v1")
            self.assertTrue(Path(payload["artifacts"]["public_preview_position_update_json"]).exists())
            self.assertEqual(validate_public_preview_position_update(payload), [])


if __name__ == "__main__":
    unittest.main()
