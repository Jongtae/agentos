from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / 'scripts' / 'kernel_welcome_first_vm_proof_pack.py'


class KernelWelcomeFirstVMProofPackTests(unittest.TestCase):
    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checklist = root / 'checklist.json'
            checklist.write_text(json.dumps({'schema_version':'agentos-remastered-vm-boot-checklist.v1','summary':{'ok':True}}) + '\n', encoding='utf-8')
            first = root / 'first.json'
            first.write_text(json.dumps({'schema_version':'agentos-vm-first-screen-evidence.v1','evidence_status':'ready','expected_first_path':'Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>'}) + '\n', encoding='utf-8')
            target = root / 'target.json'
            target.write_text(json.dumps({'schema_version':'agentos-boot-target-activation.v1','default_boot_target_label':'Continue to AgentOS','activation_status':'ready'}) + '\n', encoding='utf-8')
            out = root / 'proof-pack.json'
            subprocess.run([
                'python3', str(SCRIPT),
                '--report-dir', str(root / 'reports'),
                '--checklist-manifest', str(checklist),
                '--vm-first-screen-evidence', str(first),
                '--boot-target-activation', str(target),
                '--output', str(out),
            ], cwd=ROOT_DIR, check=True)
            result = subprocess.run(['python3', str(SCRIPT), '--validate', str(out), '--json'], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload['ok'])


if __name__ == '__main__':
    unittest.main()
