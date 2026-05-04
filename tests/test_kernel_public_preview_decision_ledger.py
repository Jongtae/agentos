from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_decision_ledger import (
    build_public_preview_decision_ledger,
    validate_public_preview_decision_ledger,
)


class PublicPreviewDecisionLedgerTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appdl-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_decision_ledger(
                workspace=str(workspace),
                report_dir=str(report_dir),
                snapshot_label="c",
            )
            self.assertEqual(payload["schema_version"], "agentos-public-preview-decision-ledger.v1")
            self.assertIn(payload["summary"]["decision_state"], {"ready_for_public_preview_decision", "hold_before_public_preview_decision"})
            self.assertEqual(validate_public_preview_decision_ledger(payload), [])


if __name__ == "__main__":
    unittest.main()
