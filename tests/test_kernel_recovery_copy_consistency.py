from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
import sys

SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_recovery_copy_consistency import build_recovery_copy_consistency, validate_recovery_copy_consistency


class KernelRecoveryCopyConsistencyTests(unittest.TestCase):
    def test_build_recovery_copy_consistency_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)

            payload = build_recovery_copy_consistency(
                workspace=str(workspace),
                report_dir=str(artifacts),
                snapshot_label="consistency",
            )

            self.assertEqual(payload["schema_version"], "agentos-recovery-copy-consistency.v1")
            self.assertTrue(Path(payload["artifacts"]["recovery_copy_consistency_manifest_json"]).exists())
            self.assertIn(payload["summary"]["overall_state"], {"watch", "ready"})
            self.assertEqual(validate_recovery_copy_consistency(payload), [])


if __name__ == "__main__":
    unittest.main()
