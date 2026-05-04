from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.codex_slot_transition_compatibility import build_codex_slot_transition_compatibility_summary
from scripts.kernel_codex_slot_transition_compatibility import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_slot_transition_compatibility.py"
INSTALLED_BOOT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-installed-boot"


class KernelCodexSlotTransitionCompatibilityTests(unittest.TestCase):
    def test_summary_reports_runtime_first_transition(self) -> None:
        summary = build_codex_slot_transition_compatibility_summary(
            slot_update_contract={
                "active_slot": "A",
                "inactive_slot": "B",
                "rollback_slot": "A",
                "next_slot": "B",
            },
            next_boot_target={"staged": True, "target_slot": "B", "transition_kind": "switch_to_inactive_slot"},
            slot_recovery={
                "rollback_candidate": "A",
                "recovery_required": False,
                "next_action": "boot_staged_slot_b",
                "runtime_return_target": "codex_cli_managed_session",
            },
            installed_boot_to_codex={
                "runtime_target": "codex_cli_managed_session",
                "managed_session_reachable": True,
            },
            recovery_to_codex={"recovery_ready": True},
        )
        self.assertTrue(summary["continuity_ready"])
        self.assertEqual(summary["runtime_return_target"], "codex_cli_managed_session")
        self.assertEqual(validate_payload(summary), [])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(Path(td) / "installed.env")
            env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"] = str(Path(td) / "slot-switch.env")
            env["AGENTOS_STATE_ROOT"] = str(Path(td) / "state-root")
            slots_dir = Path(env["AGENTOS_STATE_ROOT"]) / "slots"
            slots_dir.mkdir(parents=True, exist_ok=True)
            (slots_dir / "slot-state.env").write_text(
                "active_slot=A\ninactive_slot=B\nrollback_slot=A\nnext_slot=B\nhealth_state=healthy\n",
                encoding="utf-8",
            )
            (slots_dir / "next-boot.env").write_text(
                "bootable_slot=B\nstaged_from_slot=A\npayload_version=v-test\npayload_channel=preview\npayload_digest=abc123\npayload_file=/tmp/payload.json\n",
                encoding="utf-8",
            )
            Path(env["AGENTOS_SLOT_SWITCH_EVIDENCE_FILE"]).write_text(
                "planned_slot=B\nobserved_slot=B\nswitch_confirmed=true\nevidence_status=ready\ntransition_kind=booted_planned_slot\n",
                encoding="utf-8",
            )
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
            out = Path(td) / "slot-transition.json"
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
