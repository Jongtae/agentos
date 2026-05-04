from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_platform_validation import build_platform_validation_matrix, validate_platform_validation_matrix

ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT_DIR / "scripts" / "install_kernel_boot_integration.sh"
VALIDATION_SCRIPT = ROOT_DIR / "scripts" / "kernel_platform_validation.py"


class KernelPlatformValidationTests(unittest.TestCase):
    def test_build_platform_validation_produces_valid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            report_dir = root / "reports"
            install_root = root / "install-root"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "platform-validation-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [str(INSTALL_SCRIPT)],
                cwd=ROOT_DIR,
                check=True,
                env={
                    **dict(__import__("os").environ),
                    "AGENTOS_INSTALL_ROOT": str(install_root),
                    "AGENTOS_ENABLE_SYSTEMD": "0",
                    "DEFAULT_WORKSPACE": str(workspace),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            payload = build_platform_validation_matrix(
                workspace=str(workspace),
                report_dir=str(report_dir),
                install_root=str(install_root),
                snapshot_label="matrix-smoke",
            )
            self.assertEqual(payload["schema_version"], "agentos-platform-validation-matrix.v1")
            self.assertTrue(payload["summary"]["ok"])
            self.assertEqual(payload["summary"]["environment_count"], 3)
            self.assertEqual(payload["summary"]["active_origin_count"], 3)
            self.assertEqual(payload["baseline"]["architecture"], "x86_64")
            self.assertEqual(payload["baseline"]["preferred_session_origins"], ["live_appliance_boot", "installed_appliance_boot"])
            self.assertIn("x86_64_live_appliance_vm", payload["validation_matrix"])
            self.assertEqual(validate_platform_validation_matrix(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            report_dir = root / "reports"
            install_root = root / "install-root"
            out = root / "platform-validation.json"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "platform-validation-roundtrip",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [str(INSTALL_SCRIPT)],
                cwd=ROOT_DIR,
                check=True,
                env={
                    **dict(__import__("os").environ),
                    "AGENTOS_INSTALL_ROOT": str(install_root),
                    "AGENTOS_ENABLE_SYSTEMD": "0",
                    "DEFAULT_WORKSPACE": str(workspace),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            subprocess.run(
                [
                    "python3",
                    str(VALIDATION_SCRIPT),
                    "--workspace",
                    str(workspace),
                    "--report-dir",
                    str(report_dir),
                    "--install-root",
                    str(install_root),
                    "--output",
                    str(out),
                ],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(VALIDATION_SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
