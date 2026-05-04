from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.installed_boot_to_codex import build_installed_boot_to_codex_summary
from scripts.kernel_installed_boot_to_codex import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALLED_BOOT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-installed-boot"
SCRIPT = ROOT_DIR / "scripts" / "kernel_installed_boot_to_codex.py"


class KernelInstalledBootToCodexTests(unittest.TestCase):
    def test_summary_links_installed_boot_to_codex_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            boot_file = Path(td) / "installed.env"
            evidence_file = Path(td) / "slot-switch.env"
            env = dict(os.environ)
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(boot_file)
            env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"] = str(evidence_file)
            evidence_file.write_text(
                "planned_slot=B\nobserved_slot=B\nswitch_confirmed=true\nevidence_status=ready\ntransition_kind=booted_planned_slot\n",
                encoding="utf-8",
            )
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
            summary = build_installed_boot_to_codex_summary(
                installed_boot={
                    "origin": "installed_appliance_boot",
                    "manifest_path": str(boot_file),
                    "manifest_exists": True,
                    "identity_path": ["AgentOS Setup", "AgentOS Managed Session", "ai>"],
                    "runtime_owner": "codex_cli_managed_session",
                    "runtime_target": "codex_cli_managed_session",
                    "runtime_continuity": True,
                },
                primary_runtime={"managed_runtime_target": "codex_cli_managed_session"},
                runtime_contract={"continuity_contract": {"rejoin_target": "codex_cli_managed_session"}},
                next_boot_target={"target_slot": "B"},
            )
        self.assertTrue(summary["managed_session_reachable"])
        self.assertEqual(summary["target_slot"], "B")
        self.assertEqual(validate_payload(summary), [])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            boot_file = Path(td) / "installed.env"
            evidence_file = Path(td) / "slot-switch.env"
            out = Path(td) / "installed-boot-to-codex.json"
            env = dict(os.environ)
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(boot_file)
            env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"] = str(evidence_file)
            evidence_file.write_text(
                "planned_slot=B\nobserved_slot=B\nswitch_confirmed=true\nevidence_status=ready\ntransition_kind=booted_planned_slot\n",
                encoding="utf-8",
            )
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
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
