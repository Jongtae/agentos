from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_escalation_pack import (
    build_public_preview_escalation_pack,
    validate_public_preview_escalation_pack,
)


class PublicPreviewEscalationPackTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apppe-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_escalation_pack(
                workspace=str(workspace),
                report_dir=str(report_dir),
                snapshot_label="c",
            )
            self.assertEqual(payload["schema_version"], "agentos-public-preview-escalation-pack.v1")
            self.assertIn(payload["summary"]["escalation_decision"], {"hold_public_preview", "check_public_preview_announcement_readiness"})
            self.assertEqual(validate_public_preview_escalation_pack(payload), [])


if __name__ == "__main__":
    unittest.main()
