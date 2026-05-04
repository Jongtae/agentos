from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_remastered_vm_boot_checklist.py"


class KernelRemasteredVMBootChecklistTests(unittest.TestCase):
    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = root / "state-root"
            slots_dir = state_root / "slots"
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / "slot-state.env").write_text(
                "schema_version=agentos-slot-metadata.v1\nactive_slot=B\ninactive_slot=A\nrollback_slot=A\nnext_slot=B\nhealth_state=healthy\n",
                encoding="utf-8",
            )
            installed_boot = root / "installed.env"
            installed_boot.write_text(
                "origin=installed_appliance_boot\nidentity_path=AgentOS Setup -> AgentOS Managed Session -> ai>\n",
                encoding="utf-8",
            )
            switch_evidence = root / "switch.env"
            switch_evidence.write_text(
                "planned_slot=B\nobserved_slot=B\nswitch_confirmed=true\nevidence_status=ready\ntransition_kind=booted_planned_slot\npayload_version=v-checklist\npayload_channel=preview\nidentity_path=AgentOS Setup -> AgentOS Managed Session -> ai>\n",
                encoding="utf-8",
            )
            next_boot = slots_dir / "next-boot.env"
            next_boot.write_text(
                "schema_version=agentos-next-boot.v1\nbootable_slot=B\nstaged_from_slot=A\nrollback_slot=A\npayload_file=/tmp/payload.json\npayload_version=v-checklist\npayload_channel=preview\npayload_digest=abc123\n",
                encoding="utf-8",
            )
            flow = root / "boot-flow-proof.json"
            flow.write_text(json.dumps({
                "schema_version": "agentos-remastered-boot-flow-proof.v1",
                "proof_status": "ready",
            }) + "\n", encoding="utf-8")
            target = root / "boot-target-activation.json"
            target.write_text(json.dumps({
                "schema_version": "agentos-boot-target-activation.v1",
                "boot_target_contract": "agentos_continue_boot_target.v1",
                "activation_status": "ready",
            }) + "\n", encoding="utf-8")
            first = root / "vm-first-screen-evidence.json"
            first.write_text(json.dumps({
                "schema_version": "agentos-vm-first-screen-evidence.v1",
                "evidence_contract": "agentos_vm_first_screen_evidence.v1",
                "evidence_status": "ready",
            }) + "\n", encoding="utf-8")
            out = root / "checklist.json"
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = str(state_root)
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(installed_boot)
            env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"] = str(switch_evidence)
            subprocess.run([
                "python3",
                str(SCRIPT),
                "--report-dir",
                str(root / "reports"),
                "--boot-flow-proof",
                str(flow),
                "--boot-target-activation",
                str(target),
                "--vm-first-screen-evidence",
                str(first),
                "--output",
                str(out),
            ], cwd=ROOT_DIR, env=env, check=True)
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
