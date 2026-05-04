from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_launch_readiness_review import build_public_preview_launch_readiness_review, validate_public_preview_launch_readiness_review


class PublicPreviewLaunchReadinessReviewTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="applrr-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_launch_readiness_review(workspace=str(workspace), report_dir=str(report_dir), snapshot_label="c")
            self.assertEqual(payload["schema_version"], "agentos-public-preview-launch-readiness-review.v1")
            self.assertIn(payload["summary"]["launch_readiness"], {"ready", "not_ready"})
            self.assertEqual(validate_public_preview_launch_readiness_review(payload), [])


if __name__ == "__main__":
    unittest.main()
