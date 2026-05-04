#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import select
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utm_client import UTMClient, UTMError
from utm_disposable_vm import UTM_DOCUMENTS_DIR, _list_vm_names, create_vm, default_vm_name, force_delete_vm

SCHEMA_VERSION = "agentos-utm-repo-free-acceptance.v1"
DEFAULT_GUEST_WORKSPACE = os.environ.get("AGENTOS_DEFAULT_WORKSPACE", "/home/ubuntu/agentos-ws")
DEFAULT_SEED_WORKSPACE = os.environ.get("AGENTOS_SEED_WORKSPACE", "/var/lib/agentos/workspaces/default")
DEFAULT_DOCUMENT_PATH = "documents/agentos-first-run.md"
DEFAULT_WEB_URL = "https://example.com"
UTM_APPLESCRIPT_REF = 'application id "com.utmapp.UTM"'
GUEST_EXEC_TRANSIENT_RETRIES = int(os.environ.get("AGENTOS_UTM_GUEST_EXEC_TRANSIENT_RETRIES", "24"))
GUEST_EXEC_TRANSIENT_DELAY_SEC = int(os.environ.get("AGENTOS_UTM_GUEST_EXEC_TRANSIENT_DELAY_SEC", "5"))
UTM_CONTROL_COMMAND_TIMEOUT_SEC = int(os.environ.get("AGENTOS_UTM_CONTROL_COMMAND_TIMEOUT_SEC", "30"))
UTM_APPLESCRIPT_TIMEOUT_SEC = int(os.environ.get("AGENTOS_UTM_APPLESCRIPT_TIMEOUT_SEC", "180"))


class AcceptanceError(RuntimeError):
    pass


class AcceptanceComplete(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_root() -> Path:
    path = ROOT_DIR / "workspaces" / "default" / "artifacts" / "utm-acceptance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_path(name: str) -> Path:
    return _artifact_root() / name


def _run(command: list[str], *, timeout_sec: int | None = None) -> subprocess.CompletedProcess[str]:
    timeout = UTM_CONTROL_COMMAND_TIMEOUT_SEC if timeout_sec is None else timeout_sec
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        detail = f"command timed out after {timeout}s: {' '.join(command)}"
        return subprocess.CompletedProcess(command, 124, stdout or "", (stderr + "\n" + detail).strip())


def _latest_release_metadata() -> Path:
    candidate = ROOT_DIR / "build-output" / "release" / "agentos-release-metadata.json"
    if candidate.is_file():
        return candidate
    raise AcceptanceError(f"release metadata not found: {candidate}")


def _manifest_value(path: Path, key: str, default: str = "") -> str:
    if not path.is_file():
        return default
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return default


def _host_arch() -> str:
    return platform.machine() or "unknown"


def _guest_arch_from_iso(path: Path, release: dict) -> str:
    manifest_path = Path(str(release.get("build_manifest_path", "")))
    manifest_arch = _manifest_value(manifest_path, "arch", "")
    if manifest_arch:
        return manifest_arch
    name = path.name
    for arch in ("amd64", "arm64", "aarch64", "x86_64"):
        if f"-{arch}." in name or name.endswith(f"-{arch}.iso"):
            return arch
    return str(release.get("arch", "") or "unknown")


def _emulation_required(host_arch: str, guest_arch: str) -> bool:
    normalized_host = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}.get(host_arch, host_arch)
    normalized_guest = {"x86_64": "amd64", "aarch64": "arm64"}.get(guest_arch, guest_arch)
    if normalized_host == "unknown" or normalized_guest == "unknown":
        return False
    return normalized_host != normalized_guest


def _load_release_identity(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest_path = Path(str(payload.get("build_manifest_path", "")))
    payload["manifest_boot_target_activated"] = _manifest_value(manifest_path, "boot_target_activated", "false") == "true"
    payload["manifest_vm_first_screen_evidence_included"] = _manifest_value(manifest_path, "vm_first_screen_evidence_included", "false") == "true"
    payload["manifest_boot_flow_proof_included"] = _manifest_value(manifest_path, "boot_flow_proof_included", "false") == "true"
    payload["manifest_base_image_type"] = _manifest_value(
        manifest_path,
        "base_image_type",
        str(payload.get("base_image_type", "")),
    )
    return payload


def _osascript(lines: list[str]) -> str:
    command = ["osascript"]
    for line in lines:
        command.extend(["-e", line])
    proc = subprocess.CompletedProcess(command, 1, "", "")
    error_text = ""
    for attempt in range(5):
        proc = _run(command, timeout_sec=UTM_APPLESCRIPT_TIMEOUT_SEC)
        error_text = proc.stderr.strip() or proc.stdout.strip()
        if proc.returncode == 0:
            break
        if "Application isn’t running. (-600)" not in error_text:
            break
        _run(["open", "-a", "UTM"])
        _run(["osascript", "-e", f"tell {UTM_APPLESCRIPT_REF} to activate"])
        time.sleep(2 + attempt)
    if proc.returncode != 0:
        raise AcceptanceError(error_text or "osascript failed")
    return proc.stdout.strip()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def start_disposable(vm_name: str) -> None:
    apple_error = ""
    try:
        _osascript(
            [
                f"tell {UTM_APPLESCRIPT_REF}",
                f'start virtual machine named "{_escape(vm_name)}" without saving',
                "end tell",
            ]
        )
        return
    except Exception as exc:
        apple_error = str(exc)
    for backend in ("utmctl", None):
        try:
            UTMClient(backend=backend).start(vm_name)
            return
        except Exception:
            pass
    raise AcceptanceError(apple_error or f"unable to start disposable VM: {vm_name}")


def restart_disposable(vm_name: str) -> None:
    _osascript(
        [
            f"tell {UTM_APPLESCRIPT_REF}",
            f'try\nstop virtual machine named "{_escape(vm_name)}" by force\nend try',
            f'try\nstop virtual machine named "{_escape(vm_name)}" by kill\nend try',
            "end tell",
        ]
    )
    time.sleep(5)
    start_disposable(vm_name)


def _guest_exec(vm_name: str, command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    utmctl = "/Applications/UTM.app/Contents/MacOS/utmctl"
    cmd = [utmctl, "exec", "--hide", vm_name]
    for key, value in (env or {}).items():
        cmd.extend(["--env", f"{key}={value}"])
    cmd.extend(["--cmd", *command])
    last = _run(cmd)
    for _ in range(max(0, GUEST_EXEC_TRANSIENT_RETRIES)):
        text = "\n".join(part for part in [last.stdout, last.stderr] if part)
        if last.returncode == 0 or "OSStatus error -10004" not in text:
            return last
        time.sleep(max(0, GUEST_EXEC_TRANSIENT_DELAY_SEC))
        last = _run(cmd)
    return last


def _guest_pull_file(vm_name: str, guest_path: str) -> subprocess.CompletedProcess[str]:
    utmctl = "/Applications/UTM.app/Contents/MacOS/utmctl"
    return _run([utmctl, "file", "pull", "--hide", vm_name, guest_path])


def _guest_agent_error_text(proc: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
    lowered = text.lower()
    if "failed to open file" in lowered and "no such file or directory" in lowered:
        return ""
    markers = (
        "qemu guest agent is not running or not installed on the guest",
        "qemu-guest-agent",
        "qemu guest agent",
    )
    if any(marker in lowered for marker in markers):
        return text[-1000:]
    return ""


def _guest_cat(vm_name: str, guest_path: str) -> subprocess.CompletedProcess[str]:
    return _guest_pull_file(vm_name, guest_path)


def _wait_running(vm_name: str, *, timeout_sec: int) -> dict:
    try:
        client = UTMClient(backend="utmctl")
    except Exception as first_exc:
        try:
            client = UTMClient()
        except Exception as fallback_exc:
            return {
                "ok": False,
                "state": f"utm control plane unavailable: {first_exc}; fallback unavailable: {fallback_exc}",
                "backend": "unavailable",
            }
    deadline = time.time() + timeout_sec
    last_state = "starting"
    while time.time() < deadline:
        try:
            running = client.status(vm_name)
            ip_payload = client.ip(vm_name)
            if isinstance(ip_payload, dict):
                ips = list(ip_payload.get("ips", []) or [])
            else:
                ips = list(ip_payload or [])
            if running or ips:
                state = "running" if running else "running_via_guest_ip"
                return {
                    "ok": True,
                    "state": state,
                    "backend": client.backend_name,
                    "ips": ips,
                }
            last_state = "stopped"
        except UTMError as exc:
            last_state = str(exc)
        time.sleep(2)
    return {"ok": False, "state": last_state, "backend": client.backend_name}


def _derive_top_task_success(artifact: dict) -> bool:
    summary = dict(artifact.get("summary") or {})
    steps = dict(artifact.get("steps") or {})
    guided = dict(steps.get("guided_operator_surface") or {})
    document_access = dict(steps.get("document_access") or {})
    web_access = dict(steps.get("web_access") or {})
    inbox_proof = dict(steps.get("inbox_proof") or {})
    if not summary.get("guided_operator_surface_reachable", False):
        return False
    document_ok = bool(document_access.get("native_handled", False))
    web_ok = bool(web_access.get("native_handled", False) or web_access.get("escalated_handled", False))
    inbox_ok = bool(inbox_proof.get("summary", {}).get("inbox_execution_ready", False))
    top_tasks = list(guided.get("top_tasks") or [])
    has_recover_task = any(task.get("id") == "recover_rejoin" for task in top_tasks)
    return bool(document_ok and web_ok and inbox_ok and has_recover_task)


def _derive_recovery_degraded_acceptance(artifact: dict) -> bool:
    summary = dict(artifact.get("summary") or {})
    guided = dict((artifact.get("steps") or {}).get("guided_operator_surface") or {})
    if not summary.get("guided_operator_surface_reachable", False):
        return False
    if not summary.get("recovery_affordance_visible", False):
        return False
    state = str(guided.get("state", "")).strip()
    if state not in {
        "runtime_ready",
        "runtime_degraded",
        "workspace_blocked",
        "provider_unavailable",
        "proof_export_unavailable",
    }:
        return False
    top_tasks = list(guided.get("top_tasks") or [])
    recover_task = next((task for task in top_tasks if task.get("id") == "recover_rejoin"), {})
    handoff = dict(recover_task.get("handoff") or {})
    return bool(
        recover_task.get("status") == "ready"
        and handoff.get("continuity") == "rejoin_path"
        and handoff.get("target_surface") == "recovery_path"
    )


def _derive_telegram_loop_ready(artifact: dict) -> bool:
    summary = dict(artifact.get("summary") or {})
    if not summary.get("guided_operator_surface_reachable", False):
        return False
    if not summary.get("provider_ready", False):
        return False
    if not summary.get("workspace_writable", False):
        return False
    return bool(
        summary.get("telegram_ingress_received", False)
        and summary.get("telegram_chat_allowed", False)
        and summary.get("telegram_request_routed", False)
        and summary.get("internal_web_query_success", False)
        and summary.get("telegram_reply_ready", False)
    )


def _telegram_live_send_env(chat_id: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in (
        "AGENTOS_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "AGENTOS_TELEGRAM_TOKEN",
        "AGENTOS_TELEGRAM_API_BASE_URL",
        "TELEGRAM_API_BASE_URL",
        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS",
        "TELEGRAM_ALLOWED_CHAT_IDS",
    ):
        value = os.environ.get(key, "").strip()
        if value:
            env[key] = value
    if not env.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS") and not env.get("TELEGRAM_ALLOWED_CHAT_IDS") and chat_id:
        env["AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id
    return env


def _telegram_token_configured(env: dict[str, str]) -> bool:
    return bool(
        env.get("AGENTOS_TELEGRAM_BOT_TOKEN")
        or env.get("TELEGRAM_BOT_TOKEN")
        or env.get("AGENTOS_TELEGRAM_TOKEN")
    )


def _redacted_guest_exec_step(proc: subprocess.CompletedProcess[str]) -> dict:
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


def _parse_json_stdout(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads((proc.stdout or "").strip())
    except Exception:
        return {}


def _derive_telegram_operator_visible(artifact: dict) -> bool:
    guided = dict((artifact.get("steps") or {}).get("guided_operator_surface") or {})
    if not guided.get("guided_operator_surface_reachable", False):
        return False
    runtime_summary = dict(guided.get("runtime_summary") or {})
    top_tasks = list(guided.get("top_tasks") or [])
    top_task_ids = {str(task.get("id", "")).strip() for task in top_tasks}
    required_task_ids = {"ask_from_telegram", "search_and_reply", "review_telegram_ingress"}
    return bool(
        runtime_summary.get("telegram_ingress_ready", False)
        and required_task_ids.issubset(top_task_ids)
    )


def _wait_guest_agent(vm_name: str, *, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    attempts = 0
    last_error = ""
    while time.time() < deadline:
        attempts += 1
        proc = _guest_pull_file(vm_name, "/etc/os-release")
        guest_agent_error = _guest_agent_error_text(proc)
        stdout = (proc.stdout or "").strip()
        if proc.returncode == 0 and not guest_agent_error and "PRETTY_NAME=" in stdout:
            ip_proc = _run(["python3", str(ROOT_DIR / "scripts" / "utm_client.py"), "--json", "ip", vm_name])
            ip_payload = json.loads(ip_proc.stdout) if ip_proc.returncode == 0 and ip_proc.stdout.strip() else {}
            return {
                "ok": True,
                "attempts": attempts,
                "ips": list(ip_payload.get("ips", []) or []),
                "reachability_mode": "file_pull",
            }
        last_error = (
            guest_agent_error
            or proc.stderr.strip()
            or proc.stdout.strip()
            or f"guest file pull probe did not return os-release (rc={proc.returncode})"
        )[-1000:]
        time.sleep(5)
    return {"ok": False, "attempts": attempts, "error": last_error}


def _serial_port_address(vm_name: str) -> str:
    proc = _run(
        [
            "osascript",
            "-e",
            f"tell {UTM_APPLESCRIPT_REF}",
            "-e",
            f'get properties of serial ports of virtual machine named "{_escape(vm_name)}"',
            "-e",
            "end tell",
        ]
    )
    if proc.returncode != 0:
        return ""
    match = re.search(r"address:([^,\n]+)", proc.stdout)
    return match.group(1).strip() if match else ""


def _serial_port_from_debug_log(vm_name: str) -> str:
    debug_log = UTM_DOCUMENTS_DIR / f"{vm_name}.utm" / "Data" / "debug.log"
    if not debug_log.is_file():
        return ""
    text = debug_log.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"char device redirected to (/dev/\S+) \(label term0\)", text)
    return matches[-1] if matches else ""


def _serial_capture(path: str, *, timeout_sec: int = 3, max_bytes: int = 32768) -> str:
    if not path:
        return ""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return ""

    chunks: list[bytes] = []
    total = 0
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline and total < max_bytes:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            try:
                data = os.read(fd, min(4096, max_bytes - total))
            except BlockingIOError:
                continue
            if not data:
                continue
            chunks.append(data)
            total += len(data)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8", "replace")[-max_bytes:]


def _serial_indicates_boot_progress(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "systemd[",
        "reloading finished",
        "reached target",
        "welcome to ubuntu",
        "cloud-init",
        "gdm",
        "agentos",
    )
    return any(marker in lowered for marker in markers)


def _serial_boot_progress_layer(text: str) -> str:
    lowered = text.lower()
    if _serial_indicates_boot_progress(text):
        return "userspace"
    if "linux version" in lowered or "kernel command line" in lowered or "booting paravirtualized kernel" in lowered:
        return "kernel"
    if "bdsdxe:" in lowered or "uefi qemu" in lowered or "boot000" in lowered:
        return "firmware"
    return "unobserved"


def _serial_acceptance_proof(text: str) -> dict:
    marker = "AGENTOS_ACCEPTANCE_PROOF_JSON="
    latest = ""
    for line in text.splitlines():
        if marker in line:
            latest = line.split(marker, 1)[1].strip()
    if not latest:
        return {}
    try:
        payload = json.loads(latest)
    except json.JSONDecodeError:
        return {}
    if payload.get("schema_version") != "agentos-serial-acceptance-proof.v1":
        return {}
    return payload


def _boot_progress_unobserved_without_excerpt(step: dict) -> bool:
    return step.get("state") == "boot_progress_unobserved" and not step.get("excerpt")


def _wait_boot_complete(serial_path: str, *, timeout_sec: int = 120, grub_enter_delay_sec: int = 5) -> dict:
    if not serial_path:
        return {
            "ok": True,
            "state": "serial_unavailable",
            "detail": "serial PTY path unavailable; proceeding to guest-agent gate",
            "grub_seen": False,
            "enter_sent": False,
            "excerpt": "",
        }

    try:
        fd = os.open(serial_path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return {
            "ok": True,
            "state": "serial_unavailable",
            "detail": f"unable to open serial PTY: {serial_path}; proceeding to guest-agent gate",
            "grub_seen": False,
            "enter_sent": False,
            "excerpt": "",
        }

    chunks: list[bytes] = []
    grub_seen = False
    enter_sent = False
    grub_seen_at = 0.0
    last_enter_sent_at = 0.0
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if ready:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    data = b""
                except OSError as exc:
                    text = b"".join(chunks).decode("utf-8", "replace")[-32768:]
                    return {
                        "ok": False,
                        "state": "serial_read_failed",
                        "detail": f"serial PTY read failed: {exc}",
                        "grub_seen": grub_seen,
                        "enter_sent": enter_sent,
                        "excerpt": text,
                    }
                if data:
                    chunks.append(data)
            text = b"".join(chunks).decode("utf-8", "replace")[-32768:]
            lowered = text.lower()
            if ("gnu grub" in lowered or "grub version" in lowered) and not grub_seen:
                grub_seen = True
                grub_seen_at = time.time()
            if _serial_indicates_boot_progress(text):
                return {
                    "ok": True,
                    "state": "boot_progress_observed",
                    "detail": "serial log reached userspace/systemd progress",
                    "progress_layer": "userspace",
                    "grub_seen": grub_seen,
                    "enter_sent": enter_sent,
                    "excerpt": text,
                }
            if not enter_sent and (
                (grub_seen and (time.time() - grub_seen_at) >= grub_enter_delay_sec)
                or (not grub_seen and not text and (deadline - time.time()) <= max(timeout_sec - grub_enter_delay_sec, 0))
            ):
                try:
                    os.write(fd, b"\r")
                    enter_sent = True
                    last_enter_sent_at = time.time()
                except OSError:
                    pass
            elif grub_seen and enter_sent and (time.time() - last_enter_sent_at) >= grub_enter_delay_sec:
                try:
                    os.write(fd, b"\r")
                    last_enter_sent_at = time.time()
                except OSError:
                    pass
        text = b"".join(chunks).decode("utf-8", "replace")[-32768:]
        if grub_seen:
            state = "grub_stuck"
            detail = "serial stayed in GRUB without userspace progress"
            ok = False
        else:
            state = "boot_progress_unobserved"
            detail = "serial did not show userspace progress before timeout; proceeding to guest-agent gate"
            ok = True
        return {
            "ok": ok,
            "state": state,
            "detail": detail,
            "progress_layer": _serial_boot_progress_layer(text),
            "grub_seen": grub_seen,
            "enter_sent": enter_sent,
            "excerpt": text,
        }
    finally:
        os.close(fd)


def _run_guest_json(vm_name: str, shell_snippet: str, *, env: dict[str, str] | None = None) -> dict:
    proc = _guest_exec(vm_name, ["/bin/sh", "-lc", shell_snippet], env=env)
    if proc.returncode != 0:
        raise AcceptanceError(proc.stderr.strip() or proc.stdout.strip() or f"guest command failed: {shell_snippet}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"guest JSON decode failed for `{shell_snippet}`: {proc.stdout[:500]}") from exc


def _run_guest_json_via_file(
    vm_name: str,
    shell_snippet: str,
    guest_output_path: str,
    *,
    env: dict[str, str] | None = None,
    timeout_sec: int = 30,
) -> dict:
    quoted_path = json.dumps(guest_output_path)
    wrapped = (
        "python3 - <<'PY'\n"
        "import os, subprocess\n"
        f"output_path = {quoted_path}\n"
        "os.makedirs(os.path.dirname(output_path), exist_ok=True)\n"
        f"command = {json.dumps(shell_snippet)}\n"
        "with open(output_path, 'w', encoding='utf-8') as handle:\n"
        "    proc = subprocess.run(['/bin/sh', '-lc', command], stdout=handle, stderr=subprocess.PIPE, text=True, check=False)\n"
        "if proc.returncode != 0:\n"
        "    raise SystemExit(proc.stderr.strip() or f'guest command failed: {command}')\n"
        "PY"
    )
    _run_guest_shell(vm_name, wrapped, env=env)
    text = _wait_for_guest_file_text(vm_name, guest_output_path, timeout_sec=timeout_sec)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"guest JSON decode failed for `{shell_snippet}` via {guest_output_path}: {text[:500]}") from exc


def _run_guest_shell(vm_name: str, shell_snippet: str, *, env: dict[str, str] | None = None) -> None:
    proc = _guest_exec(vm_name, ["/bin/sh", "-lc", shell_snippet], env=env)
    if proc.returncode != 0:
        raise AcceptanceError(proc.stderr.strip() or proc.stdout.strip() or f"guest command failed: {shell_snippet}")


def _guest_json_file_optional(vm_name: str, guest_path: str) -> dict:
    proc = _guest_cat(vm_name, guest_path)
    guest_agent_error = _guest_agent_error_text(proc)
    if guest_agent_error:
        raise AcceptanceError(f"guest agent unavailable while reading {guest_path}: {guest_agent_error}")
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def _guest_json_file_with_fallback(vm_name: str, *guest_paths: str) -> tuple[dict, str]:
    for guest_path in guest_paths:
        payload = _guest_json_file_optional(vm_name, guest_path)
        if payload:
            return payload, guest_path
    return {}, ""


def _engine_availability_guest_paths(guest_workspace: str) -> tuple[str, ...]:
    return (
        f"{guest_workspace}/artifacts/kernel-engine/latest-kernel-engine-availability.json",
        f"{DEFAULT_SEED_WORKSPACE}/artifacts/kernel-engine/latest-kernel-engine-availability.json",
    )


def _workflow_status_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/runtime-entry/latest-workflow-status.json"


def _acceptance_collector_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/acceptance-proof/latest-acceptance-proof-collector.json"


def _guest_engine_availability_status(vm_name: str, guest_workspace: str) -> tuple[dict, str]:
    output_path = f"{guest_workspace}/artifacts/kernel-engine/latest-kernel-engine-availability.json"
    payload = _run_guest_json_via_file(
        vm_name,
        (
            f"/usr/local/bin/agentos-kernelctl engine-availability "
            f"--workspace {guest_workspace} --no-bootstrap --json || true"
        ),
        output_path,
        timeout_sec=180,
    )
    return payload, output_path


def _inbox_proof_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-inbox-proof-baseline.json"


def _research_workflow_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-research-request-response-workflow.json"


def _inbox_workflow_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-inbox-triage-summary-response-workflow.json"


def _telegram_thread_status_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-telegram-thread-status.json"


def _inbox_reply_workflow_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-inbox-reply-workflow.json"


def _research_brief_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-research-brief-response.json"


def _telegram_proof_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-telegram-proof-baseline.json"


def _telegram_web_execution_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-telegram-web-execution.json"


def _telegram_reply_guest_path(guest_workspace: str) -> str:
    return f"{guest_workspace}/artifacts/capability-substrate/latest-telegram-reply-surface.json"


def _wait_for_guest_json_file_with_fallback(
    vm_name: str, *guest_paths: str, timeout_sec: int = 180, poll_interval_sec: int = 3
) -> tuple[dict, str]:
    deadline = time.time() + timeout_sec
    last_payload: dict = {}
    last_path = ""
    while time.time() < deadline:
        payload, path = _guest_json_file_with_fallback(vm_name, *guest_paths)
        if payload:
            return payload, path
        last_payload, last_path = payload, path
        time.sleep(poll_interval_sec)
    return last_payload, last_path


def _guest_runtime_entry_status(vm_name: str, guest_workspace: str) -> dict:
    workspace_literal = json.dumps(guest_workspace)
    return _run_guest_json_via_file(
        vm_name,
        (
            "python3 - <<'PY'\n"
            "import json\n"
            "import subprocess\n"
            "from pathlib import Path\n"
            f"workspace = Path({workspace_literal})\n"
            "probe = workspace / 'data' / '.agentos-write-probe'\n"
            "workspace.mkdir(parents=True, exist_ok=True)\n"
            "(workspace / 'documents').mkdir(parents=True, exist_ok=True)\n"
            "(workspace / 'artifacts').mkdir(parents=True, exist_ok=True)\n"
            "(workspace / 'data').mkdir(parents=True, exist_ok=True)\n"
            "workspace_writable = True\n"
            "write_error = ''\n"
            "try:\n"
            "    probe.write_text('ok', encoding='utf-8')\n"
            "    probe.unlink()\n"
            "except Exception as exc:\n"
            "    workspace_writable = False\n"
            "    write_error = str(exc)\n"
            "def svc(name):\n"
            "    proc = subprocess.run(['systemctl', 'show', name, '--property=ActiveState,SubState,Result,ExecMainStatus'], capture_output=True, text=True, check=False)\n"
            "    payload = {}\n"
            "    for line in proc.stdout.splitlines():\n"
            "        if '=' in line:\n"
            "            key, value = line.split('=', 1)\n"
            "            payload[key] = value\n"
            "    payload['returncode'] = proc.returncode\n"
            "    payload['stderr'] = proc.stderr.strip()\n"
            "    return payload\n"
            "print(json.dumps({\n"
            "    'runtime_entry_mode': 'tty',\n"
            "    'workspace': str(workspace),\n"
            "    'workspace_writable': workspace_writable,\n"
            "    'write_error': write_error,\n"
            "    'seed_spec_present': (workspace / 'spec.yaml').is_file(),\n"
            "    'seed_document_present': (workspace / 'documents' / 'agentos-first-run.md').is_file(),\n"
            "    'services': {\n"
            "        'agentos_ollama': svc('agentos-ollama.service'),\n"
            "        'agentos_firstrun': svc('agentos-firstrun.service'),\n"
            "    },\n"
            "}))\n"
            "PY"
        ),
        f"{guest_workspace}/artifacts/runtime-entry/latest-runtime-entry-status.json",
        timeout_sec=30,
    )


def _wait_for_runtime_entry_status(vm_name: str, guest_workspace: str, *, timeout_sec: int = 60) -> tuple[dict, str]:
    return _wait_for_guest_json_file_with_fallback(
        vm_name,
        f"{guest_workspace}/artifacts/runtime-entry/latest-runtime-entry-status.json",
        timeout_sec=timeout_sec,
        poll_interval_sec=3,
    )


def _guest_file_text(vm_name: str, guest_path: str) -> str:
    proc = _guest_cat(vm_name, guest_path)
    guest_agent_error = _guest_agent_error_text(proc)
    if proc.returncode != 0 or guest_agent_error:
        detail = guest_agent_error or proc.stderr.strip() or proc.stdout.strip()
        if guest_agent_error:
            raise AcceptanceError(f"guest agent unavailable while reading {guest_path}: {detail}")
        raise AcceptanceError(proc.stderr.strip() or proc.stdout.strip() or f"unable to read guest file: {guest_path}")
    return proc.stdout


def _wait_for_guest_file_text(vm_name: str, guest_path: str, *, timeout_sec: int = 120, poll_interval_sec: int = 3) -> str:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        proc = _guest_cat(vm_name, guest_path)
        guest_agent_error = _guest_agent_error_text(proc)
        if guest_agent_error:
            last_error = guest_agent_error
            time.sleep(poll_interval_sec)
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
        last_error = proc.stderr.strip() or proc.stdout.strip() or f"unable to read guest file: {guest_path}"
        time.sleep(poll_interval_sec)
    raise AcceptanceError(last_error or f"timed out waiting for guest file: {guest_path}")


def _wait_for_guest_json_artifact(
    vm_name: str,
    guest_path: str,
    *,
    timeout_sec: int = 180,
    poll_interval_sec: int = 3,
) -> dict:
    text = _wait_for_guest_file_text(
        vm_name,
        guest_path,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"guest JSON decode failed for artifact {guest_path}: {text[:500]}") from exc


def _cleanup_stale_acceptance_vms(current_vm_name: str) -> list[dict]:
    cleaned: list[dict] = []
    for name in _list_vm_names():
        if name == current_vm_name:
            continue
        if not name.startswith("AgentOS Acceptance "):
            continue
        try:
            cleaned.append(force_delete_vm(name, if_exists=True))
        except Exception as exc:
            cleaned.append({"vm_name": name, "deleted": False, "error": str(exc)})
    return cleaned


def _classify_takeover_state(bootstrap_status: dict, welcome_status: dict) -> tuple[str, str] | None:
    if not bootstrap_status:
        return ("live_session_takeover_failure", "live bootstrap did not record a takeover status")
    if bootstrap_status.get("state") in {"welcome_launch_failed", "live_session_takeover_failure"}:
        return (
            "live_session_takeover_failure",
            str(bootstrap_status.get("detail", "live bootstrap reported a takeover failure")),
        )
    if not welcome_status:
        return ("live_session_takeover_failure", "welcome shell did not record a runtime status")
    return None


def _resolve_uefi_boot(*, base_image_type: str, override: str) -> bool:
    if override == "on":
        return True
    if override == "off":
        return False
    return base_image_type == "headless-live-server-iso"


def _apply_serial_acceptance_proof(artifact: dict, proof: dict) -> None:
    artifact["steps"]["serial_acceptance_proof"] = proof
    artifact["summary"]["guest_reachable"] = bool(proof.get("guest_reachable", False))
    artifact["summary"]["workspace_writable"] = bool(proof.get("workspace_writable", False))
    artifact["summary"]["guided_operator_surface_reachable"] = bool(
        proof.get("guided_operator_surface_reachable", False)
    )
    artifact["summary"]["workflow_status_ready"] = bool(proof.get("workflow_status_ready", False))
    artifact["summary"]["operator_next_action_visible"] = bool(proof.get("operator_next_action_visible", False))
    artifact["summary"]["provider_ready"] = bool(proof.get("provider_ready", False))
    artifact["summary"]["first_prompt_success"] = bool(proof.get("first_prompt_success", False))
    artifact["summary"]["managed_reentry_ready"] = bool(proof.get("managed_reentry_ready", False))
    artifact["summary"]["usable_runtime_entry"] = bool(proof.get("usable_runtime_entry", False))
    artifact["summary"]["top_task_success"] = bool(proof.get("top_task_success", False))
    artifact["summary"]["first_run_summary_ready"] = bool(proof.get("first_run_summary_ready", False))
    artifact["summary"]["telegram_ingress_received"] = bool(proof.get("telegram_ingress_received", False))
    artifact["summary"]["telegram_chat_allowed"] = bool(proof.get("telegram_chat_allowed", False))
    artifact["summary"]["telegram_request_routed"] = bool(proof.get("telegram_request_routed", False))
    artifact["summary"]["internal_web_query_success"] = bool(proof.get("internal_web_query_success", False))
    artifact["summary"]["telegram_reply_ready"] = bool(proof.get("telegram_reply_ready", False))
    artifact["summary"]["telegram_reply_sent"] = bool(proof.get("telegram_reply_sent", False))
    artifact["summary"]["telegram_loop_ready"] = bool(proof.get("telegram_loop_ready", False))
    artifact["summary"]["browser_escalation_used"] = bool(proof.get("browser_escalation_used", False))
    artifact["summary"]["research_workflow_ready"] = bool(proof.get("research_workflow_ready", False))
    artifact["summary"]["inbox_workflow_ready"] = bool(proof.get("inbox_workflow_ready", False))
    artifact["summary"]["telegram_thread_continuity_ready"] = bool(
        proof.get("telegram_thread_continuity_ready", False)
    )
    artifact["summary"]["inbox_reply_workflow_ready"] = bool(proof.get("inbox_reply_workflow_ready", False))
    artifact["summary"]["research_brief_ready"] = bool(proof.get("research_brief_ready", False))
    artifact["summary"]["brief_artifact_exported"] = bool(proof.get("brief_artifact_exported", False))
    artifact["summary"]["runtime_entry_mode"] = str(proof.get("runtime_entry_mode") or "tty")
    artifact["summary"]["pass"] = bool(proof.get("pass", False))
    artifact["summary"]["failure_class"] = "" if artifact["summary"]["pass"] else "serial_acceptance_proof_failure"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repo-free AgentOS acceptance on a disposable UTM VM")
    parser.add_argument("--release-metadata", default="")
    parser.add_argument("--iso-path", default="")
    parser.add_argument("--vm-name", default="")
    parser.add_argument("--guest-workspace", default=DEFAULT_GUEST_WORKSPACE)
    parser.add_argument("--document-path", default=DEFAULT_DOCUMENT_PATH)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--telegram-message-text", default="search agentos roadmap")
    parser.add_argument("--telegram-chat-id", default="1001")
    parser.add_argument("--telegram-request-id", default="telegram-request-acceptance")
    parser.add_argument("--telegram-message-id", default="telegram-message-acceptance")
    parser.add_argument(
        "--telegram-live-send",
        action="store_true",
        help="Require a real Telegram sendMessage call using runtime-provided Telegram env secrets.",
    )
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument(
        "--boot-complete-timeout-sec",
        type=int,
        default=180,
        help="How long to watch serial output for userspace/AgentOS progress before the guest-agent gate.",
    )
    parser.add_argument("--guest-agent-timeout-sec", type=int, default=420)
    parser.add_argument("--memory-mib", type=int, default=8192)
    parser.add_argument("--cpu-cores", type=int, default=4)
    parser.add_argument("--disk-size-mib", type=int, default=32768)
    parser.add_argument(
        "--uefi-boot",
        choices=("auto", "on", "off"),
        default="auto",
        help="VM firmware mode. auto uses UEFI for headless live-server proof ISOs and BIOS otherwise.",
    )
    parser.add_argument("--keep-vm", action="store_true")
    parser.add_argument("--keep-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    release_metadata_path = Path(args.release_metadata).resolve() if args.release_metadata else _latest_release_metadata()
    release = _load_release_identity(release_metadata_path)
    iso_path = Path(args.iso_path).resolve() if args.iso_path else Path(str(release.get("output_path", ""))).resolve()
    if not iso_path.is_file():
        raise SystemExit(f"ISO not found: {iso_path}")

    version = str(release.get("agentos_version", "")).strip() or iso_path.stem.replace("agentos-", "")
    vm_name = args.vm_name or default_vm_name(version)
    host_arch = _host_arch()
    guest_arch = _guest_arch_from_iso(iso_path, release)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "vm": {},
        "iso": {
            "version": version,
            "path": str(iso_path),
            "release_metadata_path": str(release_metadata_path),
            "boot_target_activated": bool(release.get("boot_target_activated", False)),
            "manifest_boot_target_activated": bool(release.get("manifest_boot_target_activated", False)),
            "base_image_type": str(release.get("manifest_base_image_type") or release.get("base_image_type") or ""),
            "guest_arch": guest_arch,
        },
        "host": {
            "arch": host_arch,
            "guest_arch": guest_arch,
            "emulation_required": _emulation_required(host_arch, guest_arch),
        },
        "summary": {
            "backend_used": "utm_applescript_plus_utmctl",
            "gui_required": False,
            "gui_path_role": "fallback_debug_only",
            "guest_reachable": False,
            "guided_operator_surface_reachable": False,
            "workflow_status_ready": False,
            "operator_next_action_visible": False,
            "recovery_affordance_visible": False,
            "recovery_degraded_acceptance_ready": False,
            "workspace_writable": False,
            "provider_ready": False,
            "first_prompt_success": False,
            "managed_reentry_ready": False,
            "usable_runtime_entry": False,
            "top_task_success": False,
            "first_run_summary_ready": False,
            "telegram_ingress_received": False,
            "telegram_chat_allowed": False,
            "telegram_request_routed": False,
            "internal_web_query_success": False,
            "telegram_reply_ready": False,
            "telegram_reply_sent": False,
            "telegram_live_send_requested": bool(args.telegram_live_send),
            "telegram_send_attempted": False,
            "telegram_token_configured": _telegram_token_configured(_telegram_live_send_env(args.telegram_chat_id)),
            "telegram_polling_attempted": False,
            "telegram_live_update_received": False,
            "telegram_live_message_routed": False,
            "telegram_live_search_success": False,
            "telegram_update_offset_persisted": False,
            "telegram_loop_ready": False,
            "browser_escalation_used": False,
            "telegram_operator_visible": False,
            "research_workflow_ready": False,
            "inbox_workflow_ready": False,
            "telegram_thread_continuity_ready": False,
            "inbox_reply_workflow_ready": False,
            "research_brief_ready": False,
            "brief_artifact_exported": False,
            "runtime_entry_mode": "tty",
            "pass": False,
            "failure_class": "",
        },
        "steps": {
            "cleanup_stale_vms": [],
            "create_vm": {},
            "boot_vm": {},
            "guest_agent": {},
            "runtime_entry": {},
            "guided_operator_surface": {},
            "workflow_status": {},
            "engine_availability": {},
            "document_access": {},
            "web_access": {},
            "inbox_proof": {},
            "telegram_proof": {},
            "telegram_web_execution": {},
            "telegram_reply": {},
            "telegram_live_send": {},
            "telegram_live_loop": {},
            "research_workflow": {},
            "inbox_workflow": {},
            "telegram_thread_status": {},
            "inbox_reply_workflow": {},
            "research_brief": {},
            "serial_acceptance_proof": {},
            "first_run_summary": {},
            "vm_e2e_proof": {},
            "boot_restart": {},
        },
        "artifacts": {
            "handoff_env_text": "",
            "live_bootstrap_status": {},
            "welcome_status": {},
            "serial_port_address": "",
            "serial_capture_excerpt": "",
        },
    }

    if args.dry_run:
        planned_uefi_boot = _resolve_uefi_boot(
            base_image_type=artifact["iso"]["base_image_type"],
            override=args.uefi_boot,
        )
        artifact["vm"] = {
            "vm_name": vm_name,
            "memory_mib": args.memory_mib,
            "cpu_cores": args.cpu_cores,
            "disk_size_mib": args.disk_size_mib,
            "guest_workspace": args.guest_workspace,
            "uefi_boot": planned_uefi_boot,
        }
        artifact["planned_commands"] = [
            f"create disposable VM {vm_name}",
            f"boot ISO {iso_path}",
            "wait for guest agent readiness",
            "wait for guest acceptance proof collector artifacts",
            f"/usr/local/bin/agentos-kernelctl document-access --workspace {args.guest_workspace} --path {args.document_path} --json",
            f"/usr/local/bin/agentos-kernelctl web-access --workspace {args.guest_workspace} --url {args.web_url} --json",
            f"/usr/local/bin/agentos-kernelctl guided-operator --workspace {args.guest_workspace} --json",
            f"/usr/local/bin/agentos-kernelctl workflow-status --workspace {args.guest_workspace} --json",
            f"/usr/local/bin/agentos-kernelctl engine-availability --workspace {args.guest_workspace} --no-bootstrap --json",
            f"/usr/local/bin/agentos-kernelctl inbox-proof --workspace {args.guest_workspace} --json",
            f"/usr/local/bin/agentos-kernelctl telegram-proof --workspace {args.guest_workspace} --message-text {args.telegram_message_text} --chat-id {args.telegram_chat_id} --request-id {args.telegram_request_id} --message-id {args.telegram_message_id} --json",
            f"/usr/local/bin/agentos-kernelctl telegram-web-execution --workspace {args.guest_workspace} --message-text {args.telegram_message_text} --chat-id {args.telegram_chat_id} --request-id {args.telegram_request_id} --message-id {args.telegram_message_id} --json",
            f"/usr/local/bin/agentos-kernelctl telegram-reply --workspace {args.guest_workspace} --message-text {args.telegram_message_text} --chat-id {args.telegram_chat_id} --request-id {args.telegram_request_id} --message-id {args.telegram_message_id}{' --send' if args.telegram_live_send else ''} --json",
            f"/usr/local/bin/agentos-kernelctl telegram-live-loop --workspace {args.guest_workspace} --once{' --send' if args.telegram_live_send else ''} --json",
            f"/usr/local/bin/agentos-kernelctl research-workflow --workspace {args.guest_workspace} --message-text {args.telegram_message_text} --chat-id {args.telegram_chat_id} --request-id {args.telegram_request_id} --message-id {args.telegram_message_id} --json",
            f"/usr/local/bin/agentos-kernelctl inbox-workflow --workspace {args.guest_workspace} --json",
            f"/usr/local/bin/agentos-kernelctl first-run-summary --workspace {args.guest_workspace} --json",
            f"/usr/local/bin/agentos-kernelctl vm-e2e-proof --workspace {args.guest_workspace} --json",
        ]
        print(json.dumps(artifact, ensure_ascii=True) if args.json else json.dumps(artifact, indent=2, ensure_ascii=False))
        return 0

    keep_vm = args.keep_vm
    try:
        if args.telegram_live_send and not _telegram_token_configured(_telegram_live_send_env(args.telegram_chat_id)):
            artifact["summary"]["failure_class"] = "telegram_token_missing"
            raise AcceptanceError("telegram live send requested but no runtime Telegram bot token is configured")

        artifact["steps"]["cleanup_stale_vms"] = _cleanup_stale_acceptance_vms(vm_name)
        uefi_boot = _resolve_uefi_boot(
            base_image_type=artifact["iso"]["base_image_type"],
            override=args.uefi_boot,
        )
        artifact["steps"]["create_vm"] = create_vm(
            vm_name=vm_name,
            iso_path=str(iso_path),
            disk_size_mib=args.disk_size_mib,
            memory_mib=args.memory_mib,
            cpu_cores=args.cpu_cores,
            uefi_boot=uefi_boot,
            arch=guest_arch,
        )
        artifact["vm"] = artifact["steps"]["create_vm"]

        try:
            start_disposable(vm_name)
        except Exception as exc:
            artifact["summary"]["failure_class"] = "vm_boot_failure"
            raise AcceptanceError(str(exc)) from exc
        artifact["steps"]["boot_vm"] = _wait_running(vm_name, timeout_sec=args.timeout_sec)
        if not artifact["steps"]["boot_vm"]["ok"]:
            artifact["summary"]["failure_class"] = "vm_boot_failure"
            raise AcceptanceError("VM did not reach a running state in time")
        artifact["artifacts"]["serial_port_address"] = _serial_port_address(vm_name) or _serial_port_from_debug_log(vm_name)
        artifact["steps"]["boot_complete"] = _wait_boot_complete(
            artifact["artifacts"]["serial_port_address"],
            timeout_sec=args.boot_complete_timeout_sec,
        )
        artifact["artifacts"]["serial_capture_excerpt"] = artifact["steps"]["boot_complete"].get("excerpt", "")
        if _boot_progress_unobserved_without_excerpt(artifact["steps"]["boot_complete"]):
            restart_disposable(vm_name)
            artifact["steps"]["boot_restart"] = {"attempted": True, "reason": "serial_progress_unobserved"}
            artifact["steps"]["boot_vm_after_restart"] = _wait_running(vm_name, timeout_sec=args.timeout_sec)
            artifact["artifacts"]["serial_port_address"] = _serial_port_address(vm_name) or _serial_port_from_debug_log(vm_name)
            artifact["steps"]["boot_complete"] = _wait_boot_complete(
                artifact["artifacts"]["serial_port_address"],
                timeout_sec=args.boot_complete_timeout_sec,
            )
            artifact["artifacts"]["serial_capture_excerpt"] = artifact["steps"]["boot_complete"].get("excerpt", "")
        if _boot_progress_unobserved_without_excerpt(artifact["steps"]["boot_complete"]):
            artifact["summary"]["failure_class"] = "vm_boot_failure"
            raise AcceptanceError("serial boot progress was not observed after restart")
        if not artifact["steps"]["boot_complete"]["ok"]:
            artifact["summary"]["failure_class"] = "vm_boot_failure"
            raise AcceptanceError(artifact["steps"]["boot_complete"].get("detail", "serial boot progress was not observed"))

        if not release.get("manifest_boot_target_activated", False):
            artifact["summary"]["failure_class"] = "welcome_setup_handoff_failure"
            raise AcceptanceError("boot target activation is false; fresh-ISO gate remains blocked")

        artifact["steps"]["guest_agent"] = _wait_guest_agent(vm_name, timeout_sec=args.guest_agent_timeout_sec)
        if not artifact["steps"]["guest_agent"]["ok"]:
            latest_serial_excerpt = _serial_capture(
                artifact["artifacts"]["serial_port_address"],
                timeout_sec=10,
                max_bytes=65536,
            )
            if latest_serial_excerpt:
                artifact["artifacts"]["serial_capture_excerpt"] = latest_serial_excerpt
            serial_proof = _serial_acceptance_proof(artifact["artifacts"]["serial_capture_excerpt"])
            if serial_proof:
                _apply_serial_acceptance_proof(artifact, serial_proof)
                if artifact["summary"]["pass"]:
                    raise AcceptanceComplete()
                raise AcceptanceError("serial acceptance proof was present but did not pass")
            progress_layer = str(artifact["steps"].get("boot_complete", {}).get("progress_layer", "")).strip()
            if progress_layer in {"firmware", "kernel"}:
                artifact["summary"]["failure_class"] = "vm_boot_failure"
                raise AcceptanceError(
                    f"serial reached {progress_layer} but userspace/AgentOS proof was not observed before guest-agent gate"
                )
            artifact["summary"]["failure_class"] = "guest_agent_unavailable"
            raise AcceptanceError(artifact["steps"]["guest_agent"].get("error", "guest agent unavailable"))
        artifact["summary"]["guest_reachable"] = True
        runtime_entry, runtime_entry_path = _wait_for_runtime_entry_status(
            vm_name,
            args.guest_workspace,
            timeout_sec=240,
        )
        if not runtime_entry:
            artifact["artifacts"]["acceptance_collector_status"] = _guest_json_file_optional(
                vm_name,
                _acceptance_collector_guest_path(args.guest_workspace),
            )
            artifact["summary"]["failure_class"] = "runtime_workspace_unwritable"
            raise AcceptanceError("guest runtime entry artifact was not produced by the acceptance proof collector")
        artifact["steps"]["runtime_entry"] = runtime_entry
        artifact["artifacts"]["runtime_entry_status_path"] = runtime_entry_path
        artifact["summary"]["runtime_entry_mode"] = str(artifact["steps"]["runtime_entry"].get("runtime_entry_mode", "tty"))
        artifact["summary"]["workspace_writable"] = bool(artifact["steps"]["runtime_entry"].get("workspace_writable", False))
        if not artifact["summary"]["workspace_writable"]:
            artifact["summary"]["failure_class"] = "runtime_workspace_unwritable"
            raise AcceptanceError(artifact["steps"]["runtime_entry"].get("write_error", "guest runtime workspace is not writable"))
        artifact["artifacts"]["serial_capture_excerpt"] = _serial_capture(
            artifact["artifacts"]["serial_port_address"],
            timeout_sec=2,
        )

        artifact["steps"]["guided_operator_surface"] = _wait_for_guest_json_artifact(
            vm_name,
            f"{args.guest_workspace}/artifacts/runtime-entry/latest-guided-operator-surface.json",
            timeout_sec=240,
            poll_interval_sec=5,
        )
        artifact["summary"]["guided_operator_surface_reachable"] = bool(
            artifact["steps"]["guided_operator_surface"].get("guided_operator_surface_reachable", False)
        )
        artifact["summary"]["recovery_affordance_visible"] = bool(
            artifact["steps"]["guided_operator_surface"].get("recovery_affordance_visible", False)
        )
        artifact["summary"]["telegram_operator_visible"] = _derive_telegram_operator_visible(artifact)
        artifact["summary"]["recovery_degraded_acceptance_ready"] = _derive_recovery_degraded_acceptance(artifact)

        artifact["steps"]["workflow_status"] = _wait_for_guest_json_artifact(
            vm_name,
            _workflow_status_guest_path(args.guest_workspace),
            timeout_sec=240,
            poll_interval_sec=5,
        )
        workflow_summary = dict(artifact["steps"]["workflow_status"].get("summary") or {})
        artifact["summary"]["workflow_status_ready"] = bool(workflow_summary.get("workflow_status_ready", False))
        artifact["summary"]["operator_next_action_visible"] = bool(
            artifact["steps"]["workflow_status"].get("next_actions")
        )
        if not artifact["summary"]["workflow_status_ready"]:
            artifact["summary"]["failure_class"] = "welcome_setup_handoff_failure"
            raise AcceptanceError("workflow status surface did not become ready")

        engine_availability, engine_availability_path = _wait_for_guest_json_file_with_fallback(
            vm_name,
            *_engine_availability_guest_paths(args.guest_workspace),
            timeout_sec=240,
            poll_interval_sec=5,
        )
        artifact["steps"]["engine_availability"] = engine_availability
        artifact["artifacts"]["engine_availability_path"] = engine_availability_path
        engine_summary = dict(artifact["steps"]["engine_availability"].get("summary") or {})
        if not engine_summary.get("usable_runtime_entry", False):
            artifact["artifacts"]["acceptance_collector_status"] = _guest_json_file_optional(
                vm_name,
                _acceptance_collector_guest_path(args.guest_workspace),
            )
        artifact["summary"]["provider_ready"] = bool(engine_summary.get("provider_ready", False))
        artifact["summary"]["first_prompt_success"] = bool(engine_summary.get("first_prompt_success", False))
        artifact["summary"]["managed_reentry_ready"] = bool(engine_summary.get("managed_reentry_ready", False))
        artifact["summary"]["usable_runtime_entry"] = bool(engine_summary.get("usable_runtime_entry", False))
        if not artifact["summary"]["usable_runtime_entry"]:
            artifact["summary"]["failure_class"] = "engine_unavailable"
            raise AcceptanceError("kernel engine availability did not reach usable_runtime_entry")

        live_bootstrap_status, live_bootstrap_status_path = _wait_for_guest_json_file_with_fallback(
            vm_name,
            "/var/lib/agentos/live-bootstrap/live-session-status.json",
            "/tmp/agentos-live-bootstrap/live-session-status.json",
        )
        welcome_status, welcome_status_path = _wait_for_guest_json_file_with_fallback(
            vm_name,
            "/var/lib/agentos/live-bootstrap/welcome-status.json",
            "/tmp/agentos-live-bootstrap/welcome-status.json",
            timeout_sec=180,
        )
        artifact["artifacts"]["live_bootstrap_status"] = live_bootstrap_status
        artifact["artifacts"]["welcome_status"] = welcome_status
        artifact["artifacts"]["live_bootstrap_status_path"] = live_bootstrap_status_path
        artifact["artifacts"]["welcome_status_path"] = welcome_status_path

        try:
            handoff_text = _wait_for_guest_file_text(
                vm_name,
                "/tmp/agentos-handoff.env",
                timeout_sec=15,
            )
        except AcceptanceError:
            handoff_text = ""
        artifact["artifacts"]["handoff_env_text"] = handoff_text

        first_run_summary_path = f"{args.guest_workspace}/artifacts/repo-free-first-run/latest-first-run-summary.json"
        artifact["steps"]["first_run_summary"] = _wait_for_guest_json_artifact(
            vm_name,
            first_run_summary_path,
            timeout_sec=180,
            poll_interval_sec=5,
        )
        artifact["steps"]["document_access"] = dict(artifact["steps"]["first_run_summary"].get("document_access") or {})
        artifact["steps"]["web_access"] = dict(artifact["steps"]["first_run_summary"].get("web_access") or {})
        if not artifact["steps"]["document_access"].get("native_handled", False):
            artifact["summary"]["failure_class"] = "document_path_failure"
            raise AcceptanceError("document access was not handled natively")
        web_ok = bool(
            artifact["steps"]["web_access"].get("native_handled", False)
            or artifact["steps"]["web_access"].get("escalated_handled", False)
        )
        if not web_ok:
            artifact["summary"]["failure_class"] = "web_path_failure"
            raise AcceptanceError("web access did not produce a native or escalated result")
        if not artifact["steps"]["first_run_summary"].get("summary", {}).get("capability_proof_ready", False):
            artifact["summary"]["failure_class"] = "summary_or_proof_export_failure"
            raise AcceptanceError("first-run summary did not reach capability_proof_ready")
        artifact["summary"]["first_run_summary_ready"] = True

        artifact["steps"]["inbox_proof"] = _wait_for_guest_json_artifact(
            vm_name,
            _inbox_proof_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )
        if not artifact["steps"]["inbox_proof"].get("summary", {}).get("inbox_execution_ready", False):
            artifact["summary"]["failure_class"] = "inbox_proof_failure"
            raise AcceptanceError("inbox proof did not reach inbox_execution_ready")
        artifact["summary"]["top_task_success"] = _derive_top_task_success(artifact)
        if not artifact["summary"]["top_task_success"]:
            artifact["summary"]["failure_class"] = "summary_or_proof_export_failure"
            raise AcceptanceError("guided operator top task success was not observed")

        artifact["steps"]["telegram_proof"] = _wait_for_guest_json_artifact(
            vm_name,
            _telegram_proof_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        telegram_summary = dict(artifact["steps"]["telegram_proof"].get("summary") or {})
        artifact["summary"]["telegram_ingress_received"] = bool(telegram_summary.get("telegram_ingress_received", False))
        artifact["summary"]["telegram_chat_allowed"] = bool(telegram_summary.get("telegram_chat_allowed", False))
        artifact["summary"]["telegram_request_routed"] = bool(telegram_summary.get("telegram_request_routed", False))
        if not (
            artifact["summary"]["telegram_ingress_received"]
            and artifact["summary"]["telegram_chat_allowed"]
            and artifact["summary"]["telegram_request_routed"]
        ):
            artifact["summary"]["failure_class"] = "telegram_ingress_failure"
            raise AcceptanceError("telegram ingress proof did not reach routed request state")

        artifact["steps"]["telegram_web_execution"] = _wait_for_guest_json_artifact(
            vm_name,
            _telegram_web_execution_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        execution_report = dict(artifact["steps"]["telegram_web_execution"] or {})
        execution_proof = dict(execution_report.get("proof") or {})
        artifact["summary"]["internal_web_query_success"] = bool(
            execution_report.get("native_handled", False) and execution_proof.get("ok", False)
        )
        artifact["summary"]["browser_escalation_used"] = bool(execution_report.get("browser_escalation_used", False))
        if not artifact["summary"]["internal_web_query_success"]:
            artifact["summary"]["failure_class"] = "telegram_web_execution_failure"
            raise AcceptanceError("telegram internal web execution did not succeed")
        if artifact["summary"]["browser_escalation_used"]:
            artifact["summary"]["failure_class"] = "telegram_web_execution_failure"
            raise AcceptanceError("telegram happy-path acceptance unexpectedly required browser escalation")

        artifact["steps"]["telegram_reply"] = _wait_for_guest_json_artifact(
            vm_name,
            _telegram_reply_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        reply_report = dict(artifact["steps"]["telegram_reply"] or {})
        artifact["summary"]["telegram_reply_ready"] = bool(reply_report.get("reply_ready", False))
        artifact["summary"]["telegram_reply_sent"] = bool(reply_report.get("reply_sent", False))
        artifact["summary"]["telegram_loop_ready"] = _derive_telegram_loop_ready(artifact)
        if not artifact["summary"]["telegram_reply_ready"]:
            artifact["summary"]["failure_class"] = "telegram_reply_failure"
            raise AcceptanceError("telegram reply surface did not reach reply_ready")
        if not artifact["summary"]["telegram_loop_ready"]:
            artifact["summary"]["failure_class"] = "telegram_reply_failure"
            raise AcceptanceError("telegram acceptance loop did not reach ready state")

        if args.telegram_live_send:
            live_send_env = _telegram_live_send_env(args.telegram_chat_id)
            live_send_cmd = [
                "/usr/local/bin/agentos-kernelctl",
                "telegram-live-loop",
                "--workspace",
                args.guest_workspace,
                "--once",
                "--send",
                "--json",
            ]
            live_send_proc = _guest_exec(vm_name, live_send_cmd, env=live_send_env)
            artifact["steps"]["telegram_live_send"] = _redacted_guest_exec_step(live_send_proc)
            artifact["steps"]["telegram_live_loop"] = artifact["steps"]["telegram_live_send"]
            live_send_report = _parse_json_stdout(live_send_proc)
            if live_send_report:
                artifact["steps"]["telegram_live_loop"] = live_send_report
            live_summary = live_send_report.get("summary", {}) if isinstance(live_send_report.get("summary"), dict) else live_send_report
            artifact["summary"]["telegram_polling_attempted"] = bool(live_summary.get("telegram_polling_attempted", False))
            artifact["summary"]["telegram_live_update_received"] = bool(live_summary.get("telegram_live_update_received", False))
            artifact["summary"]["telegram_live_message_routed"] = bool(live_summary.get("telegram_live_message_routed", False))
            artifact["summary"]["telegram_live_search_success"] = bool(live_summary.get("telegram_live_search_success", False))
            artifact["summary"]["telegram_update_offset_persisted"] = bool(live_summary.get("telegram_update_offset_persisted", False))
            artifact["summary"]["telegram_send_attempted"] = bool(
                live_send_report.get("reply", {}).get("send_attempted", False)
                if isinstance(live_send_report.get("reply"), dict)
                else False
            )
            artifact["summary"]["telegram_reply_sent"] = bool(live_summary.get("telegram_reply_sent", False))
            artifact["summary"]["telegram_token_configured"] = bool(
                live_send_report.get("transport", {}).get("bot_token_configured", False)
            )
            if not artifact["summary"]["telegram_token_configured"]:
                artifact["summary"]["failure_class"] = "telegram_token_missing"
                raise AcceptanceError("telegram live send requested but no bot token was configured")
            if not artifact["summary"]["telegram_polling_attempted"]:
                artifact["summary"]["failure_class"] = "telegram_polling_unavailable"
                raise AcceptanceError("telegram live polling was not attempted")
            if not artifact["summary"]["telegram_live_update_received"]:
                artifact["summary"]["failure_class"] = "telegram_live_update_timeout"
                raise AcceptanceError("telegram live polling did not receive an update")
            if live_summary.get("telegram_chat_rejected", False):
                artifact["summary"]["failure_class"] = "telegram_chat_rejected"
                raise AcceptanceError("telegram live update came from a rejected chat")
            if not artifact["summary"]["telegram_live_message_routed"]:
                artifact["summary"]["failure_class"] = "telegram_live_update_timeout"
                raise AcceptanceError("telegram live update was not routed")
            if not artifact["summary"]["telegram_live_search_success"]:
                artifact["summary"]["failure_class"] = "internal_web_query_failure"
                raise AcceptanceError("telegram live update did not complete internal web search")
            if not artifact["summary"]["telegram_send_attempted"]:
                artifact["summary"]["failure_class"] = "telegram_send_failure"
                raise AcceptanceError("telegram live send was not attempted")
            if not artifact["summary"]["telegram_reply_sent"]:
                artifact["summary"]["failure_class"] = "telegram_send_failure"
                raise AcceptanceError("telegram live send did not report reply_sent=true")

        artifact["steps"]["research_workflow"] = _wait_for_guest_json_artifact(
            vm_name,
            _research_workflow_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        research_workflow = dict(artifact["steps"]["research_workflow"] or {})
        artifact["summary"]["research_workflow_ready"] = bool(research_workflow.get("workflow_ready", False))
        if not artifact["summary"]["research_workflow_ready"]:
            artifact["summary"]["failure_class"] = "telegram_reply_failure"
            raise AcceptanceError("research workflow surface did not reach workflow_ready")

        artifact["steps"]["inbox_workflow"] = _wait_for_guest_json_artifact(
            vm_name,
            _inbox_workflow_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        inbox_workflow = dict(artifact["steps"]["inbox_workflow"] or {})
        artifact["summary"]["inbox_workflow_ready"] = bool(inbox_workflow.get("workflow_ready", False))
        if not artifact["summary"]["inbox_workflow_ready"]:
            artifact["summary"]["failure_class"] = "inbox_proof_failure"
            raise AcceptanceError("inbox workflow surface did not reach workflow_ready")

        artifact["steps"]["telegram_thread_status"] = _wait_for_guest_json_artifact(
            vm_name,
            _telegram_thread_status_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        telegram_thread = dict(artifact["steps"]["telegram_thread_status"] or {})
        artifact["summary"]["telegram_thread_continuity_ready"] = bool(
            telegram_thread.get("telegram_thread_continuity_ready", False)
        )
        if not artifact["summary"]["telegram_thread_continuity_ready"]:
            artifact["summary"]["failure_class"] = "telegram_thread_continuity_failure"
            raise AcceptanceError("telegram thread continuity surface did not reach ready state")

        artifact["steps"]["inbox_reply_workflow"] = _wait_for_guest_json_artifact(
            vm_name,
            _inbox_reply_workflow_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        inbox_reply = dict(artifact["steps"]["inbox_reply_workflow"] or {})
        artifact["summary"]["inbox_reply_workflow_ready"] = bool(
            inbox_reply.get("inbox_reply_workflow_ready", False)
        )
        if not artifact["summary"]["inbox_reply_workflow_ready"]:
            artifact["summary"]["failure_class"] = "inbox_reply_workflow_failure"
            raise AcceptanceError("inbox reply workflow surface did not reach ready state")

        artifact["steps"]["research_brief"] = _wait_for_guest_json_artifact(
            vm_name,
            _research_brief_guest_path(args.guest_workspace),
            timeout_sec=180,
            poll_interval_sec=5,
        )

        research_brief = dict(artifact["steps"]["research_brief"] or {})
        artifact["summary"]["research_brief_ready"] = bool(research_brief.get("research_brief_ready", False))
        artifact["summary"]["brief_artifact_exported"] = bool(research_brief.get("brief_artifact_exported", False))
        if not artifact["summary"]["research_brief_ready"]:
            artifact["summary"]["failure_class"] = "research_brief_failure"
            raise AcceptanceError("research brief workflow surface did not reach ready state")
        if not artifact["summary"]["brief_artifact_exported"]:
            artifact["summary"]["failure_class"] = "research_brief_failure"
            raise AcceptanceError("research brief workflow did not export a dedicated brief artifact")

        vm_e2e_proof_path = f"{args.guest_workspace}/artifacts/control-plane-capabilities/latest-vm-e2e-proof.json"
        artifact["steps"]["vm_e2e_proof"] = _wait_for_guest_json_artifact(
            vm_name,
            vm_e2e_proof_path,
            timeout_sec=180,
            poll_interval_sec=5,
        )
        vm_summary = dict(artifact["steps"]["vm_e2e_proof"].get("summary") or {})
        if not all(
            vm_summary.get(key, False)
            for key in (
                "vm_e2e_runtime_ok",
                "vm_e2e_capability_ok",
                "vm_e2e_intake_ok",
                "vm_e2e_service_permission_ok",
                "vm_e2e_escalation_integrity_ok",
            )
        ):
            artifact["summary"]["failure_class"] = "summary_or_proof_export_failure"
            raise AcceptanceError("vm-e2e-proof summary booleans are not all true")

        artifact["summary"]["pass"] = True
        artifact["summary"]["failure_class"] = ""

    except AcceptanceComplete:
        pass
    except AcceptanceError as exc:
        if not artifact["summary"]["failure_class"]:
            artifact["summary"]["failure_class"] = "summary_or_proof_export_failure"
        artifact["summary"]["error"] = str(exc)
        keep_vm = keep_vm or args.keep_on_failure
    except Exception as exc:
        if not artifact["summary"]["failure_class"]:
            artifact["summary"]["failure_class"] = "vm_boot_failure"
        artifact["summary"]["error"] = f"acceptance runner error: {exc}"
        keep_vm = keep_vm or args.keep_on_failure
    finally:
        artifact_path = _artifact_path("latest-repo-free-utm-acceptance.json")
        artifact["artifacts"]["acceptance_artifact_json"] = str(artifact_path)
        if not keep_vm and artifact.get("vm", {}).get("vm_name"):
            try:
                artifact["cleanup"] = force_delete_vm(artifact["vm"]["vm_name"], if_exists=True)
            except Exception as exc:
                artifact["cleanup"] = {"ok": False, "error": str(exc)}
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=True) + "\n", encoding="utf-8")

    print(json.dumps(artifact, ensure_ascii=True) if args.json else json.dumps(artifact, indent=2, ensure_ascii=False))
    return 0 if artifact["summary"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
