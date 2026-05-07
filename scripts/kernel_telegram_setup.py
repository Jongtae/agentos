#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib import request as urllib_request

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.capability_substrate import _manifest_path
from kernel.operator_activity import append_activity_event

TELEGRAM_SETUP_SCHEMA = "agentos-telegram-setup.v1"
TELEGRAM_SETUP_MANIFEST = "latest-telegram-setup.json"
BOTFATHER_URL = "https://t.me/BotFather"
TELEGRAM_WEB_URL = "https://web.telegram.org/"
TELEGRAM_DESKTOP_URL = "https://desktop.telegram.org/"
SETUP_PAGE_SCHEMA = "agentos-telegram-setup-page.v1"
TELEGRAM_POLLING_SERVICE = "agentos-telegram-live-loop.service"
TELEGRAM_WEBHOOK_SERVICE = "agentos-telegram-webhookd.service"


def _redact_token(token: str) -> str:
    token = str(token or "").strip()
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def _get_json(url: str) -> tuple[int, dict]:
    req = urllib_request.Request(url, headers={"User-Agent": "AgentOS/0.1"})
    with urllib_request.urlopen(req, timeout=10) as response:
        raw = response.read(100_000)
        try:
            return int(response.status), json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except Exception:
            return int(response.status), {"raw_text": raw.decode("utf-8", errors="replace")}


def _looks_like_telegram_polling_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return "409" in text and "conflict" in text


def _safe_error(exc: Exception, token: str = "") -> str:
    text = str(exc)
    token = str(token or "").strip()
    if token:
        text = text.replace(token, _redact_token(token))
    return text


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _quote_env(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_env_file(path)
    existing.update({key: value for key, value in updates.items() if value != ""})
    lines = [f"{key}={_quote_env(existing[key])}" for key in sorted(existing)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _extract_chat_id(updates: list[dict]) -> str:
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get("message")
        if not isinstance(message, dict):
            message = update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if isinstance(chat, dict) and chat.get("id") is not None:
            return str(chat.get("id", "")).strip()
    return ""


def _telegram_url(api_base_url: str, token: str, method: str, query: dict | None = None) -> str:
    url = f"{api_base_url.rstrip('/')}/bot{token}/{method}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def _clear_telegram_webhook(api_base_url: str, token: str) -> dict:
    result = {
        "webhook_clear_attempted": True,
        "webhook_clear_ok": False,
        "webhook_clear_status_code": 0,
        "webhook_clear_error": "",
    }
    try:
        status, payload = _get_json(
            _telegram_url(api_base_url, token, "deleteWebhook", {"drop_pending_updates": "false"})
        )
        result["webhook_clear_status_code"] = status
        result["webhook_clear_ok"] = bool(isinstance(payload, dict) and payload.get("ok", False))
    except Exception as exc:
        result["webhook_clear_error"] = _safe_error(exc, token)
    return result


def build_telegram_setup_report(
    workspace_dir: str | Path,
    *,
    env_file: str | Path | None = None,
    token: str = "",
    chat_id: str = "",
    api_base_url: str = "",
    write_env: bool = True,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    env_path = Path(env_file or os.environ.get("AGENTOS_ENV_FILE", Path.home() / ".config" / "agentos" / "env")).expanduser()
    env_values = _read_env_file(env_path)
    token_value = (token or env_values.get("AGENTOS_TELEGRAM_BOT_TOKEN") or env_values.get("TELEGRAM_BOT_TOKEN") or env_values.get("AGENTOS_TELEGRAM_TOKEN") or "").strip()
    chat_id_value = (chat_id or env_values.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS") or env_values.get("TELEGRAM_ALLOWED_CHAT_IDS") or "").strip()
    api_base = (api_base_url or env_values.get("AGENTOS_TELEGRAM_API_BASE_URL") or env_values.get("TELEGRAM_API_BASE_URL") or os.environ.get("AGENTOS_TELEGRAM_API_BASE_URL") or "https://api.telegram.org").strip() or "https://api.telegram.org"
    webhook_public_url = (
        env_values.get("AGENTOS_TELEGRAM_WEBHOOK_PUBLIC_URL")
        or env_values.get("TELEGRAM_WEBHOOK_PUBLIC_URL")
        or os.environ.get("AGENTOS_TELEGRAM_WEBHOOK_PUBLIC_URL")
        or os.environ.get("TELEGRAM_WEBHOOK_PUBLIC_URL")
        or ""
    ).strip()
    target_transport = "webhook" if webhook_public_url else "polling"

    payload = {
        "schema_version": TELEGRAM_SETUP_SCHEMA,
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_setup",
        "setup_mode": "terminal_only",
        "botfather_url": BOTFATHER_URL,
        "telegram_web_url": TELEGRAM_WEB_URL,
        "telegram_desktop_url": TELEGRAM_DESKTOP_URL,
        "env_file": str(env_path),
        "token_configured": bool(token_value),
        "token_masked": _redact_token(token_value),
        "get_me_attempted": False,
        "get_me_ok": False,
        "bot_username": "",
        "chat_id_auto_attempted": False,
        "chat_id_auto_detected": False,
        "chat_id_configured": bool(chat_id_value),
        "chat_id": chat_id_value,
        "target_transport": target_transport,
        "webhook_public_url_configured": bool(webhook_public_url),
        "webhook_clear_attempted": False,
        "webhook_clear_ok": False,
        "env_written": False,
        "proof": {"ok": False, "reason": ""},
        "summary": {},
        "artifacts": {},
    }

    if not token_value:
        payload["proof"]["reason"] = "telegram_token_missing"
    else:
        payload["get_me_attempted"] = True
        try:
            status, get_me = _get_json(_telegram_url(api_base, token_value, "getMe"))
            payload["transport"] = {"api_base_url": api_base, "get_me_status_code": status}
            payload["get_me_ok"] = bool(isinstance(get_me, dict) and get_me.get("ok", False))
            result = get_me.get("result", {}) if isinstance(get_me, dict) else {}
            payload["bot_username"] = str(result.get("username", "") if isinstance(result, dict) else "")
            if not payload["get_me_ok"]:
                payload["proof"]["reason"] = "telegram_token_invalid"
        except Exception as exc:
            payload["transport"] = {"api_base_url": api_base, "error": _safe_error(exc, token_value)}
            payload["proof"]["reason"] = "telegram_token_validation_failed"

    if payload["get_me_ok"] and not chat_id_value:
        payload["chat_id_auto_attempted"] = True
        try:
            try:
                status, updates_payload = _get_json(_telegram_url(api_base, token_value, "getUpdates", {"limit": 10, "timeout": 0}))
            except Exception as exc:
                if not _looks_like_telegram_polling_conflict(exc):
                    raise
                payload.setdefault("transport", {})["poll_conflict_detected"] = True
                payload.setdefault("transport", {})["webhook_active"] = True
                payload["proof"]["reason"] = "telegram_webhook_active_chat_id_lookup_blocked"
                status, updates_payload = 409, {"ok": False, "result": []}
            payload.setdefault("transport", {})["get_updates_status_code"] = status
            updates = updates_payload.get("result", []) if isinstance(updates_payload, dict) else []
            chat_id_value = _extract_chat_id(updates if isinstance(updates, list) else [])
            payload["chat_id"] = chat_id_value
            payload["chat_id_auto_detected"] = bool(chat_id_value)
            payload["chat_id_configured"] = bool(chat_id_value)
            if not chat_id_value and payload["proof"].get("reason") != "telegram_webhook_active_chat_id_lookup_blocked":
                payload["proof"]["reason"] = "telegram_chat_id_missing"
        except Exception as exc:
            payload.setdefault("transport", {})["get_updates_error"] = _safe_error(exc, token_value)
            payload["proof"]["reason"] = "telegram_chat_id_lookup_failed"

    if payload["get_me_ok"] and chat_id_value:
        payload["chat_id"] = chat_id_value
        payload["chat_id_configured"] = True
        if write_env:
            updates = {
                "AGENTOS_TELEGRAM_BOT_TOKEN": token_value,
                "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": chat_id_value,
                "AGENTOS_TELEGRAM_TRANSPORT": target_transport,
            }
            if target_transport == "polling":
                updates["AGENTOS_TELEGRAM_POLLING_ENABLED"] = "true"
            if api_base != "https://api.telegram.org":
                updates["AGENTOS_TELEGRAM_API_BASE_URL"] = api_base
            if webhook_public_url:
                updates["AGENTOS_TELEGRAM_WEBHOOK_PUBLIC_URL"] = webhook_public_url
            _write_env_file(env_path, updates)
            payload["env_written"] = env_path.is_file() and env_path.stat().st_size > 0
        if target_transport == "polling":
            webhook_clear = _clear_telegram_webhook(api_base, token_value)
            payload.update(
                {
                    "webhook_clear_attempted": bool(webhook_clear.get("webhook_clear_attempted", False)),
                    "webhook_clear_ok": bool(webhook_clear.get("webhook_clear_ok", False)),
                }
            )
            payload.setdefault("transport", {}).update(webhook_clear)
        payload["proof"]["ok"] = bool((not write_env) or payload["env_written"])
        payload["proof"]["reason"] = "" if payload["proof"]["ok"] else "telegram_env_write_failed"
        if payload["proof"]["ok"]:
            receiver_activation = _activate_receiver_service(target_transport)
            payload["receiver_activation"] = receiver_activation
            append_activity_event(
                workspace,
                kind="setup.completed",
                source_label="Telegram",
                human_message=(
                    "Telegram connected. "
                    f"Bot: @{payload.get('bot_username', '-') or '-'}; "
                    f"Chat: {payload.get('chat_id', '-') or '-'}; "
                    "Receiver: active. Try now: send status or search AgentOS roadmap."
                ),
                request_id="telegram-setup",
                intent="telegram_setup",
                capability="telegram_setup",
                action="complete_setup",
                decision={"state": "completed"},
            )

    payload["summary"] = {
        "token_configured": bool(payload["token_configured"]),
        "get_me_ok": bool(payload["get_me_ok"]),
        "chat_id_configured": bool(payload["chat_id_configured"]),
        "chat_id_auto_detected": bool(payload["chat_id_auto_detected"]),
        "env_written": bool(payload["env_written"]),
        "target_transport": target_transport,
        "webhook_clear_attempted": bool(payload["webhook_clear_attempted"]),
        "webhook_clear_ok": bool(payload["webhook_clear_ok"]),
        "receiver_activation_attempted": bool(payload.get("receiver_activation", {}).get("attempted", False)),
        "receiver_activation_ok": bool(payload.get("receiver_activation", {}).get("ok", False)),
        "failure_class": "" if payload["proof"]["ok"] else str(payload["proof"].get("reason", "")),
    }
    if write_manifest:
        manifest = _manifest_path(workspace, TELEGRAM_SETUP_MANIFEST)
        manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
        payload["artifacts"]["latest_telegram_setup_manifest_json"] = str(manifest)
    return payload


def _activate_receiver_service(target_transport: str) -> dict:
    service = TELEGRAM_WEBHOOK_SERVICE if target_transport == "webhook" else TELEGRAM_POLLING_SERVICE
    payload = {
        "attempted": False,
        "ok": False,
        "service": service,
        "method": "",
        "returncode": None,
        "error": "",
    }
    if os.environ.get("AGENTOS_TELEGRAM_ACTIVATE_RECEIVER", "1").strip().lower() in {"0", "false", "no", "off"}:
        payload["error"] = "disabled_by_env"
        return payload
    command_prefixes: list[list[str]] = []
    if command := os.environ.get("AGENTOS_SYSTEMCTL_CMD", "").strip():
        command_prefixes.append([command])
    command_prefixes.append(["systemctl"])
    if os.geteuid() != 0:
        command_prefixes.append(["sudo", "-n", "systemctl"])

    for prefix in command_prefixes:
        executable = prefix[0]
        if not shutil.which(executable):
            continue
        payload["attempted"] = True
        payload["method"] = " ".join(prefix + ["restart", service])
        try:
            proc = subprocess.run(
                prefix + ["restart", service],
                text=True,
                capture_output=True,
                timeout=8,
                check=False,
            )
        except Exception as exc:
            payload["error"] = _safe_error(exc)
            continue
        payload["returncode"] = proc.returncode
        if proc.returncode == 0:
            payload["ok"] = True
            payload["error"] = ""
            return payload
        payload["error"] = _safe_error(RuntimeError((proc.stderr or proc.stdout or "").strip()))
    if not payload["attempted"] and not payload["error"]:
        payload["error"] = "systemctl_unavailable"
    return payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_SETUP_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_SETUP_SCHEMA}")
    if payload.get("capability") != "telegram_setup":
        errors.append("capability must be telegram_setup")
    for key in ("token_configured", "get_me_attempted", "get_me_ok", "chat_id_configured", "env_written"):
        if not isinstance(payload.get(key), bool):
            errors.append(f"{key} must be a boolean")
    rendered = json.dumps(payload, ensure_ascii=True)
    for raw_key in ("AGENTOS_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "AGENTOS_TELEGRAM_TOKEN"):
        if raw_key in rendered:
            errors.append("payload must not include token env key names")
    return errors


def _render_setup_page(
    *,
    message: str,
    proof_ok: bool = False,
    failure_class: str = "",
    bot_username: str = "",
    chat_id: str = "",
    token_known: bool = False,
    target_transport: str = "polling",
) -> bytes:
    status = "Connected" if proof_ok else "Waiting for token"
    safe_message = html.escape(message)
    safe_failure = html.escape(failure_class)
    safe_bot = html.escape(bot_username)
    safe_chat = html.escape(chat_id)
    safe_transport = html.escape(target_transport or "polling")
    token_hint = (
        "Token captured. You may leave this blank while retrying chat id detection."
        if token_known and not proof_ok
        else "Paste token once. AgentOS will not show it again."
    )
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentOS Telegram Setup</title>
  <style>
    body {{ margin: 0; background: #101315; color: #ecf2ec; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 32px 20px; }}
    .card {{ border: 1px solid #314039; border-radius: 18px; padding: 24px; background: linear-gradient(145deg, #17201c, #111718); box-shadow: 0 16px 48px rgba(0,0,0,.28); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    p {{ line-height: 1.5; color: #b9c7bf; }}
    label {{ display: block; margin-top: 18px; font-weight: 700; }}
    input {{ width: 100%; box-sizing: border-box; margin-top: 8px; border-radius: 12px; border: 1px solid #3c5048; background: #0a0f0d; color: #f8fff9; padding: 14px; font-size: 16px; }}
    button {{ margin-top: 20px; border: 0; border-radius: 999px; padding: 13px 18px; background: #8ddf9e; color: #06100a; font-weight: 800; font-size: 16px; cursor: pointer; }}
    .status {{ display: inline-flex; border-radius: 999px; padding: 8px 12px; background: #24362f; color: #c9f8d1; font-weight: 700; }}
    .ok {{ background: #163d22; color: #bbffc8; }}
	    .warn {{ background: #3f2f15; color: #ffe3a3; }}
	    .note {{ border: 1px solid #355143; border-radius: 14px; padding: 12px 14px; background: #0d1512; margin: 16px 0; }}
	    code {{ background: #0a0f0d; padding: 2px 6px; border-radius: 6px; }}
	    a {{ color: #9eeeb1; }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <div class="status {'ok' if proof_ok else 'warn'}">{html.escape(status)}</div>
      <h1>AgentOS Telegram Setup</h1>
      <p>{safe_message}</p>
	      <ol>
	        <li>Open <a href="{BOTFATHER_URL}">BotFather</a> on your phone or host.</li>
	        <li>If needed, send <code>/newbot</code>, choose a name and username, then copy the token.</li>
	        <li>Paste the token below. Then send <code>/start</code> to your bot so AgentOS can detect your chat id.</li>
	      </ol>
	      <div class="note">
        <strong>Network tip:</strong> phone QR setup works best when the VM network is <strong>Bridged</strong>.
        If this page does not open from your phone, keep this page open from the Mac host browser instead.
      </div>
      <div class="note">
        <strong>Runtime path:</strong> AgentOS will use <strong>{safe_transport}</strong> after setup.
        If no public webhook URL is configured, AgentOS clears stale Telegram webhooks and listens with its built-in background receiver.
      </div>
	      <form method="post" action="/setup">
        <label for="token">Telegram bot token</label>
        <input id="token" name="token" type="password" autocomplete="off" autofocus placeholder="123456789:AA..." />
        <p>{html.escape(token_hint)}</p>
        <label for="chat_id">Chat ID, optional fallback</label>
        <input id="chat_id" name="chat_id" type="text" inputmode="numeric" placeholder="Leave blank for auto-detect after /start" />
        <button type="submit">Connect Telegram</button>
      </form>
      <p>Bot: <strong>{safe_bot or "-"}</strong><br>Chat ID: <strong>{safe_chat or "-"}</strong><br>Issue: <strong>{safe_failure or "-"}</strong></p>
      <p>No token is shown in this page after submit, and AgentOS writes it only to the local env file.</p>
    </div>
  </main>
</body>
</html>"""
    return body.encode("utf-8")


def _display_setup_url(host: str, display_host: str | None, port: int) -> str:
    url_host = (display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host)).strip()
    return f"http://{url_host}:{port}/setup"


def _connect_host_for_bind_host(host: str) -> str:
    return "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host


def _port_accepts_connections(host: str, port: int) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((_connect_host_for_bind_host(host), port), timeout=0.2):
            return True
    except OSError:
        return False


def serve_telegram_setup_page_background(
    workspace_dir: str | Path,
    *,
    env_file: str | Path | None = None,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8787,
    api_base_url: str = "",
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
) -> dict:
    workspace_path = Path(workspace_dir).expanduser()
    artifacts_dir = workspace_path / "artifacts" / "telegram-setup"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    setup_url = _display_setup_url(host, display_host, port) if port > 0 else ""
    url_path = Path(url_file).expanduser() if url_file else artifacts_dir / "setup-page-url.txt"
    log_path = artifacts_dir / "setup-page-server.log"
    pid_path = artifacts_dir / "setup-page-server.pid"

    if port > 0 and _port_accepts_connections(host, port):
        latest_manifest = _manifest_path(workspace_path, TELEGRAM_SETUP_MANIFEST)
        latest_payload = _read_json_file(latest_manifest)
        completed = bool(latest_payload.get("proof", {}).get("ok", False))
        if setup_url:
            url_path.write_text(setup_url + "\n", encoding="utf-8")
        return {
            "schema_version": SETUP_PAGE_SCHEMA,
            "setup_page_started": True,
            "setup_page_background": True,
            "setup_page_already_running": True,
            "setup_page_url": setup_url,
            "setup_page_bound_host": host,
            "setup_page_display_host": (display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host)).strip(),
            "setup_page_bound_port": port,
            "completed": completed,
            "failure_class": "",
            "operator_action_required": "open_setup_page",
            "log_path": str(log_path),
            "pid_path": str(pid_path),
            "telegram_setup": latest_payload,
        }

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--workspace",
        str(workspace_path),
        "--serve-http",
        "--host",
        host,
        "--display-host",
        display_host,
        "--port",
        str(port),
        "--timeout-sec",
        str(timeout_sec),
        "--url-file",
        str(url_path),
        "--json",
    ]
    if env_file:
        cmd.extend(["--env-file", str(env_file)])
    if api_base_url:
        cmd.extend(["--api-base-url", api_base_url])

    with log_path.open("ab") as log_handle:
        proc = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    pid_path.write_text(str(proc.pid) + "\n", encoding="utf-8")

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if url_path.exists():
            setup_url = url_path.read_text(encoding="utf-8").strip()
            break
        if port > 0 and _port_accepts_connections(host, port):
            setup_url = _display_setup_url(host, display_host, port)
            url_path.write_text(setup_url + "\n", encoding="utf-8")
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)

    if proc.poll() is not None and not setup_url:
        return {
            "schema_version": SETUP_PAGE_SCHEMA,
            "setup_page_started": False,
            "setup_page_background": True,
            "setup_page_already_running": False,
            "setup_page_url": "",
            "setup_page_bound_host": host,
            "setup_page_display_host": display_host,
            "setup_page_bound_port": port,
            "completed": False,
            "failure_class": "telegram_setup_page_start_failed",
            "operator_action_required": "check_log",
            "log_path": str(log_path),
            "pid_path": str(pid_path),
            "telegram_setup": {},
        }

    return {
        "schema_version": SETUP_PAGE_SCHEMA,
        "setup_page_started": True,
        "setup_page_background": True,
        "setup_page_already_running": False,
        "setup_page_url": setup_url,
        "setup_page_bound_host": host,
        "setup_page_display_host": display_host,
        "setup_page_bound_port": port,
        "completed": False,
        "failure_class": "",
        "operator_action_required": "open_setup_page",
        "log_path": str(log_path),
        "pid_path": str(pid_path),
        "telegram_setup": {},
    }


def serve_telegram_setup_page(
    workspace_dir: str | Path,
    *,
    env_file: str | Path | None = None,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8787,
    api_base_url: str = "",
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
) -> dict:
    state: dict[str, object] = {
        "schema_version": SETUP_PAGE_SCHEMA,
        "setup_page_started": True,
        "setup_page_url": "",
        "setup_page_bound_host": host,
        "setup_page_bound_port": port,
        "completed": False,
        "payload": {},
        "failure_class": "",
        "pending_token": "",
    }
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/setup"}:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
            proof = payload.get("proof", {}) if isinstance(payload, dict) else {}
            token_known = bool(state.get("pending_token")) or bool(payload.get("token_configured", False))
            body = _render_setup_page(
                message="Paste your Telegram bot token here instead of typing it into the VM console.",
                proof_ok=bool(proof.get("ok")),
                failure_class=str((payload.get("summary", {}) if isinstance(payload, dict) else {}).get("failure_class", "")),
                bot_username=str(payload.get("bot_username", "") if isinstance(payload, dict) else ""),
                chat_id=str(payload.get("chat_id", "") if isinstance(payload, dict) else ""),
                token_known=token_known,
                target_transport=str(payload.get("target_transport", "polling") if isinstance(payload, dict) else "polling"),
            )
            self._send(200, body)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/setup":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
            token = form.get("token", [""])[0].strip() or str(state.get("pending_token", "") or "")
            chat_id = form.get("chat_id", [""])[0].strip()
            if token:
                state["pending_token"] = token
            payload = build_telegram_setup_report(
                workspace_dir,
                env_file=env_file,
                token=token,
                chat_id=chat_id,
                api_base_url=api_base_url,
            )
            state["payload"] = payload
            state["completed"] = bool(payload.get("proof", {}).get("ok"))
            state["failure_class"] = str(payload.get("summary", {}).get("failure_class", ""))
            if state["completed"]:
                state["pending_token"] = ""
                done.set()
            message = (
                "Telegram is connected. Return to AgentOS; the TUI will update and the background receiver will pick up messages automatically."
                if state["completed"]
                else "Not connected yet. If chat id is missing, send /start to your bot and click Connect again, or enter chat id manually. You do not need to paste the token again on this page."
            )
            body = _render_setup_page(
                message=message,
                proof_ok=bool(state["completed"]),
                failure_class=str(state["failure_class"]),
                bot_username=str(payload.get("bot_username", "")),
                chat_id=str(payload.get("chat_id", "")),
                token_known=bool(state.get("pending_token")) or bool(payload.get("token_configured", False)),
                target_transport=str(payload.get("target_transport", "polling")),
            )
            self._send(200, body)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    actual_port = int(server.server_address[1])
    url_host = (display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host)).strip()
    setup_url = _display_setup_url(host, url_host, actual_port)
    state["setup_page_bound_port"] = actual_port
    state["setup_page_url"] = setup_url
    if url_file:
        Path(url_file).write_text(setup_url + "\n", encoding="utf-8")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        done.wait(timeout=max(1, int(timeout_sec)))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if not state["completed"] and not state["failure_class"]:
        state["failure_class"] = "telegram_setup_page_timeout"
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    return {
        "schema_version": SETUP_PAGE_SCHEMA,
        "setup_page_started": True,
        "setup_page_url": setup_url,
        "setup_page_bound_host": host,
        "setup_page_display_host": url_host,
        "setup_page_bound_port": actual_port,
        "completed": bool(state["completed"]),
        "failure_class": str(state["failure_class"]),
        "telegram_setup": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminal-only AgentOS Telegram bot setup")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--serve-http", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--display-host", default="")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--url-file", default="")
    parser.add_argument("--no-write-env", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("telegram setup: PASS" if result["ok"] else "telegram setup: FAIL"))
        return 0 if result["ok"] else 1

    if args.serve_http:
        serve_fn = serve_telegram_setup_page_background if args.background else serve_telegram_setup_page
        payload = serve_fn(
            args.workspace,
            env_file=args.env_file or None,
            host=args.host,
            display_host=args.display_host,
            port=args.port,
            api_base_url=args.api_base_url,
            timeout_sec=args.timeout_sec,
            url_file=args.url_file or None,
        )
        text = json.dumps(payload, ensure_ascii=True)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if payload.get("completed") or payload.get("setup_page_background") else 1

    token = args.token
    chat_id = args.chat_id
    if not token and not args.json:
        token = input("Telegram bot token: ").strip()
    payload = build_telegram_setup_report(
        args.workspace,
        env_file=args.env_file or None,
        token=token,
        chat_id=chat_id,
        api_base_url=args.api_base_url,
        write_env=not args.no_write_env,
    )
    if payload["proof"]["reason"] in {"telegram_chat_id_missing", "telegram_chat_id_lookup_failed"} and not args.json:
        print("Send /start to your bot from Telegram, then press Enter to retry chat id auto-detection.")
        input()
        payload = build_telegram_setup_report(
            args.workspace,
            env_file=args.env_file or None,
            token=token,
            api_base_url=args.api_base_url,
            write_env=not args.no_write_env,
        )
        if payload["proof"]["reason"] in {"telegram_chat_id_missing", "telegram_chat_id_lookup_failed"}:
            manual = input("Chat id was not auto-detected. Enter chat id manually, or leave blank to skip: ").strip()
            if manual:
                payload = build_telegram_setup_report(
                    args.workspace,
                    env_file=args.env_file or None,
                    token=token,
                    chat_id=manual,
                    api_base_url=args.api_base_url,
                    write_env=not args.no_write_env,
                )

    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_SETUP_SCHEMA)}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
