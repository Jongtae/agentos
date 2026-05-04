from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_operator_review_pack_history import build_review_pack_history


class KernelOperatorReviewPackHistoryTests(unittest.TestCase):
    def test_build_review_pack_history_summarizes_drift(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pack-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-operator-review-pack.v1",
                        "generated_at_utc": "2026-04-13T00:00:00Z",
                        "workspace": "/tmp/ws",
                        "summary": {
                            "session_phase": "setup_session",
                            "approval_forensic_status": "pending",
                            "validation_stable": False,
                            "control_categories": ["bridge"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "pack-2.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-operator-review-pack.v1",
                        "generated_at_utc": "2026-04-14T00:00:00Z",
                        "workspace": "/tmp/ws",
                        "summary": {
                            "session_phase": "ai_shell",
                            "approval_forensic_status": "quiet",
                            "validation_stable": True,
                            "control_categories": ["bridge", "operator_control"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_review_pack_history(history_dir=str(root), limit=10)
            self.assertEqual(payload["schema_version"], "agentos-operator-review-pack-history.v1")
            self.assertEqual(payload["summary"]["review_pack_count"], 2)
            self.assertFalse(payload["summary"]["stable"])
            self.assertIn("session_phase", payload["summary"]["changed_fields"])
            self.assertEqual(payload["summary"]["latest_session_phase"], "ai_shell")


if __name__ == "__main__":
    unittest.main()
