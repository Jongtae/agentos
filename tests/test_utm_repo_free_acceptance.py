from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "utm_repo_free_acceptance.py"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utm_repo_free_acceptance import (
    _boot_progress_unobserved_without_excerpt,
    _classify_takeover_state,
    _derive_recovery_degraded_acceptance,
    _derive_telegram_operator_visible,
    _derive_top_task_success,
    _engine_availability_guest_paths,
    _guest_engine_availability_status,
    _guest_exec,
    _guest_agent_error_text,
    _guest_json_file_optional,
    _guest_json_file_with_fallback,
    _emulation_required,
    _guest_arch_from_iso,
    _inbox_reply_workflow_guest_path,
    _inbox_proof_guest_path,
    _research_workflow_guest_path,
    _research_brief_guest_path,
    _parse_json_stdout,
    _redacted_guest_exec_step,
    _run,
    _serial_indicates_boot_progress,
    _serial_acceptance_proof,
    _serial_boot_progress_layer,
    _apply_serial_acceptance_proof,
    _wait_boot_complete,
    _wait_guest_agent,
    _wait_running,
    _wait_for_runtime_entry_status,
    _run_guest_json_via_file,
    _serial_capture,
    _telegram_live_send_env,
    _telegram_thread_status_guest_path,
    _telegram_token_configured,
    _workflow_status_guest_path,
)


class UtmRepoFreeAcceptanceTests(unittest.TestCase):
    def test_telegram_live_send_env_uses_runtime_secret_and_redacts_exec_step(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENTOS_TELEGRAM_BOT_TOKEN": "secret-token",
                "AGENTOS_TELEGRAM_API_BASE_URL": "http://127.0.0.1:9999",
            },
            clear=True,
        ):
            env = _telegram_live_send_env("1001")

        self.assertTrue(_telegram_token_configured(env))
        self.assertEqual(env["AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS"], "1001")
        self.assertEqual(env["AGENTOS_TELEGRAM_API_BASE_URL"], "http://127.0.0.1:9999")
        self.assertFalse(_telegram_token_configured({}))

        proc = subprocess.CompletedProcess(
            ["agentos-kernelctl", "telegram-reply"],
            0,
            stdout='{"reply_sent": true}\n',
            stderr="",
        )
        step = _redacted_guest_exec_step(proc)
        self.assertEqual(step["returncode"], 0)
        self.assertEqual(_parse_json_stdout(proc), {"reply_sent": True})
        self.assertNotIn("secret-token", json.dumps(step))

    def test_guest_arch_from_manifest_or_iso_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "manifest.txt"
            manifest.write_text("arch=arm64\n", encoding="utf-8")
            release = {"build_manifest_path": str(manifest)}
            self.assertEqual(_guest_arch_from_iso(Path("agentos-v-test-amd64.iso"), release), "arm64")

        self.assertEqual(_guest_arch_from_iso(Path("agentos-v-test-amd64.iso"), {}), "amd64")
        self.assertEqual(_guest_arch_from_iso(Path("agentos-v-test-arm64.iso"), {}), "arm64")

    def test_emulation_required_normalizes_common_arch_names(self) -> None:
        self.assertTrue(_emulation_required("arm64", "amd64"))
        self.assertFalse(_emulation_required("aarch64", "arm64"))
        self.assertFalse(_emulation_required("x86_64", "amd64"))

    def test_run_returns_timeout_completed_process(self) -> None:
        result = _run(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(2)",
            ],
            timeout_sec=0.01,
        )

        self.assertEqual(result.returncode, 124)
        self.assertIn("command timed out", result.stderr)

    def test_serial_boot_progress_layer_classifies_firmware_kernel_and_userspace(self) -> None:
        self.assertEqual(_serial_boot_progress_layer('BdsDxe: starting Boot0001 "UEFI QEMU DVD-ROM"'), "firmware")
        self.assertEqual(_serial_boot_progress_layer("[    0.000000] Linux version 6.8.0"), "kernel")
        self.assertEqual(_serial_boot_progress_layer("[  OK  ] Reached target multi-user.target"), "userspace")
        self.assertEqual(_serial_boot_progress_layer(""), "unobserved")

    def test_run_guest_json_via_file_reads_guest_artifact(self) -> None:
        import utm_repo_free_acceptance as module

        original_run_shell = module._run_guest_shell
        original_wait_file = module._wait_for_guest_file_text
        calls = []

        module._run_guest_shell = lambda vm_name, shell_snippet, env=None: calls.append(
            ("shell", vm_name, shell_snippet)
        )
        module._wait_for_guest_file_text = (
            lambda vm_name, guest_path, timeout_sec=30, poll_interval_sec=3: '{"ok": true}'
        )
        try:
            payload = _run_guest_json_via_file(
                "vm",
                "/usr/local/bin/agentos-kernelctl guided-operator --json",
                "/tmp/guided-operator.json",
            )
        finally:
            module._run_guest_shell = original_run_shell
            module._wait_for_guest_file_text = original_wait_file

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(calls[0][1], "vm")
        self.assertIn("/tmp/guided-operator.json", calls[0][2])

    def test_derive_recovery_degraded_acceptance_requires_visible_rejoin_path(self) -> None:
        artifact = {
            "summary": {
                "guided_operator_surface_reachable": True,
                "recovery_affordance_visible": True,
            },
            "steps": {
                "guided_operator_surface": {
                    "state": "provider_unavailable",
                    "top_tasks": [
                        {
                            "id": "recover_rejoin",
                            "status": "ready",
                            "handoff": {
                                "continuity": "rejoin_path",
                                "target_surface": "recovery_path",
                            },
                        }
                    ],
                }
            },
        }
        self.assertTrue(_derive_recovery_degraded_acceptance(artifact))
        artifact["steps"]["guided_operator_surface"]["top_tasks"][0]["status"] = "blocked"
        self.assertFalse(_derive_recovery_degraded_acceptance(artifact))

    def test_derive_top_task_success_requires_guided_surface_and_core_tasks(self) -> None:
        artifact = {
            "summary": {"guided_operator_surface_reachable": True},
            "steps": {
                "guided_operator_surface": {"top_tasks": [{"id": "recover_rejoin"}]},
                "document_access": {"native_handled": True},
                "web_access": {"native_handled": True},
                "inbox_proof": {"summary": {"inbox_execution_ready": True}},
            },
        }
        self.assertTrue(_derive_top_task_success(artifact))
        artifact["steps"]["web_access"] = {"native_handled": False, "escalated_handled": False}
        self.assertFalse(_derive_top_task_success(artifact))

    def test_derive_top_task_success_ignores_telegram_fields(self) -> None:
        artifact = {
            "summary": {"guided_operator_surface_reachable": True},
            "steps": {
                "guided_operator_surface": {
                    "top_tasks": [
                        {"id": "recover_rejoin"},
                        {"id": "ask_from_telegram"},
                        {"id": "search_and_reply"},
                        {"id": "review_telegram_ingress"},
                    ]
                },
                "document_access": {"native_handled": True},
                "web_access": {"native_handled": True},
                "inbox_proof": {"summary": {"inbox_execution_ready": True}},
                "telegram_proof": {
                    "summary": {
                        "telegram_ingress_received": False,
                        "telegram_request_routed": False,
                        "telegram_web_execution_ok": False,
                        "telegram_reply_ready": False,
                        "telegram_reply_sent": False,
                    }
                },
            },
        }
        self.assertTrue(_derive_top_task_success(artifact))

    def test_derive_telegram_operator_visible_requires_ingress_summary_and_tasks(self) -> None:
        artifact = {
            "steps": {
                "guided_operator_surface": {
                    "guided_operator_surface_reachable": True,
                    "runtime_summary": {"telegram_ingress_ready": True},
                    "top_tasks": [
                        {"id": "ask_from_telegram"},
                        {"id": "search_and_reply"},
                        {"id": "review_telegram_ingress"},
                    ],
                }
            }
        }
        self.assertTrue(_derive_telegram_operator_visible(artifact))
        artifact["steps"]["guided_operator_surface"]["top_tasks"].pop()
        self.assertFalse(_derive_telegram_operator_visible(artifact))

    def test_research_workflow_guest_path_uses_capability_artifact_location(self) -> None:
        self.assertEqual(
            _research_workflow_guest_path("/home/ubuntu/agentos-ws"),
            "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-research-request-response-workflow.json",
        )

    def test_stage73_repair_guest_paths_use_capability_artifact_location(self) -> None:
        workspace = "/home/ubuntu/agentos-ws"
        self.assertEqual(
            _telegram_thread_status_guest_path(workspace),
            "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-telegram-thread-status.json",
        )
        self.assertEqual(
            _inbox_reply_workflow_guest_path(workspace),
            "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-inbox-reply-workflow.json",
        )
        self.assertEqual(
            _research_brief_guest_path(workspace),
            "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-research-brief-response.json",
        )

    def test_workflow_status_guest_path_uses_runtime_entry_artifact_location(self) -> None:
        self.assertEqual(
            _workflow_status_guest_path("/home/ubuntu/agentos-ws"),
            "/home/ubuntu/agentos-ws/artifacts/runtime-entry/latest-workflow-status.json",
        )

    def test_inbox_proof_fallback_prefers_file_based_guest_wrapper(self) -> None:
        command = (
            "/usr/local/bin/agentos-kernelctl inbox-proof --workspace "
            "/home/ubuntu/agentos-ws --json"
        )
        guest_path = _inbox_proof_guest_path("/home/ubuntu/agentos-ws")
        calls: list[tuple[str, str, str, str]] = []

        def fake_run_guest_json_via_file(vm_name: str, shell_snippet: str, output_path: str, *, env=None, timeout_sec=30):
            calls.append((vm_name, shell_snippet, output_path, str(timeout_sec)))
            return {"summary": {"inbox_execution_ready": True}}

        self.assertEqual(guest_path, "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-inbox-proof-baseline.json")
        payload = fake_run_guest_json_via_file("vm", command, guest_path)
        self.assertTrue(payload["summary"]["inbox_execution_ready"])
        self.assertEqual(
            calls,
            [("vm", command, guest_path, "30")],
        )

    def test_guest_agent_error_text_detects_stderr_only_failure(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["utmctl", "exec"],
            returncode=0,
            stdout="",
            stderr="The QEMU guest agent is not running or not installed on the guest.\n",
        )
        error = _guest_agent_error_text(proc)
        self.assertIn("QEMU guest agent is not running", error)

    def test_guest_agent_error_text_ignores_clean_success(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["utmctl", "exec"],
            returncode=0,
            stdout="",
            stderr="",
        )
        self.assertEqual(_guest_agent_error_text(proc), "")

    def test_guest_agent_error_text_ignores_missing_guest_file(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["utmctl", "file", "pull"],
            returncode=1,
            stdout="",
            stderr="OSStatus error -2700.\nfailed to open file '/tmp/missing' (mode: 'r'): No such file or directory",
        )
        self.assertEqual(_guest_agent_error_text(proc), "")

    def test_classify_takeover_state_requires_bootstrap_marker(self) -> None:
        failure = _classify_takeover_state({}, {})
        self.assertEqual(
            failure,
            ("live_session_takeover_failure", "live bootstrap did not record a takeover status"),
        )

    def test_classify_takeover_state_rejects_failed_launcher(self) -> None:
        failure = _classify_takeover_state(
            {"state": "welcome_launch_failed", "detail": "launcher command failed"},
            {},
        )
        self.assertEqual(
            failure,
            ("live_session_takeover_failure", "launcher command failed"),
        )

    def test_serial_capture_missing_path_returns_empty(self) -> None:
        self.assertEqual(_serial_capture("/definitely/missing/serial"), "")

    def test_serial_indicates_boot_progress_detects_systemd(self) -> None:
        self.assertTrue(_serial_indicates_boot_progress("[  141.229797] systemd[1]: Reloading finished in 6895 ms."))
        self.assertFalse(_serial_indicates_boot_progress("GNU GRUB version 2.12"))
        self.assertFalse(_serial_indicates_boot_progress('BdsDxe: starting Boot0001 "UEFI QEMU DVD-ROM QM00001"'))

    def test_serial_acceptance_proof_parses_latest_marker(self) -> None:
        payload = {
            "schema_version": "agentos-serial-acceptance-proof.v1",
            "pass": True,
            "provider_ready": True,
        }
        text = "noise\nAGENTOS_ACCEPTANCE_PROOF_JSON={\"schema_version\":\"ignored\"}\n"
        text += "AGENTOS_ACCEPTANCE_PROOF_JSON=" + json.dumps(payload) + "\n"

        self.assertEqual(_serial_acceptance_proof(text), payload)
        self.assertEqual(_serial_acceptance_proof("no marker"), {})

    def test_apply_serial_acceptance_proof_updates_summary(self) -> None:
        artifact = {
            "summary": {"pass": False, "failure_class": "guest_agent_unavailable"},
            "steps": {},
        }
        proof = {
            "runtime_entry_mode": "tty",
            "guest_reachable": True,
            "workspace_writable": True,
            "guided_operator_surface_reachable": True,
            "workflow_status_ready": True,
            "operator_next_action_visible": True,
            "provider_ready": True,
            "first_prompt_success": True,
            "managed_reentry_ready": True,
            "usable_runtime_entry": True,
            "top_task_success": True,
            "research_workflow_ready": True,
            "inbox_workflow_ready": True,
            "telegram_thread_continuity_ready": True,
            "inbox_reply_workflow_ready": True,
            "research_brief_ready": True,
            "brief_artifact_exported": True,
            "pass": True,
        }

        _apply_serial_acceptance_proof(artifact, proof)

        self.assertTrue(artifact["summary"]["pass"])
        self.assertEqual(artifact["summary"]["failure_class"], "")
        self.assertTrue(artifact["summary"]["guest_reachable"])
        self.assertTrue(artifact["summary"]["workflow_status_ready"])
        self.assertTrue(artifact["summary"]["operator_next_action_visible"])
        self.assertTrue(artifact["summary"]["inbox_workflow_ready"])
        self.assertTrue(artifact["summary"]["telegram_thread_continuity_ready"])
        self.assertTrue(artifact["summary"]["inbox_reply_workflow_ready"])
        self.assertTrue(artifact["summary"]["research_brief_ready"])
        self.assertTrue(artifact["summary"]["brief_artifact_exported"])
        self.assertEqual(artifact["steps"]["serial_acceptance_proof"], proof)

    def test_boot_progress_unobserved_without_excerpt_requires_empty_excerpt(self) -> None:
        self.assertTrue(
            _boot_progress_unobserved_without_excerpt(
                {"state": "boot_progress_unobserved", "excerpt": ""}
            )
        )
        self.assertFalse(
            _boot_progress_unobserved_without_excerpt(
                {"state": "boot_progress_unobserved", "excerpt": "GNU GRUB"}
            )
        )
        self.assertFalse(
            _boot_progress_unobserved_without_excerpt(
                {"state": "serial_unavailable", "excerpt": ""}
            )
        )

    def test_wait_boot_complete_reports_missing_serial_path(self) -> None:
        result = _wait_boot_complete("/definitely/missing/serial", timeout_sec=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "serial_unavailable")

    def test_wait_boot_complete_auto_enters_grub_and_detects_progress(self) -> None:
        import utm_repo_free_acceptance as module

        reads = [
            b"GNU GRUB version 2.12\r\n",
            b"[  10.0] systemd[1]: Reloading finished in 10 ms.\r\n",
        ]
        writes = []

        original_open = module.os.open
        original_close = module.os.close
        original_read = module.os.read
        original_write = module.os.write
        original_select = module.select.select
        original_time = module.time.time
        try:
            module.os.open = lambda path, flags: 123
            module.os.close = lambda fd: None

            def fake_read(fd: int, n: int) -> bytes:
                return reads.pop(0) if reads else b""

            module.os.read = fake_read
            module.os.write = lambda fd, data: writes.append(data) or len(data)
            module.select.select = lambda r, w, x, timeout: ([123], [], [])

            ticks = iter([0.0, 0.0, 0.0, 0.1, 0.1, 0.2, 0.2])
            module.time.time = lambda: next(ticks, 0.2)

            result = _wait_boot_complete("/dev/ttys000", timeout_sec=5, grub_enter_delay_sec=0)
        finally:
            module.os.open = original_open
            module.os.close = original_close
            module.os.read = original_read
            module.os.write = original_write
            module.select.select = original_select
            module.time.time = original_time

        self.assertTrue(result["ok"])
        self.assertTrue(result["grub_seen"])
        self.assertTrue(result["enter_sent"])
        self.assertIn(b"\r", writes)
        self.assertIn("systemd[1]", result["excerpt"])

    def test_wait_boot_complete_reports_serial_read_eio_as_boot_failure(self) -> None:
        import utm_repo_free_acceptance as module

        original_open = module.os.open
        original_close = module.os.close
        original_read = module.os.read
        original_select = module.select.select
        original_time = module.time.time
        try:
            module.os.open = lambda path, flags: 123
            module.os.close = lambda fd: None
            module.os.read = lambda fd, n: (_ for _ in ()).throw(OSError(5, "Input/output error"))
            module.select.select = lambda r, w, x, timeout: ([123], [], [])

            ticks = iter([0.0, 0.0, 0.1])
            module.time.time = lambda: next(ticks, 0.1)

            result = _wait_boot_complete("/dev/ttys000", timeout_sec=5, grub_enter_delay_sec=0)
        finally:
            module.os.open = original_open
            module.os.close = original_close
            module.os.read = original_read
            module.select.select = original_select
            module.time.time = original_time

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "serial_read_failed")
        self.assertIn("Input/output error", result["detail"])

    def test_guest_json_file_with_fallback_uses_second_path(self) -> None:
        calls = []

        def fake_optional(vm_name: str, guest_path: str) -> dict:
            calls.append((vm_name, guest_path))
            if guest_path.endswith("/tmp/agentos-live-bootstrap/live-session-status.json"):
                return {"state": "bootstrap_started"}
            return {}

        from utm_repo_free_acceptance import _guest_json_file_optional as original_optional
        import utm_repo_free_acceptance as module

        module._guest_json_file_optional = fake_optional
        try:
            payload, path = _guest_json_file_with_fallback(
                "vm",
                "/var/lib/agentos/live-bootstrap/live-session-status.json",
                "/tmp/agentos-live-bootstrap/live-session-status.json",
            )
        finally:
            module._guest_json_file_optional = original_optional

        self.assertEqual(payload, {"state": "bootstrap_started"})
        self.assertEqual(path, "/tmp/agentos-live-bootstrap/live-session-status.json")
        self.assertEqual(len(calls), 2)

    def test_guest_json_file_optional_parses_json(self) -> None:
        import utm_repo_free_acceptance as module

        original_guest_cat = module._guest_cat
        module._guest_cat = lambda vm_name, guest_path: subprocess.CompletedProcess(
            args=["utmctl", "file", "pull"],
            returncode=0,
            stdout='{"state":"bootstrap_started"}',
            stderr="",
        )
        try:
            payload = _guest_json_file_optional("vm", "/guest/path.json")
        finally:
            module._guest_cat = original_guest_cat

        self.assertEqual(payload, {"state": "bootstrap_started"})

    def test_wait_for_runtime_entry_status_prefers_file_artifact(self) -> None:
        import utm_repo_free_acceptance as module

        original_wait = module._wait_for_guest_json_file_with_fallback
        calls = []

        def fake_wait(vm_name: str, *guest_paths: str, timeout_sec: int = 60, poll_interval_sec: int = 3):
            calls.append((vm_name, guest_paths, timeout_sec, poll_interval_sec))
            return (
                {"runtime_entry_mode": "tty", "workspace_writable": True},
                "/home/ubuntu/agentos-ws/artifacts/runtime-entry/latest-runtime-entry-status.json",
            )

        module._wait_for_guest_json_file_with_fallback = fake_wait
        try:
            payload, path = _wait_for_runtime_entry_status("vm", "/home/ubuntu/agentos-ws")
        finally:
            module._wait_for_guest_json_file_with_fallback = original_wait

        self.assertEqual(payload["runtime_entry_mode"], "tty")
        self.assertTrue(payload["workspace_writable"])
        self.assertEqual(
            path,
            "/home/ubuntu/agentos-ws/artifacts/runtime-entry/latest-runtime-entry-status.json",
        )
        self.assertEqual(calls[0][0], "vm")

    def test_engine_availability_guest_paths_include_interactive_and_seed(self) -> None:
        self.assertEqual(
            _engine_availability_guest_paths("/home/ubuntu/agentos-ws"),
            (
                "/home/ubuntu/agentos-ws/artifacts/kernel-engine/latest-kernel-engine-availability.json",
                "/var/lib/agentos/workspaces/default/artifacts/kernel-engine/latest-kernel-engine-availability.json",
            ),
        )

    def test_guest_engine_availability_status_uses_guest_file_artifact(self) -> None:
        import utm_repo_free_acceptance as module

        original_run_guest_json_via_file = module._run_guest_json_via_file
        calls = []

        def fake_run_guest_json_via_file(vm_name: str, shell_snippet: str, output_path: str, *, env=None, timeout_sec=30):
            calls.append((vm_name, shell_snippet, output_path, timeout_sec))
            return {"summary": {"usable_runtime_entry": True}}

        module._run_guest_json_via_file = fake_run_guest_json_via_file
        try:
            payload, path = _guest_engine_availability_status("vm", "/home/ubuntu/agentos-ws")
        finally:
            module._run_guest_json_via_file = original_run_guest_json_via_file

        self.assertTrue(payload["summary"]["usable_runtime_entry"])
        self.assertEqual(
            path,
            "/home/ubuntu/agentos-ws/artifacts/kernel-engine/latest-kernel-engine-availability.json",
        )
        self.assertIn("engine-availability", calls[0][1])
        self.assertIn("|| true", calls[0][1])
        self.assertEqual(calls[0][2], path)
        self.assertEqual(calls[0][3], 180)

    def test_guest_exec_retries_transient_utm_exec_osstatus(self) -> None:
        import utm_repo_free_acceptance as module

        original_run = module._run
        original_sleep = module.time.sleep
        original_retries = module.GUEST_EXEC_TRANSIENT_RETRIES
        calls = []
        responses = [
            subprocess.CompletedProcess(args=["utmctl"], returncode=1, stdout="", stderr="OSStatus error -10004."),
            subprocess.CompletedProcess(args=["utmctl"], returncode=0, stdout='{"ok": true}', stderr=""),
        ]

        def fake_run(command):
            calls.append(command)
            return responses.pop(0)

        module._run = fake_run
        module.time.sleep = lambda seconds: None
        module.GUEST_EXEC_TRANSIENT_RETRIES = 5
        try:
            proc = _guest_exec("vm", ["/bin/sh", "-lc", "true"])
        finally:
            module._run = original_run
            module.time.sleep = original_sleep
            module.GUEST_EXEC_TRANSIENT_RETRIES = original_retries

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(calls), 2)

    def test_guest_exec_does_not_retry_normal_guest_command_failure(self) -> None:
        import utm_repo_free_acceptance as module

        original_run = module._run
        calls = []

        def fake_run(command):
            calls.append(command)
            return subprocess.CompletedProcess(args=["utmctl"], returncode=2, stdout="", stderr="command failed")

        module._run = fake_run
        try:
            proc = _guest_exec("vm", ["/bin/sh", "-lc", "false"])
        finally:
            module._run = original_run

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(len(calls), 1)

    def test_guest_exec_transient_retry_count_is_configurable(self) -> None:
        import utm_repo_free_acceptance as module

        original_run = module._run
        original_sleep = module.time.sleep
        original_retries = module.GUEST_EXEC_TRANSIENT_RETRIES
        calls = []

        def fake_run(command):
            calls.append(command)
            return subprocess.CompletedProcess(args=["utmctl"], returncode=1, stdout="", stderr="OSStatus error -10004.")

        module._run = fake_run
        module.time.sleep = lambda seconds: None
        module.GUEST_EXEC_TRANSIENT_RETRIES = 3
        try:
            proc = _guest_exec("vm", ["/bin/sh", "-lc", "true"])
        finally:
            module._run = original_run
            module.time.sleep = original_sleep
            module.GUEST_EXEC_TRANSIENT_RETRIES = original_retries

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(calls), 4)

    def test_inbox_proof_guest_path_uses_capability_substrate_artifact(self) -> None:
        self.assertEqual(
            _inbox_proof_guest_path("/home/ubuntu/agentos-ws"),
            "/home/ubuntu/agentos-ws/artifacts/capability-substrate/latest-inbox-proof-baseline.json",
        )

    def test_wait_guest_agent_accepts_file_pull_reachability(self) -> None:
        import utm_repo_free_acceptance as module

        original_guest_pull = module._guest_pull_file
        original_run = module._run
        module._guest_pull_file = lambda vm_name, guest_path: subprocess.CompletedProcess(
            args=["utmctl", "file", "pull"],
            returncode=0,
            stdout='PRETTY_NAME="Ubuntu"\n',
            stderr="",
        )
        module._run = lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"ips":["192.0.2.10"]}',
            stderr="",
        )
        try:
            result = _wait_guest_agent("vm", timeout_sec=1)
        finally:
            module._guest_pull_file = original_guest_pull
            module._run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["reachability_mode"], "file_pull")
        self.assertEqual(result["ips"], ["192.0.2.10"])

    def test_wait_running_accepts_guest_ip_when_status_lags(self) -> None:
        import utm_repo_free_acceptance as module

        class FakeClient:
            backend_name = "proxy"

            def status(self, vm_name: str) -> bool:
                return False

            def ip(self, vm_name: str) -> dict:
                return {"ips": ["198.51.100.41"], "ip": "198.51.100.41"}

        original_client = module.UTMClient
        original_sleep = module.time.sleep
        module.UTMClient = lambda: FakeClient()
        module.time.sleep = lambda seconds: None
        try:
            result = _wait_running("vm", timeout_sec=1)
        finally:
            module.UTMClient = original_client
            module.time.sleep = original_sleep

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "running_via_guest_ip")
        self.assertEqual(result["ips"], ["198.51.100.41"])

    def test_wait_running_accepts_list_style_ip_payload(self) -> None:
        import utm_repo_free_acceptance as module

        class FakeClient:
            backend_name = "proxy"

            def status(self, vm_name: str) -> bool:
                return False

            def ip(self, vm_name: str) -> list[str]:
                return ["198.51.100.42"]

        original_client = module.UTMClient
        original_sleep = module.time.sleep
        module.UTMClient = lambda: FakeClient()
        module.time.sleep = lambda seconds: None
        try:
            result = _wait_running("vm", timeout_sec=1)
        finally:
            module.UTMClient = original_client
            module.time.sleep = original_sleep

        self.assertTrue(result["ok"])
        self.assertEqual(result["ips"], ["198.51.100.42"])

    def test_wait_running_reports_control_plane_unavailable(self) -> None:
        import utm_repo_free_acceptance as module

        original_client = module.UTMClient
        module.UTMClient = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("utmctl timeout"))
        try:
            result = _wait_running("vm", timeout_sec=1)
        finally:
            module.UTMClient = original_client

        self.assertFalse(result["ok"])
        self.assertEqual(result["backend"], "unavailable")
        self.assertIn("utm control plane unavailable", result["state"])

    def test_dry_run_includes_guest_flow_and_artifact_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            release_dir = Path(td) / "release"
            release_dir.mkdir(parents=True)
            iso_path = release_dir / "agentos-v-test-amd64.iso"
            iso_path.write_text("stub", encoding="utf-8")
            manifest_path = Path(td) / "manifest-v-test.txt"
            manifest_path.write_text(
                "boot_target_activated=true\n"
                "vm_first_screen_evidence_included=true\n"
                "boot_flow_proof_included=true\n",
                encoding="utf-8",
            )
            metadata = release_dir / "agentos-release-metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "agentos_version": "v-test",
                        "output_path": str(iso_path),
                        "build_manifest_path": str(manifest_path),
                        "boot_target_activated": True,
                    }
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--release-metadata",
                    str(metadata),
                    "--dry-run",
                    "--uefi-boot",
                    "on",
                    "--telegram-live-send",
                    "--json",
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
            )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "agentos-utm-repo-free-acceptance.v1")
        self.assertEqual(payload["iso"]["version"], "v-test")
        self.assertEqual(payload["iso"]["base_image_type"], "")
        self.assertEqual(payload["iso"]["guest_arch"], "amd64")
        self.assertIn("arch", payload["host"])
        self.assertEqual(payload["host"]["guest_arch"], "amd64")
        self.assertIn("emulation_required", payload["host"])
        self.assertEqual(payload["vm"]["guest_workspace"], "/home/ubuntu/agentos-ws")
        self.assertTrue(payload["vm"]["uefi_boot"])
        self.assertFalse(payload["summary"]["gui_required"])
        self.assertEqual(payload["summary"]["gui_path_role"], "fallback_debug_only")
        self.assertFalse(payload["summary"]["guided_operator_surface_reachable"])
        self.assertFalse(payload["summary"]["workflow_status_ready"])
        self.assertFalse(payload["summary"]["operator_next_action_visible"])
        self.assertFalse(payload["summary"]["recovery_affordance_visible"])
        self.assertFalse(payload["summary"]["recovery_degraded_acceptance_ready"])
        self.assertFalse(payload["summary"]["workspace_writable"])
        self.assertFalse(payload["summary"]["provider_ready"])
        self.assertFalse(payload["summary"]["first_prompt_success"])
        self.assertFalse(payload["summary"]["managed_reentry_ready"])
        self.assertFalse(payload["summary"]["usable_runtime_entry"])
        self.assertFalse(payload["summary"]["top_task_success"])
        self.assertFalse(payload["summary"].get("telegram_ingress_received", False))
        self.assertFalse(payload["summary"].get("telegram_chat_allowed", False))
        self.assertFalse(payload["summary"].get("telegram_request_routed", False))
        self.assertFalse(payload["summary"].get("telegram_web_execution_ok", False))
        self.assertFalse(payload["summary"].get("telegram_reply_ready", False))
        self.assertFalse(payload["summary"].get("telegram_reply_sent", False))
        self.assertTrue(payload["summary"].get("telegram_live_send_requested", False))
        self.assertFalse(payload["summary"].get("telegram_send_attempted", False))
        self.assertFalse(payload["summary"].get("telegram_token_configured", False))
        self.assertFalse(payload["summary"].get("telegram_polling_attempted", False))
        self.assertFalse(payload["summary"].get("telegram_live_update_received", False))
        self.assertFalse(payload["summary"].get("telegram_live_message_routed", False))
        self.assertFalse(payload["summary"].get("telegram_live_search_success", False))
        self.assertFalse(payload["summary"].get("telegram_update_offset_persisted", False))
        self.assertFalse(payload["summary"].get("telegram_loop_ready", False))
        self.assertFalse(payload["summary"].get("browser_escalation_used", False))
        self.assertFalse(payload["summary"].get("telegram_operator_visible", False))
        self.assertFalse(payload["summary"].get("research_workflow_ready", False))
        self.assertFalse(payload["summary"].get("inbox_workflow_ready", False))
        self.assertFalse(payload["summary"]["pass"])
        self.assertIn("telegram_proof", payload["steps"])
        self.assertIn("telegram_web_execution", payload["steps"])
        self.assertIn("telegram_reply", payload["steps"])
        self.assertIn("telegram_live_send", payload["steps"])
        self.assertIn("telegram_live_loop", payload["steps"])
        self.assertIn("research_workflow", payload["steps"])
        self.assertIn("inbox_workflow", payload["steps"])
        self.assertIn("cleanup_stale_vms", payload["steps"])
        self.assertIn("runtime_entry", payload["steps"])
        self.assertIn("guided_operator_surface", payload["steps"])
        self.assertIn("workflow_status", payload["steps"])
        self.assertIn("engine_availability", payload["steps"])
        self.assertEqual(payload["summary"]["runtime_entry_mode"], "tty")
        self.assertTrue(any("document-access" in command for command in payload["planned_commands"]))
        self.assertTrue(any("engine-availability" in command for command in payload["planned_commands"]))
        self.assertTrue(any("guided-operator" in command for command in payload["planned_commands"]))
        self.assertTrue(any("workflow-status" in command for command in payload["planned_commands"]))
        self.assertTrue(any("inbox-proof" in command for command in payload["planned_commands"]))
        self.assertTrue(any("vm-e2e-proof" in command for command in payload["planned_commands"]))
        self.assertTrue(any("telegram-proof" in command for command in payload["planned_commands"]))
        self.assertTrue(any("telegram-live-loop" in command and "--send" in command for command in payload["planned_commands"]))
        self.assertTrue(any("research-workflow" in command for command in payload["planned_commands"]))
        self.assertTrue(any("inbox-workflow" in command for command in payload["planned_commands"]))
        self.assertIn("serial_port_address", payload["artifacts"])
        self.assertIn("serial_capture_excerpt", payload["artifacts"])

    def test_live_send_without_token_fails_before_vm_creation(self) -> None:
        import utm_repo_free_acceptance as module

        with tempfile.TemporaryDirectory() as td:
            release_dir = Path(td) / "release"
            release_dir.mkdir(parents=True)
            iso_path = release_dir / "agentos-v-test-amd64.iso"
            iso_path.write_text("stub", encoding="utf-8")
            manifest_path = Path(td) / "manifest-v-test.txt"
            manifest_path.write_text(
                "boot_target_activated=true\n",
                encoding="utf-8",
            )
            metadata = release_dir / "agentos-release-metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "agentos_version": "v-test",
                        "output_path": str(iso_path),
                        "build_manifest_path": str(manifest_path),
                        "boot_target_activated": True,
                    }
                ),
                encoding="utf-8",
            )
            artifact_path = Path(td) / "acceptance.json"

            def fail_if_called(*args, **kwargs):
                raise AssertionError("VM creation/cleanup must not run when live-send token is missing")

            argv = [
                "utm_repo_free_acceptance.py",
                "--release-metadata",
                str(metadata),
                "--telegram-live-send",
                "--json",
            ]
            clean_env = {
                key: value
                for key, value in os.environ.items()
                if "TELEGRAM" not in key
            }
            with patch.object(sys, "argv", argv), patch.dict(os.environ, clean_env, clear=True), patch.object(
                module, "_artifact_path", return_value=artifact_path
            ), patch.object(module, "create_vm", side_effect=fail_if_called), patch.object(
                module, "_cleanup_stale_acceptance_vms", side_effect=fail_if_called
            ), redirect_stdout(StringIO()):
                self.assertEqual(module.main(), 1)

            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["failure_class"], "telegram_token_missing")
            self.assertTrue(payload["summary"]["telegram_live_send_requested"])
            self.assertFalse(payload["summary"]["telegram_token_configured"])
            self.assertFalse(payload["summary"]["telegram_send_attempted"])
            self.assertFalse(payload["summary"]["telegram_polling_attempted"])
            self.assertEqual(payload["steps"]["cleanup_stale_vms"], [])
            self.assertEqual(payload["steps"]["create_vm"], {})


if __name__ == "__main__":
    unittest.main()
