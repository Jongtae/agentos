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

from kernel_external_evaluation_checklist import (
    build_external_evaluation_checklist,
    validate_external_evaluation_checklist,
)


class KernelExternalEvaluationChecklistTests(unittest.TestCase):
    def test_build_external_evaluation_checklist_writes_expected_layout(self) -> None:
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
                        "channel": "expert_review",
                        "session_label": "preview-a",
                        "recommendation": "advance",
                        "summary": "Looks ready for guided review.",
                        "findings": [{"title": "Minor note", "severity": "low", "area": "guide", "detail": "Clear enough."}],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_external_evaluation_checklist(
                workspace=str(workspace),
                report_dir=str(artifacts),
                feedback_file=str(feedback),
                snapshot_label="candidate",
            )

            self.assertEqual(payload["schema_version"], "agentos-external-evaluation-checklist.v1")
            self.assertTrue(Path(payload["artifacts"]["external_evaluation_checklist_markdown"]).exists())
            self.assertTrue(Path(payload["artifacts"]["feedback_intake_manifest_json"]).exists())
            self.assertEqual(payload["summary"]["recommendation"], "advance")
            self.assertEqual(validate_external_evaluation_checklist(payload), [])


if __name__ == "__main__":
    unittest.main()
