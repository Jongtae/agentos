from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
INSTALLED_BOOT = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-installed-boot'
HANDOFF = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-handoff'
STATE_INIT = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-state-root-init'
SLOT_SWITCH_EVIDENCE = ROOT_DIR / 'image-assets' / 'live' / 'bin' / 'agentos-slot-switch-evidence'


class AgentOSInstalledBootTests(unittest.TestCase):
    def test_installed_boot_writes_manifest_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            boot_file = Path(td) / 'installed.env'
            handoff_file = Path(td) / 'handoff.env'
            evidence_file = Path(td) / 'slot-switch.env'
            state_root = Path(td) / 'state-root'
            slots_dir = state_root / 'slots'
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / 'next-boot.env').write_text(
                'schema_version=agentos-next-boot.v1\nbootable_slot=B\nstaged_from_slot=A\nrollback_slot=A\npayload_file=/tmp/payload.json\npayload_version=v-test\npayload_channel=preview\npayload_digest=abc123\n',
                encoding='utf-8',
            )
            env = dict(os.environ)
            env['AGENTOS_INSTALLED_BOOT_FILE'] = str(boot_file)
            env['AGENTOS_HANDOFF_BIN'] = str(HANDOFF)
            env['AGENTOS_HANDOFF_FILE'] = str(handoff_file)
            env['AGENTOS_STATE_ROOT'] = str(state_root)
            env['AGENTOS_STATE_ROOT_INIT_BIN'] = str(STATE_INIT)
            env['AGENTOS_SLOT_SWITCH_EVIDENCE_BIN'] = str(SLOT_SWITCH_EVIDENCE)
            env['AGENTOS_SLOT_SWITCH_EVIDENCE_FILE'] = str(evidence_file)
            env['AGENTOS_ACTIVE_SLOT'] = 'B'
            env['AGENTOS_INACTIVE_SLOT'] = 'A'
            env['AGENTOS_NEXT_SLOT'] = 'B'
            proc = subprocess.run(
                ['bash', str(INSTALLED_BOOT)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            boot = boot_file.read_text(encoding='utf-8')
            handoff = handoff_file.read_text(encoding='utf-8')
            evidence = evidence_file.read_text(encoding='utf-8')
        self.assertIn('origin=installed_appliance_boot', boot)
        self.assertIn('identity_path=AgentOS Setup -> AgentOS Managed Session -> ai>', boot)
        self.assertIn('route=installed_appliance_boot', handoff)
        self.assertIn('next_step=agentos_setup', handoff)
        self.assertIn('switch_confirmed=true', evidence)
        self.assertIn('planned_slot=B', evidence)


if __name__ == '__main__':
    unittest.main()
