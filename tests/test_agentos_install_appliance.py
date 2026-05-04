from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
INSTALLER = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-install-appliance'
HANDOFF = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-handoff'
WELCOME = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-welcome-shell'


class AgentOSInstallApplianceTests(unittest.TestCase):
    def test_install_script_writes_request_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            req = Path(td) / 'install.env'
            env = dict(os.environ)
            env['AGENTOS_INSTALL_REQUEST_FILE'] = str(req)
            proc = subprocess.run(
                ['bash', str(INSTALLER)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 10)
            self.assertTrue(req.exists())
            content = req.read_text(encoding='utf-8')
        self.assertIn('action_label=Install AgentOS', content)
        self.assertIn('persistence_goal=make_this_appliance_persistent', content)
        self.assertIn('target_origin=installed_appliance_boot', content)
        self.assertIn('installer_ui_hidden=true', content)

    def test_install_script_records_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            req = Path(td) / 'install.env'
            handoff = Path(td) / 'handoff.env'
            env = dict(os.environ)
            env['AGENTOS_INSTALL_REQUEST_FILE'] = str(req)
            env['AGENTOS_HANDOFF_BIN'] = str(HANDOFF)
            env['AGENTOS_HANDOFF_FILE'] = str(handoff)
            proc = subprocess.run(
                ['bash', str(INSTALLER)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 10)
            content = handoff.read_text(encoding='utf-8')
        self.assertIn('route=install_agentos', content)
        self.assertIn('next_step=persistent_install', content)
        self.assertIn('origin=agentos_install_appliance', content)

    def test_welcome_install_execs_install_appliance_helper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            req = Path(td) / 'install.env'
            handoff = Path(td) / 'handoff.env'
            env = dict(os.environ)
            env['AGENTOS_INSTALL_APPLIANCE_BIN'] = str(INSTALLER)
            env['AGENTOS_INSTALL_REQUEST_FILE'] = str(req)
            env['AGENTOS_HANDOFF_BIN'] = str(HANDOFF)
            env['AGENTOS_HANDOFF_FILE'] = str(handoff)
            proc = subprocess.run(
                ['bash', str(WELCOME), 'install'],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 10)
            self.assertTrue(req.exists())
            content = req.read_text(encoding='utf-8')
        self.assertIn('written_by=agentos-install-appliance.v1', content)
        self.assertIn('Post-install identity: AgentOS Setup -> AgentOS Managed Session -> ai>', proc.stdout)


if __name__ == '__main__':
    unittest.main()
