from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.verify_remastered_boot_flow import build_proof, validate_proof

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / 'scripts' / 'verify_remastered_boot_flow.py'


class VerifyRemasteredBootFlowTests(unittest.TestCase):
    def test_build_proof_marks_ready_when_assets_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso_root = root / 'iso-root'
            live_root = root / 'live-root'
            report_path = root / 'boot-report.json'
            (iso_root / 'agentos' / 'boot-assets').mkdir(parents=True, exist_ok=True)
            (live_root / 'etc' / 'xdg' / 'autostart').mkdir(parents=True, exist_ok=True)
            (live_root / 'usr' / 'local' / 'bin').mkdir(parents=True, exist_ok=True)
            for name in ['agentos-welcome-shell', 'agentos-recovery-shell', 'agentos-handoff', 'agentos-install-appliance', 'agentos-state-root-init', 'agentos-installed-boot', 'agentos-slot-metadata-init']:
                (live_root / 'usr' / 'local' / 'bin' / name).write_text('x', encoding='utf-8')
            (live_root / 'etc' / 'xdg' / 'autostart' / 'agentos-welcome.desktop').write_text('desktop', encoding='utf-8')
            report_path.write_text(json.dumps({
                'continue_present': True,
                'install_present': False,
                'install_path_available': True,
                'recovery_present': True,
                'installer_hidden_default_path': True,
                'default_boot_target_label': 'Continue to AgentOS',
                'default_boot_target_entry_index': 0,
                'default_boot_target_configured': True,
            }), encoding='utf-8')
            payload = build_proof(iso_root=iso_root, live_root=live_root, boot_patch_report=report_path)
            self.assertEqual(payload['proof_status'], 'ready')
            self.assertEqual(validate_proof(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso_root = root / 'iso-root'
            live_root = root / 'live-root'
            report_path = root / 'boot-report.json'
            out = root / 'boot-proof.json'
            (iso_root / 'agentos' / 'boot-assets').mkdir(parents=True, exist_ok=True)
            (live_root / 'etc' / 'xdg' / 'autostart').mkdir(parents=True, exist_ok=True)
            (live_root / 'usr' / 'local' / 'bin').mkdir(parents=True, exist_ok=True)
            for name in ['agentos-welcome-shell', 'agentos-recovery-shell', 'agentos-handoff', 'agentos-install-appliance', 'agentos-state-root-init', 'agentos-installed-boot', 'agentos-slot-metadata-init']:
                (live_root / 'usr' / 'local' / 'bin' / name).write_text('x', encoding='utf-8')
            (live_root / 'etc' / 'xdg' / 'autostart' / 'agentos-welcome.desktop').write_text('desktop', encoding='utf-8')
            report_path.write_text(json.dumps({
                'continue_present': True,
                'install_present': False,
                'install_path_available': True,
                'recovery_present': True,
                'installer_hidden_default_path': True,
                'default_boot_target_label': 'Continue to AgentOS',
                'default_boot_target_entry_index': 0,
                'default_boot_target_configured': True,
            }), encoding='utf-8')
            subprocess.run([
                'python3', str(SCRIPT), '--iso-root', str(iso_root), '--live-root', str(live_root), '--boot-patch-report', str(report_path), '--output', str(out)
            ], cwd=ROOT_DIR, check=True)
            result = subprocess.run([
                'python3', str(SCRIPT), '--validate', str(out), '--json'
            ], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload['ok'])


if __name__ == '__main__':
    unittest.main()
