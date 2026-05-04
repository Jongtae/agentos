from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_decision_pack import build_public_preview_decision_pack, validate_public_preview_decision_pack


class PublicPreviewDecisionPackTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apppd-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_decision_pack(workspace=str(workspace), report_dir=str(report_dir), snapshot_label="c")
            self.assertEqual(payload["schema_version"], "agentos-public-preview-decision-pack.v1")
            self.assertIn(payload["summary"]["go_signal"], {"public_preview_go_candidate", "public_preview_hold_candidate"})
            self.assertEqual(validate_public_preview_decision_pack(payload), [])


if __name__ == "__main__":
    unittest.main()
