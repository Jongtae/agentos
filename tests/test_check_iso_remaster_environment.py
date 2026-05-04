from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "check_iso_remaster_environment.py"


class IsoRemasterEnvironmentTests(unittest.TestCase):
    def test_json_shape(self):
        proc = subprocess.run(["python3", str(SCRIPT), "--json"], capture_output=True, text=True, check=False)
        self.assertIn(proc.returncode, (0, 1))
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "agentos-iso-remaster-environment.v1")
        self.assertEqual(payload["supported_environment"], "linux-remaster-toolchain")
        self.assertEqual(payload["required_tools"], ["xorriso", "unsquashfs", "mksquashfs", "bsdtar"])
        self.assertIsInstance(payload["missing_tools"], list)
        self.assertIsInstance(payload["tools"], dict)
