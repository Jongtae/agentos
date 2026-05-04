from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "remaster_agentos_iso.sh"


class RemasterAgentOsIsoContractTests(unittest.TestCase):
    def test_help(self):
        proc = subprocess.run([str(SCRIPT), '--help'], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('Usage:', proc.stdout)
        self.assertIn('--base-image', proc.stdout)
        self.assertIn('--asset-bundle', proc.stdout)
        self.assertIn('--output-iso', proc.stdout)
