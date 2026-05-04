from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'kernel_recovery_reentry_after_slot_switch.py'


class KernelRecoveryReentryAfterSlotSwitchTests(unittest.TestCase):
    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            reboot = tmp_path / 'reboot.json'
            recovery = tmp_path / 'recovery.json'
            out = tmp_path / 'proof.json'
            reboot.write_text(json.dumps({
                'schema_version': 'agentos-installed-reboot-slot-proof.v1',
                'summary': {'ok': True},
            }) + '\n', encoding='utf-8')
            recovery.write_text(json.dumps({
                'schema_version': 'agentos-slot-recovery-logic.v1',
                'recovery_required': True,
                'return_action': 'return_to_agentos',
                'return_path': 'AgentOS Recovery -> Return to AgentOS -> ai>',
            }) + '\n', encoding='utf-8')

            subprocess.run([
                str(SCRIPT),
                '--report-dir', str(tmp_path / 'reports'),
                '--installed-reboot-slot-proof', str(reboot),
                '--slot-recovery-logic', str(recovery),
                '--output', str(out),
            ], check=True)

            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(payload['schema_version'], 'agentos-recovery-reentry-after-slot-switch.v1')
            self.assertTrue(payload['summary']['ok'])

            validate = subprocess.run([
                str(SCRIPT),
                '--validate', str(out),
                '--json',
            ], check=True, capture_output=True, text=True)
            result = json.loads(validate.stdout)
            self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
