from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.codex_launch_supervision import build_codex_launch_supervision_summary, update_supervision_state
from kernel.engine.base import EngineRunResult
from scripts.kernel_codex_launch_supervision import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_launch_supervision.py"
SUPERVISOR_SCRIPT = ROOT_DIR / "scripts" / "agentos_codex_supervisor.py"


class KernelCodexLaunchSupervisionTests(unittest.TestCase):
    def test_supervision_state_tracks_failed_launch_and_restart_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = update_supervision_state(
                state_root=td,
                session_origin="live_appliance_boot",
                command="codex",
                restart_policy="on_failure",
                max_attempts=3,
                cooldown_sec=5,
                run_result=EngineRunResult(ok=False, error_type="non_zero_exit", error_message="boom", exit_code=2),
            )
            self.assertEqual(payload["last_launch_state"], "failed")
            self.assertEqual(payload["next_action"], "restart_codex_cli")
            summary = build_codex_launch_supervision_summary(
                state_root=td,
                provider="codex",
                engine_status="FAIL",
                restart_policy="on_failure",
                max_attempts=3,
                cooldown_sec=5,
            )
            self.assertEqual(summary["failure_class"], "non_zero_exit")
            self.assertEqual(validate_payload({"schema_version": summary["schema_version"], **summary}), [])

    def test_supervisor_cli_success_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/usr/bin/env bash\nif [ \"$1\" = \"exec\" ]; then\n  printf 'HEALTH_OK'\n  exit 0\nfi\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            spec = {
                "name": "codex-launch-supervision",
                "tools": {"bash": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {
                        "command": str(fake),
                        "timeout_sec": 5,
                        "model": "gpt-test",
                        "supervision": {"enabled": True, "restart_policy": "on_failure", "max_attempts": 3, "cooldown_sec": 1},
                    },
                },
            }
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = "dummy"
            env["AGENTOS_CODEX_SUPERVISION_STATE_FILE"] = str(root / "runtime" / "codex-launch-supervision.json")
            result = subprocess.run(
                ["python3", str(SUPERVISOR_SCRIPT), "--workspace", str(root), "--json"],
                cwd=ROOT_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            report = subprocess.run(
                ["python3", str(SCRIPT), "--workspace", str(root), "--json"],
                cwd=ROOT_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(report.stdout)
            self.assertEqual(summary["restart_policy"], "on_failure")
            self.assertEqual(summary["last_launch_state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
