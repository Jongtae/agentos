from __future__ import annotations

import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.utm_disposable_vm import _normalize_guest_arch, _patch_config


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "utm_disposable_vm.py"


class UtmDisposableVmTests(unittest.TestCase):
    def test_normalize_guest_arch_for_utm(self) -> None:
        self.assertEqual(_normalize_guest_arch("amd64"), "x86_64")
        self.assertEqual(_normalize_guest_arch("arm64"), "aarch64")

    def test_force_delete_vm_tolerates_utm_client_init_failure(self) -> None:
        from scripts import utm_disposable_vm as mod

        osascript_calls = []

        def fake_run_osascript(lines):
            osascript_calls.append(lines)
            return ""

        with (
            mock.patch.object(mod, "_list_vm_names", return_value=["AgentOS Acceptance Test"]),
            mock.patch.object(mod, "_run_osascript", side_effect=fake_run_osascript),
            mock.patch.object(mod, "UTMClient", side_effect=RuntimeError("backend unavailable")),
        ):
            report = mod.force_delete_vm("AgentOS Acceptance Test")

        self.assertTrue(report["deleted"])
        self.assertIn('delete virtual machine named "AgentOS Acceptance Test"', "\n".join(osascript_calls[-1]))

    def test_run_osascript_retries_after_launching_utm(self) -> None:
        from scripts import utm_disposable_vm as mod

        responses = [
            subprocess.CompletedProcess(
                args=["osascript"],
                returncode=1,
                stdout="",
                stderr="38:42: execution error: UTM got an error: Application isn’t running. (-600)",
            ),
            subprocess.CompletedProcess(args=["osascript"], returncode=1, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="AgentOS Preview\n", stderr=""),
        ]

        with (
            mock.patch.object(
                mod.subprocess,
                "run",
                side_effect=[
                    responses[0],
                    subprocess.CompletedProcess(args=["open"], returncode=0, stdout="", stderr=""),
                    responses[1],
                    responses[2],
                ],
            ) as run_mock,
            mock.patch.object(mod.time, "sleep") as sleep_mock,
        ):
            output = mod._run_osascript(['tell application "UTM"', 'return "AgentOS Preview"', "end tell"])

        self.assertEqual(output, "AgentOS Preview")
        self.assertEqual(run_mock.call_args_list[1].args[0], ["open", "-a", "UTM"])
        self.assertEqual(run_mock.call_args_list[2].args[0], ["osascript", "-e", f"tell {mod.UTM_APPLESCRIPT_REF} to activate"])
        sleep_mock.assert_called_once_with(2)

    def test_patch_config_sets_runtime_shape_and_bios_boot_without_extra_guest_agent_args(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            vm_name = "AgentOS Acceptance Test"
            bundle = home / "Library/Containers/com.utmapp.UTM/Data/Documents" / f"{vm_name}.utm"
            bundle.mkdir(parents=True, exist_ok=True)
            config_path = bundle / "config.plist"
            with config_path.open("wb") as handle:
                plistlib.dump(
                    {
                        "Information": {"Name": vm_name, "UUID": "test-uuid"},
                        "System": {"Architecture": "x86_64", "Target": "q35"},
                        "QEMU": {"AdditionalArguments": []},
                    },
                    handle,
                )

            from scripts import utm_disposable_vm as mod

            with mock.patch.object(
                mod,
                "UTM_DOCUMENTS_DIR",
                home / "Library/Containers/com.utmapp.UTM/Data/Documents",
            ):
                payload = _patch_config(vm_name, memory_mib=8192, cpu_cores=4)

            self.assertTrue(payload["QEMU"]["DebugLog"])
            self.assertFalse(payload["QEMU"]["UEFIBoot"])
            self.assertEqual(payload["QEMU"]["AdditionalArguments"], [])
            self.assertEqual(payload["System"]["MemorySize"], 8192)
            self.assertEqual(payload["System"]["CPUCount"], 4)
            self.assertEqual(payload["Display"][0]["Hardware"], "virtio-gpu-pci")
            self.assertEqual(payload["Serial"][0]["Mode"], "Ptty")

    def test_patch_config_sets_arm64_runtime_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            vm_name = "AgentOS Acceptance Test"
            bundle = home / "Library/Containers/com.utmapp.UTM/Data/Documents" / f"{vm_name}.utm"
            bundle.mkdir(parents=True, exist_ok=True)
            config_path = bundle / "config.plist"
            with config_path.open("wb") as handle:
                plistlib.dump(
                    {
                        "Information": {"Name": vm_name, "UUID": "test-uuid"},
                        "System": {"Architecture": "x86_64", "Target": "q35"},
                        "QEMU": {"AdditionalArguments": []},
                    },
                    handle,
                )

            from scripts import utm_disposable_vm as mod

            with mock.patch.object(
                mod,
                "UTM_DOCUMENTS_DIR",
                home / "Library/Containers/com.utmapp.UTM/Data/Documents",
            ):
                payload = _patch_config(vm_name, memory_mib=8192, cpu_cores=4, arch="arm64", uefi_boot=True)

            self.assertEqual(payload["System"]["Architecture"], "aarch64")
            self.assertEqual(payload["System"]["Target"], "virt")
            self.assertTrue(payload["QEMU"]["Hypervisor"])
            self.assertTrue(payload["QEMU"]["UEFIBoot"])

    def test_patch_config_can_enable_uefi_for_headless_server_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            vm_name = "AgentOS Acceptance Test"
            bundle = home / "Library/Containers/com.utmapp.UTM/Data/Documents" / f"{vm_name}.utm"
            bundle.mkdir(parents=True, exist_ok=True)
            config_path = bundle / "config.plist"
            with config_path.open("wb") as handle:
                plistlib.dump(
                    {
                        "Information": {"Name": vm_name, "UUID": "test-uuid"},
                        "System": {"Architecture": "x86_64", "Target": "q35"},
                        "QEMU": {"AdditionalArguments": []},
                    },
                    handle,
                )

            from scripts import utm_disposable_vm as mod

            with mock.patch.object(
                mod,
                "UTM_DOCUMENTS_DIR",
                home / "Library/Containers/com.utmapp.UTM/Data/Documents",
            ):
                payload = _patch_config(vm_name, memory_mib=8192, cpu_cores=4, uefi_boot=True)

            self.assertTrue(payload["QEMU"]["UEFIBoot"])

    def test_create_vm_sets_runtime_shape_at_creation_time(self) -> None:
        from scripts import utm_disposable_vm as mod

        script_calls = []
        with tempfile.TemporaryDirectory() as td:
            iso_path = Path(td) / "agentos.iso"
            iso_path.write_text("iso\n", encoding="utf-8")

            def fake_run_osascript(lines):
                script_calls.append(lines)
                return "AgentOS Acceptance Test"

            with (
                mock.patch.object(mod, "_list_vm_names", return_value=[]),
                mock.patch.object(mod, "_run_osascript", side_effect=fake_run_osascript),
                mock.patch.object(mod, "_patch_config", return_value={}),
                mock.patch.object(mod, "build_vm_info", return_value={"vm_name": "AgentOS Acceptance Test"}),
            ):
                payload = mod.create_vm(
                    vm_name="AgentOS Acceptance Test",
                    iso_path=str(iso_path),
                    disk_size_mib=32768,
                    memory_mib=8192,
                    cpu_cores=4,
                    uefi_boot=True,
                    arch="arm64",
                )

        create_script = "\n".join(script_calls[0])
        self.assertIn('architecture:"aarch64"', create_script)
        self.assertNotIn('target:"virt"', create_script)
        self.assertIn("memory:8192", create_script)
        self.assertIn("cpu cores:4", create_script)
        self.assertIn("hypervisor:true", create_script)
        self.assertIn("uefi:true", create_script)
        self.assertEqual(payload["disk_size_mib"], 32768)
        self.assertTrue(payload["uefi_boot"])
        self.assertEqual(payload["guest_arch"], "arm64")

    def test_info_requires_existing_vm_name(self) -> None:
        proc = subprocess.run(
            ["python3", str(SCRIPT), "info", "--vm-name", "definitely-missing-vm"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("UTM config not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
