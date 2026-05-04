from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'kernel_appliance_boot_signoff_pack.py'


class KernelApplianceBootSignoffPackTests(unittest.TestCase):
    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            welcome = tmp_path / 'welcome.json'
            reboot = tmp_path / 'reboot.json'
            recovery = tmp_path / 'recovery.json'
            out = tmp_path / 'signoff.json'
            welcome.write_text(json.dumps({
                'schema_version': 'agentos-welcome-first-vm-proof-pack.v1',
                'summary': {
                    'ok': True,
                    'expected_path': 'Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>',
                },
            }) + '\n', encoding='utf-8')
            reboot.write_text(json.dumps({
                'schema_version': 'agentos-installed-reboot-slot-proof.v1',
                'summary': {
                    'ok': True,
                    'expected_installed_path': 'Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>',
                },
            }) + '\n', encoding='utf-8')
            recovery.write_text(json.dumps({
                'schema_version': 'agentos-recovery-reentry-after-slot-switch.v1',
                'summary': {
                    'ok': True,
                    'expected_return_path': 'AgentOS Recovery -> Return to AgentOS -> ai>',
                },
            }) + '\n', encoding='utf-8')

            subprocess.run([
                str(SCRIPT),
                '--report-dir', str(tmp_path / 'reports'),
                '--welcome-first-vm-proof-pack', str(welcome),
                '--installed-reboot-slot-proof', str(reboot),
                '--recovery-reentry-after-slot-switch', str(recovery),
                '--output', str(out),
            ], check=True)

            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(payload['schema_version'], 'agentos-appliance-boot-signoff-pack.v1')
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
