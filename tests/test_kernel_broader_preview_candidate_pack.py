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

from kernel_broader_preview_candidate_pack import build_broader_preview_candidate_pack, validate_broader_preview_candidate_pack


class KernelBroaderPreviewCandidatePackTests(unittest.TestCase):
    def test_build_broader_preview_candidate_pack_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)
            (workspace / "spec.yaml").write_text("name: smoke\n", encoding="utf-8")
            (artifacts / "runtime_trace.jsonl").write_text("", encoding="utf-8")
            (artifacts / "os_events.jsonl").write_text("", encoding="utf-8")
            policy_dir = artifacts / "kernel-policy"
            policy_dir.mkdir(parents=True)
            (policy_dir / "shadow-report.json").write_text(
                json.dumps(
                    {
                        "summary": {"policies_total": 1},
                        "policy_targets": [
                            {
                                "target": "fs_workspace_boundary",
                                "readiness_score": 85,
                                "false_positive_count": 0,
                                "false_deny_count": 0,
                                "lifecycle_state": "shadow",
                                "recommended_next_state": "guarded_enforce",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (policy_dir / "bridge-state.json").write_text(json.dumps({"effective_state": "enabled"}), encoding="utf-8")
            (artifacts / "validation-history").mkdir(parents=True)
            feedback = workspace / "feedback.json"
            feedback.write_text(
                json.dumps(
                    {
                        "evaluator_id": "eva-01",
                        "channel": "guided_eval",
                        "session_label": "preview-a",
                        "recommendation": "hold",
                        "summary": "Looks close but needs one more pass.",
                        "findings": [
                            {"title": "Boot wording", "severity": "medium", "area": "boot", "detail": "Clarify the default path."},
                            {"title": "Packaging polish", "severity": "low", "area": "artifact_packaging", "detail": "Can wait later."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_broader_preview_candidate_pack(
                workspace=str(workspace),
                report_dir=str(artifacts),
                feedback_file=str(feedback),
                snapshot_label="candidate",
            )

            self.assertEqual(payload["schema_version"], "agentos-broader-preview-candidate-pack.v1")
            self.assertTrue(Path(payload["artifacts"]["broader_preview_candidate_pack_json"]).exists())
            self.assertEqual(payload["summary"]["promotion_state"], "candidate_watch")
            self.assertEqual(payload["summary"]["audience_decision"], "limited_preview_extension_only")
            self.assertEqual(payload["summary"]["direct_boot_confidence"], "watch")
            self.assertEqual(validate_broader_preview_candidate_pack(payload), [])


if __name__ == "__main__":
    unittest.main()
