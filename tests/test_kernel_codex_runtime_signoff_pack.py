from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_runtime_signoff_pack.py"
STATE_INIT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-state-root-init"
INSTALLER = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-install-appliance"
INSTALLED_BOOT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-installed-boot"


class KernelCodexRuntimeSignoffPackTests(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td) / "state-root"
            slots_dir = state_root / "slots"
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / "slot-state.env").write_text(
                "active_slot=A\ninactive_slot=B\nrollback_slot=A\nnext_slot=B\nhealth_state=healthy\n",
                encoding="utf-8",
            )
            (slots_dir / "next-boot.env").write_text(
                "bootable_slot=B\nstaged_from_slot=A\npayload_version=v-test\npayload_channel=preview\npayload_digest=abc123\npayload_file=/tmp/payload.json\n",
                encoding="utf-8",
            )
            evidence = Path(td) / "slot-switch.env"
            evidence.write_text(
                "planned_slot=B\nobserved_slot=B\nswitch_confirmed=true\nevidence_status=ready\ntransition_kind=booted_planned_slot\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = str(state_root)
            env["AGENTOS_INSTALL_REQUEST_FILE"] = str(Path(td) / "install.env")
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(Path(td) / "installed.env")
            env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"] = str(evidence)
            subprocess.run(["bash", str(STATE_INIT)], env=env, check=True, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLER)], env=env, check=False, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
            out = Path(td) / "runtime-signoff.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", "./workspaces/default", "--output", str(out)],
                cwd=ROOT_DIR,
                env=env,
                check=True,
            )
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
