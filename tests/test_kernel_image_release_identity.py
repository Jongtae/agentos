from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_image_release_identity
from scripts.kernel_image_release_identity import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_image_release_identity.py"


class KernelImageReleaseIdentityTests(unittest.TestCase):
    def test_identity_is_slot_aware(self) -> None:
        payload = build_image_release_identity(version="v-test", channel="dev")
        self.assertEqual(payload["schema_version"], "agentos-image-release-identity.v1")
        self.assertEqual(payload["version"], "v-test")
        self.assertEqual(payload["channel"], "dev")
        self.assertEqual(payload["update_model"], "image_based_ab_updates")
        self.assertEqual(payload["next_slot"], "B")
        self.assertIn("slot_metadata_file", payload)
        self.assertIn("next_boot_file", payload)
        self.assertIn("next_boot_target_role", payload)
        self.assertEqual(validate_payload(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "image-release-identity.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--version", "v-roundtrip", "--channel", "preview", "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
