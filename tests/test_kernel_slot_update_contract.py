from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_slot_state_summary, build_slot_update_contract
from scripts.kernel_slot_update_contract import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / 'scripts' / 'kernel_slot_update_contract.py'
SLOT_INIT = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-slot-metadata-init'


class KernelSlotUpdateContractTests(unittest.TestCase):
    def test_contract_defaults_to_ab_slots(self) -> None:
        payload = build_slot_update_contract()
        self.assertEqual(payload['schema_version'], 'agentos-slot-update-contract.v1')
        self.assertEqual(payload['active_slot'], 'A')
        self.assertEqual(payload['inactive_slot'], 'B')
        self.assertEqual(payload['stage_status'], 'idle')
        self.assertIn('next_boot_target', payload)
        self.assertEqual(validate_payload(payload), [])

    def test_slot_state_summary_reads_metadata_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env['AGENTOS_STATE_ROOT'] = td
            env['AGENTOS_ACTIVE_SLOT'] = 'B'
            env['AGENTOS_INACTIVE_SLOT'] = 'A'
            env['AGENTOS_ROLLBACK_SLOT'] = 'B'
            env['AGENTOS_NEXT_SLOT'] = 'A'
            subprocess.run(['bash', str(SLOT_INIT)], check=True, env=env, capture_output=True, text=True)
            old = {k: os.environ.get(k) for k in ['AGENTOS_STATE_ROOT', 'AGENTOS_ACTIVE_SLOT', 'AGENTOS_INACTIVE_SLOT', 'AGENTOS_ROLLBACK_SLOT', 'AGENTOS_NEXT_SLOT']}
            os.environ.update({
                'AGENTOS_STATE_ROOT': td,
                'AGENTOS_ACTIVE_SLOT': 'B',
                'AGENTOS_INACTIVE_SLOT': 'A',
                'AGENTOS_ROLLBACK_SLOT': 'B',
                'AGENTOS_NEXT_SLOT': 'A',
            })
            for key, value in old.items():
                self.addCleanup(lambda k=key, v=value: os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))
            summary = build_slot_state_summary()
        self.assertTrue(summary['metadata_exists'])
        self.assertEqual(summary['active_slot'], 'B')
        self.assertEqual(summary['inactive_slot'], 'A')
        self.assertEqual(summary['next_slot'], 'A')
        self.assertFalse(summary['next_boot_exists'])
        self.assertEqual(summary['next_boot_target_slot'], 'A')

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'slot-update.json'
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
