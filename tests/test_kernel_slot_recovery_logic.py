from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_slot_recovery_summary
from scripts.kernel_slot_recovery_logic import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / 'scripts' / 'kernel_slot_recovery_logic.py'
SLOT_INIT = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-slot-metadata-init'


class KernelSlotRecoveryLogicTests(unittest.TestCase):
    def test_default_summary_stays_on_active_slot(self) -> None:
        payload = build_slot_recovery_summary()
        self.assertEqual(payload['rollback_candidate'], 'A')
        self.assertEqual(payload['next_action'], 'stay_on_active_slot')
        self.assertEqual(validate_payload({'schema_version': 'agentos-slot-recovery-logic.v1', **payload}), [])

    def test_failed_health_gate_requires_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env['AGENTOS_STATE_ROOT'] = td
            env['AGENTOS_SLOT_HEALTH_STATE'] = 'health_gate_failed'
            env['AGENTOS_ROLLBACK_SLOT'] = 'A'
            subprocess.run(['bash', str(SLOT_INIT)], check=True, env=env, capture_output=True, text=True)
            result = subprocess.run(
                ['python3', str(SCRIPT), '--json'],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload['failed_health_gate'])
            self.assertTrue(payload['recovery_required'])
            self.assertEqual(payload['rollback_candidate'], 'A')
            self.assertEqual(payload['next_action'], 'rollback_to_slot_a')

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'slot-recovery.json'
            subprocess.run(['python3', str(SCRIPT), '--output', str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(
                ['python3', str(SCRIPT), '--validate', str(out), '--json'],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload['ok'])


if __name__ == '__main__':
    unittest.main()
