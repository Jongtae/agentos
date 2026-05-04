from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_next_boot_target_summary
from scripts.kernel_next_boot_target_integration import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_next_boot_target_integration.py"


class KernelNextBootTargetIntegrationTests(unittest.TestCase):
    def test_summary_reads_staged_next_boot_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            slots_dir = state_root / "slots"
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / "slot-state.env").write_text(
                "schema_version=agentos-slot-metadata.v1\nactive_slot=A\ninactive_slot=B\nrollback_slot=A\nnext_slot=B\nhealth_state=staged_update_pending\n",
                encoding="utf-8",
            )
            (slots_dir / "next-boot.env").write_text(
                "schema_version=agentos-next-boot.v1\nbootable_slot=B\nstaged_from_slot=A\nrollback_slot=A\npayload_file=/tmp/payload.json\npayload_version=v-next\npayload_channel=preview\npayload_digest=abc123\n",
                encoding="utf-8",
            )
            old = {k: os.environ.get(k) for k in ("AGENTOS_STATE_ROOT",)}
            os.environ["AGENTOS_STATE_ROOT"] = str(state_root)
            self.addCleanup(
                lambda: os.environ.pop("AGENTOS_STATE_ROOT", None)
                if old["AGENTOS_STATE_ROOT"] is None
                else os.environ.__setitem__("AGENTOS_STATE_ROOT", old["AGENTOS_STATE_ROOT"])
            )
            payload = build_next_boot_target_summary()
            self.assertTrue(payload["staged"])
            self.assertEqual(payload["target_slot"], "B")
            self.assertEqual(payload["target_role"], "installed_slot_b")
            self.assertEqual(payload["target_origin"], "installed_appliance_boot")
            self.assertEqual(payload["transition_kind"], "switch_to_inactive_slot")
            self.assertEqual(payload["payload_version"], "v-next")
            self.assertEqual(validate_payload({"schema_version": "agentos-next-boot-target-integration.v1", **payload}), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            slots_dir = state_root / "slots"
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / "slot-state.env").write_text(
                "schema_version=agentos-slot-metadata.v1\nactive_slot=A\ninactive_slot=B\nrollback_slot=A\nnext_slot=B\nhealth_state=staged_update_pending\n",
                encoding="utf-8",
            )
            (slots_dir / "next-boot.env").write_text(
                "schema_version=agentos-next-boot.v1\nbootable_slot=B\nstaged_from_slot=A\nrollback_slot=A\npayload_file=/tmp/payload.json\npayload_version=v-roundtrip\npayload_channel=preview\npayload_digest=abc123\n",
                encoding="utf-8",
            )
            out = Path(td) / "next-boot-target.json"
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = str(state_root)
            subprocess.run(["python3", str(SCRIPT), "--output", str(out)], cwd=ROOT_DIR, env=env, check=True)
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
