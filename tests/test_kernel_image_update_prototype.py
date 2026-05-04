from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_image_update_prototype import build_update_payload, validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / 'scripts' / 'kernel_image_update_prototype.py'
SLOT_INIT = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-slot-metadata-init'


class KernelImageUpdatePrototypeTests(unittest.TestCase):
    def test_build_update_payload_targets_inactive_slot(self) -> None:
        payload = build_update_payload(version='v-test', channel='preview', dry_run=True)
        self.assertEqual(payload['schema_version'], 'agentos-image-update-prototype.v1')
        self.assertEqual(payload['target_slot'], 'B')
        self.assertEqual(payload['next_slot'], 'B')
        self.assertEqual(validate_payload(payload), [])

    def test_staging_writes_payload_and_next_boot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env['AGENTOS_STATE_ROOT'] = td
            subprocess.run(['bash', str(SLOT_INIT)], check=True, env=env, capture_output=True, text=True)
            out = Path(td) / 'update.json'
            subprocess.run(
                ['python3', str(SCRIPT), '--version', 'v-stage', '--channel', 'preview', '--output', str(out)],
                check=True,
                cwd=ROOT_DIR,
                env=env,
            )
            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(payload['stage_status'], 'staged')
            self.assertTrue(Path(payload['payload_file']).exists())
            self.assertTrue(Path(payload['next_boot_file']).exists())
            metadata = Path(td) / 'slots' / 'slot-state.env'
            self.assertIn('next_slot=B', metadata.read_text(encoding='utf-8'))
            self.assertIn('health_state=staged_update_pending', metadata.read_text(encoding='utf-8'))

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'image-update.json'
            env = dict(os.environ)
            env['AGENTOS_STATE_ROOT'] = td
            subprocess.run(['bash', str(SLOT_INIT)], check=True, env=env, capture_output=True, text=True)
            subprocess.run(
                ['python3', str(SCRIPT), '--version', 'v-roundtrip', '--channel', 'dev', '--dry-run', '--output', str(out)],
                cwd=ROOT_DIR,
                check=True,
                env=env,
            )
            result = subprocess.run(
                ['python3', str(SCRIPT), '--validate', str(out), '--json'],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload['ok'])


if __name__ == '__main__':
    unittest.main()
