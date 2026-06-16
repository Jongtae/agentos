#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload, write_json_file
from kernel.capability_substrate import _manifest_path
from kernel.operator_activity import append_activity_event

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SETUP_SCHEMA = "agentos-gmail-setup.v1"
STATUS_SCHEMA = "agentos-gmail-status.v1"
READ_SCHEMA = "agentos-gmail-read.v1"
SETUP_PAGE_SCHEMA = "agentos-gmail-setup-page.v1"
GMAIL_SETUP_MANIFEST = "latest-gmail-setup.json"
GMAIL_STATUS_MANIFEST = "latest-gmail-status.json"
DEFAULT_TEST_QUERY = "newer_than:30d"


def default_credentials_path() -> Path:
    return Path(os.environ.get("AGENTOS_GMAIL_CREDENTIALS", "~/.agentos/secrets/gmail/credentials.json")).expanduser()


def default_token_path() -> Path:
    return Path(os.environ.get("AGENTOS_GMAIL_TOKEN", "~/.agentos/secrets/gmail/token.json")).expanduser()


def build_gmail_setup_report(
    workspace_dir: str | Path,
    *,
    credentials: str | Path = "",
    credentials_json: str = "",
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
    authorize: bool = False,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    target_credentials = Path(credentials_path).expanduser() if credentials_path else default_credentials_path()
    target_token = Path(token_path).expanduser() if token_path else default_token_path()

    payload = _base_payload(SETUP_SCHEMA, workspace, target_credentials, target_token)
    payload.update(
        {
            "capability": "gmail_setup",
            "credentials_registered": False,
            "oauth_authorize_attempted": False,
            "oauth_authorize_ok": False,
            "read_only_scope": GMAIL_SCOPE,
            "setup_mode": "desktop_oauth",
            "device_code_oauth_used": False,
            "device_code_oauth_excluded_reason": "google_limited_input_flow_does_not_allow_gmail_scopes",
            "operator_action_required": "",
            "proof": {"ok": False, "reason": ""},
        }
    )

    try:
        if credentials_json.strip():
            _write_secret_json(target_credentials, credentials_json)
        elif str(credentials or "").strip():
            source = Path(credentials).expanduser()
            _copy_secret_file(source, target_credentials)

        payload["credentials_registered"] = _looks_like_oauth_client_file(target_credentials)
        if not payload["credentials_registered"]:
            payload["proof"]["reason"] = "gmail_credentials_missing"
            payload["operator_action_required"] = "provide_google_oauth_desktop_client_credentials_json"
        elif authorize:
            payload["oauth_authorize_attempted"] = True
            auth_result = _run_desktop_oauth(target_credentials, target_token)
            payload.update(auth_result)
            if auth_result.get("oauth_authorize_ok"):
                payload["proof"]["ok"] = True
                payload["proof"]["reason"] = "gmail_oauth_ready"
            else:
                payload["proof"]["reason"] = str(auth_result.get("failure_class", "gmail_oauth_authorize_failed"))
                payload["operator_action_required"] = str(auth_result.get("operator_action_required", "complete_oauth_in_browser"))
        else:
            payload["proof"]["ok"] = True
            payload["proof"]["reason"] = "gmail_credentials_registered"
            payload["operator_action_required"] = "run_gmail_setup_with_authorize_or_copy_token_from_host"

        payload["token_configured"] = _looks_like_token_file(target_token)
        payload["summary"] = _summary(payload)
    except Exception as exc:
        payload["proof"]["reason"] = "gmail_setup_failed"
        payload["operator_action_required"] = "check_credentials_file_and_secret_permissions"
        payload["error"] = _safe_error(exc)
        payload["summary"] = _summary(payload)

    _emit_activity(workspace, "gmail.setup.checked", "Gmail setup checked", payload)
    if write_manifest:
        write_json_file(_manifest_path(workspace, GMAIL_SETUP_MANIFEST), scrub_payload(payload))
    return scrub_payload(payload)


def build_gmail_status_report(
    workspace_dir: str | Path,
    *,
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    credentials = Path(credentials_path).expanduser() if credentials_path else default_credentials_path()
    token = Path(token_path).expanduser() if token_path else default_token_path()
    dependencies = _google_dependency_status()
    credentials_ok = _looks_like_oauth_client_file(credentials)
    token_ok = _looks_like_token_file(token)
    ready = credentials_ok and token_ok and dependencies["available"]
    reason = ""
    if not credentials_ok:
        reason = "gmail_credentials_missing"
    elif not token_ok:
        reason = "gmail_token_missing"
    elif not dependencies["available"]:
        reason = "gmail_oauth_dependencies_missing"
    else:
        reason = "gmail_ready"
    payload = _base_payload(STATUS_SCHEMA, workspace, credentials, token)
    payload.update(
        {
            "capability": "gmail_status",
            "credentials_configured": credentials_ok,
            "token_configured": token_ok,
            "dependencies": dependencies,
            "read_only_scope": GMAIL_SCOPE,
            "live_read_ready": ready,
            "operator_action_required": "" if ready else _recovery_action(reason),
            "proof": {"ok": ready, "reason": reason},
            "summary": {
                "state": "ready" if ready else "blocked",
                "reason": reason,
                "credentials_path": str(credentials),
                "token_path": str(token),
                "secrets_redacted": True,
            },
        }
    )
    if write_manifest:
        manifest_path = _manifest_path(workspace, GMAIL_STATUS_MANIFEST)
        payload["artifacts"] = {"latest_gmail_status_json": str(manifest_path)}
        write_json_file(manifest_path, scrub_payload(payload))
    return scrub_payload(payload)


def build_gmail_read_report(
    workspace_dir: str | Path,
    *,
    query: str = DEFAULT_TEST_QUERY,
    max_results: int = 5,
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
    mock_response: str | Path = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    credentials = Path(credentials_path).expanduser() if credentials_path else default_credentials_path()
    token = Path(token_path).expanduser() if token_path else default_token_path()
    query = str(query or DEFAULT_TEST_QUERY).strip() or DEFAULT_TEST_QUERY

    payload = _base_payload(READ_SCHEMA, workspace, credentials, token)
    payload.update(
        {
            "capability": "gmail_read",
            "query": query,
            "max_results": max_results,
            "adapter": "gmail_oauth_readonly",
            "read_only_scope": GMAIL_SCOPE,
            "messages": [],
            "matched_count": 0,
            "summary": "",
            "operator_action_required": "",
            "proof": {"ok": False, "reason": ""},
        }
    )

    try:
        mock_path = Path(mock_response or os.environ.get("AGENTOS_GMAIL_MOCK_RESPONSE", "")).expanduser()
        if str(mock_response or os.environ.get("AGENTOS_GMAIL_MOCK_RESPONSE", "")).strip():
            messages = _messages_from_mock(mock_path, max_results=max_results)
            payload["messages"] = messages
            payload["matched_count"] = len(messages)
            payload["summary"] = _summarize_messages(messages, query=query)
            payload["adapter"] = "gmail_oauth_readonly_mock"
            payload["proof"] = {"ok": True, "reason": "mock_gmail_response_used"}
        else:
            status = build_gmail_status_report(
                workspace,
                credentials_path=credentials,
                token_path=token,
                write_manifest=False,
            )
            if not status.get("live_read_ready"):
                payload["proof"]["reason"] = str(status.get("proof", {}).get("reason", "gmail_live_read_not_ready"))
                payload["operator_action_required"] = str(status.get("operator_action_required", _recovery_action(payload["proof"]["reason"])))
            else:
                service = _build_gmail_service(credentials, token)
                messages = _read_gmail_messages(service, query=query, max_results=max_results)
                payload["messages"] = messages
                payload["matched_count"] = len(messages)
                payload["summary"] = _summarize_messages(messages, query=query)
                payload["proof"] = {"ok": True, "reason": "gmail_live_read_ok"}
        _emit_activity(workspace, "gmail.read.checked", f"Gmail read checked for query: {query}", payload)
    except Exception as exc:
        payload["proof"]["reason"] = "gmail_read_failed"
        payload["operator_action_required"] = "run_gmail_status_and_retry_after_setup"
        payload["error"] = _safe_error(exc)

    if write_manifest:
        write_json_file(_manifest_path(workspace, "latest-gmail-read.json"), scrub_payload(payload))
    return scrub_payload(payload)


def serve_gmail_setup_page_background(
    workspace_dir: str | Path,
    *,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8789,
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
) -> dict:
    workspace_path = Path(workspace_dir).expanduser()
    artifacts_dir = workspace_path / "artifacts" / "gmail-setup"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    setup_url = _display_setup_url(host, display_host, port) if port > 0 else ""
    url_path = Path(url_file).expanduser() if url_file else artifacts_dir / "setup-page-url.txt"
    log_path = artifacts_dir / "setup-page-server.log"
    pid_path = artifacts_dir / "setup-page-server.pid"

    if port > 0 and _port_accepts_connections(host, port):
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
            "completed": False,
            "failure_class": "",
            "operator_action_required": "open_setup_page",
            "log_path": str(log_path),
            "pid_path": str(pid_path),
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
    if credentials_path:
        cmd.extend(["--credentials-path", str(credentials_path)])
    if token_path:
        cmd.extend(["--token-path", str(token_path)])

    with log_path.open("ab") as log_handle:
        proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
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

    return {
        "schema_version": SETUP_PAGE_SCHEMA,
        "setup_page_started": bool(setup_url) or proc.poll() is None,
        "setup_page_background": True,
        "setup_page_already_running": False,
        "setup_page_url": setup_url,
        "setup_page_bound_host": host,
        "setup_page_display_host": display_host,
        "setup_page_bound_port": port,
        "completed": False,
        "failure_class": "" if (bool(setup_url) or proc.poll() is None) else "gmail_setup_page_start_failed",
        "operator_action_required": "open_setup_page" if (bool(setup_url) or proc.poll() is None) else "check_log",
        "log_path": str(log_path),
        "pid_path": str(pid_path),
    }


def serve_gmail_setup_page(
    workspace_dir: str | Path,
    *,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8789,
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
) -> dict:
    state: dict[str, object] = {"completed": False, "payload": {}, "failure_class": ""}
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
            status_payload = build_gmail_status_report(
                workspace_dir,
                credentials_path=credentials_path,
                token_path=token_path,
                write_manifest=False,
            )
            self._send(200, _render_setup_page(status_payload, message="Configure Gmail read-only access for AgentOS."))

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/setup", "/test-read"}:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form = _parse_form(self.headers.get("Content-Type", ""), raw)
            if self.path == "/setup":
                payload = build_gmail_setup_report(
                    workspace_dir,
                    credentials=str(form.get("credentials_path", "")).strip(),
                    credentials_json=str(form.get("credentials_json", "")).strip() or str(form.get("credentials_file", "")).strip(),
                    credentials_path=credentials_path,
                    token_path=token_path,
                    authorize=str(form.get("authorize", "")).strip() == "1",
                )
                state["payload"] = payload
                message = (
                    "Credentials are registered. Complete OAuth locally or copy a host-generated token into the VM secret path."
                    if payload.get("credentials_registered")
                    else "Credentials are still missing. Paste or upload a Google OAuth Desktop client credentials.json."
                )
                status_payload = build_gmail_status_report(
                    workspace_dir,
                    credentials_path=credentials_path,
                    token_path=token_path,
                    write_manifest=False,
                )
                self._send(200, _render_setup_page(status_payload, message=message, setup_payload=payload))
                return
            read_payload = build_gmail_read_report(
                workspace_dir,
                query=str(form.get("query", DEFAULT_TEST_QUERY)).strip() or DEFAULT_TEST_QUERY,
                credentials_path=credentials_path,
                token_path=token_path,
            )
            state["payload"] = read_payload
            state["completed"] = bool(read_payload.get("proof", {}).get("ok", False))
            if state["completed"]:
                done.set()
            status_payload = build_gmail_status_report(
                workspace_dir,
                credentials_path=credentials_path,
                token_path=token_path,
                write_manifest=False,
            )
            self._send(200, _render_setup_page(status_payload, message="Gmail read-only test finished.", read_payload=read_payload))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    actual_port = int(server.server_address[1])
    url_host = (display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host)).strip()
    setup_url = _display_setup_url(host, url_host, actual_port)
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
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    return {
        "schema_version": SETUP_PAGE_SCHEMA,
        "setup_page_started": True,
        "setup_page_url": setup_url,
        "setup_page_bound_host": host,
        "setup_page_display_host": url_host,
        "setup_page_bound_port": actual_port,
        "completed": bool(state["completed"]),
        "failure_class": "" if state["completed"] else "gmail_setup_page_timeout",
        "operator_action_required": "" if state["completed"] else "open_setup_page_or_run_gmail_status",
        "gmail_setup": payload,
    }


def validate_payload(payload: dict, expected_schema: str = "") -> list[str]:
    errors: list[str] = []
    schema = expected_schema or str(payload.get("schema_version", ""))
    if payload.get("schema_version") != schema:
        errors.append("schema_version mismatch")
    if "proof" not in payload or not isinstance(payload.get("proof"), dict):
        errors.append("proof object missing")
    rendered = json.dumps(payload, ensure_ascii=True)
    for forbidden in ("refresh_token", "client_secret", "access_token"):
        if forbidden in rendered:
            errors.append(f"secret-like field leaked: {forbidden}")
    return errors


def _base_payload(schema: str, workspace: Path, credentials: Path, token: Path) -> dict:
    return {
        "schema_version": schema,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "credentials_path": str(credentials),
        "token_path": str(token),
        "secrets_redacted": True,
    }


def _copy_secret_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"credentials file not found: {source}")
    _write_secret_json(target, source.read_text(encoding="utf-8"))


def _write_secret_json(target: Path, content: str) -> None:
    parsed = json.loads(content)
    if "installed" not in parsed and "web" not in parsed:
        raise ValueError("credentials.json must be a Google OAuth client file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(parsed, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    try:
        target.parent.chmod(stat.S_IRWXU)
    except OSError:
        pass


def _looks_like_oauth_client_file(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    client = payload.get("installed") if isinstance(payload.get("installed"), dict) else payload.get("web")
    return isinstance(client, dict) and bool(client.get("client_id"))


def _looks_like_token_file(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(payload.get("token") or payload.get("refresh_token"))


def _google_dependency_status() -> dict:
    missing = []
    for module in ("googleapiclient.discovery", "google_auth_oauthlib.flow", "google.oauth2.credentials"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    return {"available": not missing, "missing": missing}


def _run_desktop_oauth(credentials: Path, token: Path) -> dict:
    deps = _google_dependency_status()
    if not deps["available"]:
        return {
            "oauth_authorize_ok": False,
            "failure_class": "gmail_oauth_dependencies_missing",
            "operator_action_required": "install_requirements_or_use_host_assisted_token_copy",
            "dependencies": deps,
        }
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials), scopes=[GMAIL_SCOPE])
    creds = flow.run_local_server(port=0)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json() + "\n", encoding="utf-8")
    token.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {"oauth_authorize_ok": True, "dependencies": deps}


def _build_gmail_service(credentials: Path, token: Path):
    deps = _google_dependency_status()
    if not deps["available"]:
        raise RuntimeError("gmail oauth dependencies missing")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(token), [GMAIL_SCOPE])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json() + "\n", encoding="utf-8")
        token.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if not creds.valid:
        raise RuntimeError("gmail token invalid")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _read_gmail_messages(service, *, query: str, max_results: int) -> list[dict]:
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    refs = result.get("messages", []) if isinstance(result, dict) else []
    messages = []
    for ref in refs[:max_results]:
        msg = service.users().messages().get(userId="me", id=ref.get("id"), format="full").execute()
        messages.append(_normalize_gmail_message(msg))
    return messages


def _normalize_gmail_message(msg: dict) -> dict:
    payload = msg.get("payload", {}) if isinstance(msg, dict) else {}
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    header_map = {str(item.get("name", "")).lower(): str(item.get("value", "")) for item in headers if isinstance(item, dict)}
    date_text = header_map.get("date", "")
    date_iso = ""
    if date_text:
        try:
            date_iso = parsedate_to_datetime(date_text).isoformat()
        except Exception:
            date_iso = date_text
    return {
        "id": str(msg.get("id", "")),
        "thread_id": str(msg.get("threadId", "")),
        "from": header_map.get("from", ""),
        "to": header_map.get("to", ""),
        "subject": header_map.get("subject", ""),
        "date": date_iso,
        "snippet": str(msg.get("snippet", "")),
        "body_preview": _preview(_extract_body_text(payload), 600),
    }


def _extract_body_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    body = payload.get("body", {}) if isinstance(payload.get("body"), dict) else {}
    data = body.get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(str(data) + "==").decode("utf-8", errors="replace")
        except Exception:
            return ""
    parts = payload.get("parts", []) if isinstance(payload.get("parts"), list) else []
    for part in parts:
        text = _extract_body_text(part)
        if text:
            return text
    return ""


def _messages_from_mock(path: Path, *, max_results: int) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_messages = payload.get("messages", payload if isinstance(payload, list) else [])
    return [_normalize_mock_message(item) for item in raw_messages[:max_results] if isinstance(item, dict)]


def _normalize_mock_message(item: dict) -> dict:
    return {
        "id": str(item.get("id", "")),
        "thread_id": str(item.get("thread_id", item.get("threadId", ""))),
        "from": str(item.get("from", "")),
        "to": str(item.get("to", "")),
        "subject": str(item.get("subject", "")),
        "date": str(item.get("date", "")),
        "snippet": str(item.get("snippet", item.get("body", "")))[:240],
        "body_preview": _preview(item.get("body", item.get("snippet", "")), 600),
    }


def _summarize_messages(messages: list[dict], *, query: str) -> str:
    if not messages:
        return f"No Gmail messages matched query: {query}"
    lines = [f"Found {len(messages)} Gmail message(s) for query: {query}"]
    for message in messages[:5]:
        subject = message.get("subject") or "(no subject)"
        sender = message.get("from") or "(unknown sender)"
        snippet = _preview(message.get("snippet") or message.get("body_preview"), 140)
        lines.append(f"- {subject} from {sender}: {snippet}")
    return "\n".join(lines)


def _summary(payload: dict) -> dict:
    return {
        "state": "ready" if payload.get("proof", {}).get("ok") else "blocked",
        "reason": payload.get("proof", {}).get("reason", ""),
        "credentials_path": payload.get("credentials_path", ""),
        "token_path": payload.get("token_path", ""),
        "secrets_redacted": True,
    }


def _recovery_action(reason: str) -> str:
    if reason == "gmail_credentials_missing":
        return "run agentos-kernelctl gmail-setup --serve-http and provide Google OAuth Desktop credentials.json"
    if reason == "gmail_token_missing":
        return "complete Gmail OAuth on host or VM, then place token.json in the AgentOS Gmail secret path"
    if reason == "gmail_oauth_dependencies_missing":
        return "install Google OAuth client dependencies from requirements.txt, then rerun gmail-setup"
    return "run agentos-kernelctl gmail-status --json for setup details"


def _emit_activity(workspace: Path, kind: str, message: str, payload: dict) -> None:
    append_activity_event(
        workspace,
        kind=kind,
        source_label="AgentOS",
        human_message=message,
        request_id="gmail-setup",
        intent="gmail_read_or_draft",
        capability=str(payload.get("capability", "gmail_setup")),
        decision={"state": "completed" if payload.get("proof", {}).get("ok") else "blocked"},
    )


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


def _parse_form(content_type: str, raw: bytes) -> dict[str, str]:
    if "multipart/form-data" in content_type and "boundary=" in content_type:
        boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
        return _parse_multipart(raw, boundary)
    parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _parse_multipart(raw: bytes, boundary: str) -> dict[str, str]:
    result: dict[str, str] = {}
    marker = ("--" + boundary).encode("utf-8")
    for part in raw.split(marker):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        header_blob, body = part.split(b"\r\n\r\n", 1)
        headers = header_blob.decode("utf-8", errors="replace")
        name = ""
        for piece in headers.split(";"):
            piece = piece.strip()
            if piece.startswith("name="):
                name = piece.split("=", 1)[1].strip('"')
        if name:
            result[name] = body.rstrip(b"\r\n-").decode("utf-8", errors="replace")
    return result


def _render_setup_page(status_payload: dict, *, message: str, setup_payload: dict | None = None, read_payload: dict | None = None) -> bytes:
    credentials_path = html.escape(str(status_payload.get("credentials_path", "")))
    token_path = html.escape(str(status_payload.get("token_path", "")))
    state = "Ready" if status_payload.get("live_read_ready") else "Needs setup"
    reason = html.escape(str(status_payload.get("proof", {}).get("reason", "")))
    safe_message = html.escape(message)
    setup_summary = html.escape(json.dumps((setup_payload or {}).get("summary", {}), ensure_ascii=True))
    read_summary = html.escape(str((read_payload or {}).get("summary", "")))
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AgentOS Gmail Setup</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; padding: 32px; background: Canvas; color: CanvasText; }}
    main {{ max-width: 760px; margin: 0 auto; }}
    .card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 8px; padding: 24px; }}
    .status {{ display: inline-block; padding: 6px 10px; border-radius: 999px; background: color-mix(in srgb, CanvasText 10%, Canvas); font-weight: 700; }}
    label {{ display: block; margin-top: 16px; font-weight: 650; }}
    input, textarea {{ box-sizing: border-box; width: 100%; margin-top: 6px; padding: 10px; border-radius: 6px; border: 1px solid color-mix(in srgb, CanvasText 24%, Canvas); font: inherit; }}
    textarea {{ min-height: 150px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    button {{ margin-top: 16px; padding: 10px 14px; border-radius: 6px; border: 0; font: inherit; font-weight: 700; cursor: pointer; }}
    .note {{ margin-top: 16px; padding: 12px; border-left: 4px solid color-mix(in srgb, CanvasText 40%, Canvas); background: color-mix(in srgb, CanvasText 6%, Canvas); }}
    code, pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <div class="status">{html.escape(state)}</div>
      <h1>AgentOS Gmail Setup</h1>
      <p>{safe_message}</p>
      <p>Reason: <strong>{reason or "-"}</strong></p>
      <p>Credentials: <code>{credentials_path}</code><br />Token: <code>{token_path}</code></p>
      <div class="note">
        AgentOS uses only <code>{GMAIL_SCOPE}</code>. Tokens and refresh tokens are never displayed here and are stored outside workspace records.
      </div>
      <div class="note">
        Headless VM path: run OAuth on the host if browser callback cannot reach the VM, then copy <code>token.json</code> into the VM token path above.
      </div>
      <form method="post" action="/setup" enctype="multipart/form-data">
        <label for="credentials_file">Upload credentials.json</label>
        <input id="credentials_file" name="credentials_file" type="file" accept="application/json,.json" />
        <label for="credentials_path">Or confirm existing credentials path</label>
        <input id="credentials_path" name="credentials_path" type="text" placeholder="/path/to/credentials.json" />
        <label for="credentials_json">Or paste credentials.json</label>
        <textarea id="credentials_json" name="credentials_json" autocomplete="off"></textarea>
        <label><input name="authorize" value="1" type="checkbox" /> Start local Desktop OAuth now</label>
        <button type="submit">Save Gmail Setup</button>
      </form>
      <form method="post" action="/test-read">
        <label for="query">Read-only test query</label>
        <input id="query" name="query" type="text" value="{DEFAULT_TEST_QUERY}" />
        <button type="submit">Test Gmail Read</button>
      </form>
      <h2>Latest setup</h2>
      <pre>{setup_summary or "{}"}</pre>
      <h2>Latest read test</h2>
      <pre>{read_summary or "No read test yet."}</pre>
    </div>
  </main>
</body>
</html>"""
    return body.encode("utf-8")


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    for token in ("refresh_token", "client_secret", "access_token"):
        text = text.replace(token, "[redacted]")
    return text


def _preview(text: object, limit: int = 160) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _print_human(payload: dict) -> None:
    print("AgentOS Gmail")
    print(f"schema: {payload.get('schema_version', '')}")
    print(f"status: {payload.get('summary', {}).get('state', 'ready' if payload.get('proof', {}).get('ok') else 'blocked')}")
    print(f"reason: {payload.get('proof', {}).get('reason', '')}")
    if payload.get("summary"):
        print("")
        print(json.dumps(payload["summary"], ensure_ascii=True, indent=2))
    if payload.get("summary") is None and payload.get("response"):
        print(payload["response"])


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS Gmail read-only OAuth setup/status/read surface")
    parser.add_argument("--mode", choices=["setup", "status", "read"], default="setup")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--credentials", default="")
    parser.add_argument("--credentials-path", default="")
    parser.add_argument("--token-path", default="")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--query", default=DEFAULT_TEST_QUERY)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--mock-response", default="")
    parser.add_argument("--serve-http", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--display-host", default="")
    parser.add_argument("--port", type=int, default=8789)
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--url-file", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("gmail payload: PASS" if result["ok"] else "gmail payload: FAIL"))
        return 0 if result["ok"] else 1

    if args.serve_http:
        serve_fn = serve_gmail_setup_page_background if args.background else serve_gmail_setup_page
        payload = serve_fn(
            args.workspace,
            host=args.host,
            display_host=args.display_host,
            port=args.port,
            timeout_sec=args.timeout_sec,
            url_file=args.url_file or None,
            credentials_path=args.credentials_path or None,
            token_path=args.token_path or None,
        )
    elif args.mode == "status":
        payload = build_gmail_status_report(
            args.workspace,
            credentials_path=args.credentials_path or None,
            token_path=args.token_path or None,
        )
    elif args.mode == "read":
        payload = build_gmail_read_report(
            args.workspace,
            query=args.query,
            max_results=args.max_results,
            credentials_path=args.credentials_path or None,
            token_path=args.token_path or None,
            mock_response=args.mock_response,
        )
    else:
        payload = build_gmail_setup_report(
            args.workspace,
            credentials=args.credentials,
            credentials_path=args.credentials_path or None,
            token_path=args.token_path or None,
            authorize=args.authorize,
        )

    if args.output:
        write_json_file(args.output, payload)
    if args.json or not args.output:
        if args.json:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            _print_human(payload)
    return 0 if payload.get("proof", {}).get("ok", payload.get("setup_page_started", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
