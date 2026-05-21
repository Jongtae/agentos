#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
for candidate in (SRC_DIR, SCRIPTS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from io_utils import scrub_payload
from kernel.capability_substrate import build_telegram_live_loop_report
from kernel.operator_activity import build_activity_feed_payload
from kernel_phase2_run import run_phase2
from kernel_phase2_setup_status import build_status


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(scrub_payload(payload), ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b""
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            value = json.loads(raw.decode("utf-8") or "{}")
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


class DockerPreviewApp:
    def __init__(self, *, workspace: Path, user_root: Path, telegram_polling: bool, telegram_interval: int) -> None:
        self.workspace = workspace
        self.user_root = user_root
        self.telegram_polling = telegram_polling
        self.telegram_interval = max(5, int(telegram_interval or 10))
        self._stop = threading.Event()
        self._telegram_thread: threading.Thread | None = None

    def start_background_workers(self) -> None:
        token = os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN", "").strip()
        chats = os.environ.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
        if not self.telegram_polling or not token or not chats:
            return
        self._telegram_thread = threading.Thread(target=self._telegram_loop, name="agentos-telegram-polling-preview", daemon=True)
        self._telegram_thread.start()

    def _telegram_loop(self) -> None:
        while not self._stop.is_set():
            try:
                build_telegram_live_loop_report(self.workspace, once=True, send_reply=True, write_manifest=True)
            except Exception:
                # Keep compose logs user-facing. Detailed state is visible via /activity and artifacts.
                pass
            self._stop.wait(self.telegram_interval)

    def status(self) -> dict:
        setup = build_status(str(self.workspace), str(self.user_root))
        activity = build_activity_feed_payload(self.workspace, limit=12)
        return {
            "schema_version": "agentos-docker-runtime-preview-status.v1",
            "docker_preview": True,
            "workspace": str(self.workspace),
            "user_data_root": str(self.user_root),
            "http_url": "http://localhost:8787",
            "runtime": setup,
            "telegram": {
                "transport": "polling_preview",
                "polling_worker_enabled": bool(self.telegram_polling),
                "token_configured": bool(os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN", "").strip()),
                "allowed_chat_configured": bool(os.environ.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip()),
                "webhook_configured": False,
            },
            "activity": activity,
            "proof": {
                "ok": True,
                "docker_preview_surface_ready": True,
                "boot_or_iso_proof": False,
                "secrets_redacted": True,
            },
        }

    def run_prompt(self, message: str) -> dict:
        message = str(message or "").strip()
        if not message:
            return {
                "ok": False,
                "failure_class": "empty_prompt",
                "response": "Enter a prompt first.",
            }
        result = run_phase2(workspace=self.workspace, user_root=self.user_root, prompt=message)
        return {
            "ok": bool(result.get("proof", {}).get("ok", False)),
            "intent": result.get("intent", ""),
            "capability": result.get("capability", ""),
            "status": result.get("status", ""),
            "response": result.get("response", ""),
            "record": result.get("record", {}),
            "artifacts": result.get("artifacts", {}),
            "activity": result.get("activity_feed", {}),
            "proof": result.get("proof", {}),
        }

    def telegram_check(self) -> dict:
        try:
            payload = build_telegram_live_loop_report(self.workspace, once=True, send_reply=True, write_manifest=True)
            return payload
        except Exception as exc:
            return {
                "schema_version": "agentos-docker-telegram-preview-error.v1",
                "proof": {"ok": False, "reason": "telegram_preview_failed"},
                "friendly_error": str(exc),
            }

    def activity(self) -> dict:
        return build_activity_feed_payload(self.workspace, limit=40)


def _render_page(app: DockerPreviewApp) -> str:
    status = scrub_payload(app.status())
    adapters = status.get("runtime", {}).get("adapters", {})
    activity = status.get("activity", {}).get("events", [])
    llm_state = adapters.get("llm", {}).get("state", "unknown")
    telegram = status.get("telegram", {})
    telegram_state = "ready" if telegram.get("token_configured") and telegram.get("allowed_chat_configured") else "setup needed"
    cards = [
        ("Runtime", status.get("runtime", {}).get("overall_state", "unknown")),
        ("LLM", llm_state),
        ("Telegram", f"{telegram_state} · polling preview"),
        ("Workspace", status.get("workspace", "")),
    ]
    activity_html = "\n".join(
        f"<li><b>{html.escape(str(event.get('label', 'AgentOS')))}</b> "
        f"<span>{html.escape(str(event.get('time', '')))}</span> "
        f"{html.escape(str(event.get('human_message', '')))}</li>"
        for event in activity[-12:]
    ) or "<li>No activity yet. Run a prompt below.</li>"
    card_html = "\n".join(
        f"<section class='card'><h3>{html.escape(title)}</h3><p>{html.escape(str(value))}</p></section>"
        for title, value in cards
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentOS Docker Preview</title>
  <style>
    :root {{ color-scheme: dark; --bg:#08110f; --panel:#101c18; --line:#29463b; --text:#effaf3; --muted:#a8b9ae; --accent:#79f29a; --warn:#f2d479; }}
    body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #173429, var(--bg)); color:var(--text); }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ font-size: clamp(2.2rem, 6vw, 5rem); line-height: .94; margin: 0 0 16px; letter-spacing: -0.06em; }}
    .tag {{ display:inline-block; color:#06200e; background:var(--accent); border-radius: 999px; padding: 8px 14px; font-weight: 800; margin-bottom: 18px; }}
    .lead {{ max-width: 780px; color: var(--muted); font-size: 1.15rem; line-height: 1.6; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 28px 0; }}
    .card, .panel {{ background: color-mix(in srgb, var(--panel) 88%, transparent); border: 1px solid var(--line); border-radius: 22px; padding: 20px; box-shadow: 0 20px 80px rgba(0,0,0,.25); }}
    .card h3 {{ margin:0 0 10px; color:var(--accent); }}
    .card p {{ margin:0; color:var(--muted); overflow-wrap:anywhere; }}
    textarea {{ width:100%; min-height: 92px; box-sizing:border-box; border-radius:18px; border:1px solid var(--line); background:#06100d; color:var(--text); padding:16px; font: inherit; }}
    button {{ border:0; border-radius: 999px; background:var(--accent); color:#041008; padding: 12px 18px; font-weight: 850; margin: 12px 8px 0 0; cursor:pointer; }}
    button.secondary {{ background:#20392f; color:var(--text); border: 1px solid var(--line); }}
    pre {{ white-space: pre-wrap; overflow-wrap:anywhere; background:#050b09; border:1px solid var(--line); border-radius:18px; padding:16px; color:#d8eadf; }}
    ul {{ list-style:none; padding:0; margin:0; }}
    li {{ border-bottom:1px solid #1d332b; padding:10px 0; color:#dce9e1; }}
    li span {{ color:var(--muted); margin: 0 8px; }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="tag">Docker runtime preview</div>
    <h1>AgentOS</h1>
    <p class="lead">Try the AgentOS runtime without booting an ISO. This preview routes prompts through the same local-first intent/capability path and writes proof logs under mounted user data.</p>
  </header>
  <div class="grid">{card_html}</div>
  <section class="panel">
    <h2>Run a prompt</h2>
    <textarea id="prompt">status</textarea>
    <br>
    <button onclick="runPrompt()">Run prompt</button>
    <button class="secondary" onclick="telegramCheck()">Manual Telegram check</button>
    <button class="secondary" onclick="refreshStatus()">Refresh</button>
    <pre id="result">Ready. Try: hi, status, workspace 파일 목록 보여줘, or search AgentOS roadmap and summarize it.</pre>
  </section>
  <section class="panel" style="margin-top:18px">
    <h2>Activity</h2>
    <ul id="activity">{activity_html}</ul>
    <p><a href="/api/status">status JSON</a> · <a href="/api/activity">activity JSON</a></p>
  </section>
</main>
<script>
async function postJSON(url, payload) {{
  const res = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload || {{}})}});
  return await res.json();
}}
function showResult(payload) {{
  const response = payload.response || payload.friendly_error || JSON.stringify(payload, null, 2);
  const meta = [payload.intent, payload.capability, payload.status].filter(Boolean).join(' · ');
  document.getElementById('result').textContent = (meta ? meta + '\\n\\n' : '') + response;
  refreshActivity();
}}
async function runPrompt() {{
  document.getElementById('result').textContent = 'Running prompt...';
  showResult(await postJSON('/api/prompt', {{message: document.getElementById('prompt').value}}));
}}
async function telegramCheck() {{
  document.getElementById('result').textContent = 'Running one Telegram polling preview check...';
  const payload = await postJSON('/api/telegram/check', {{}});
  showResult({{
    response: 'telegram_polling_attempted=' + payload.telegram_polling_attempted + '\\ntelegram_live_update_received=' + payload.telegram_live_update_received + '\\ntelegram_reply_sent=' + payload.telegram_reply_sent + '\\nreason=' + ((payload.proof || {{}}).reason || ''),
    intent: 'telegram_preview',
    capability: 'telegram_polling_check',
    status: (payload.proof || {{}}).ok ? 'completed' : 'degraded'
  }});
}}
async function refreshActivity() {{
  const payload = await (await fetch('/api/activity')).json();
  const rows = payload.events || [];
  document.getElementById('activity').innerHTML = rows.slice(-12).map(e => `<li><b>${{escapeHtml(e.label || 'AgentOS')}}</b> <span>${{escapeHtml(e.time || '')}}</span> ${{escapeHtml(e.human_message || '')}}</li>`).join('') || '<li>No activity yet.</li>';
}}
async function refreshStatus() {{
  const payload = await (await fetch('/api/status')).json();
  document.getElementById('result').textContent = JSON.stringify(payload.runtime?.adapters || payload, null, 2);
  refreshActivity();
}}
function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
setInterval(refreshActivity, 5000);
</script>
</body>
</html>"""


def make_handler(app: DockerPreviewApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentOSDockerPreview/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            if _env_bool("AGENTOS_DOCKER_ACCESS_LOG", False):
                super().log_message(fmt, *args)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/setup", "/activity"}:
                _html_response(self, _render_page(app))
            elif path == "/healthz":
                _json_response(self, {"ok": True, "service": "agentos-docker-preview"})
            elif path == "/api/status":
                _json_response(self, app.status())
            elif path == "/api/activity":
                _json_response(self, app.activity())
            else:
                _json_response(self, {"ok": False, "error": "not_found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = _read_body(self)
            if path == "/api/prompt":
                _json_response(self, app.run_prompt(str(body.get("message", ""))))
            elif path == "/api/telegram/check":
                _json_response(self, app.telegram_check())
            else:
                _json_response(self, {"ok": False, "error": "not_found"}, status=404)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the AgentOS Docker runtime preview")
    parser.add_argument("--host", default=os.environ.get("AGENTOS_DOCKER_PREVIEW_HOST", "0.0.0.0"))
    parser.add_argument("--port", default=os.environ.get("AGENTOS_DOCKER_PREVIEW_PORT", "8787"))
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--user-root", default=os.environ.get("AGENTOS_USER_DATA_ROOT", "./agentos-data/user"))
    parser.add_argument("--telegram-polling", action="store_true", default=_env_bool("AGENTOS_DOCKER_TELEGRAM_POLLING", True))
    parser.add_argument("--telegram-interval", default=os.environ.get("AGENTOS_DOCKER_TELEGRAM_INTERVAL", "10"))
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    user_root = Path(args.user_root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    user_root.mkdir(parents=True, exist_ok=True)

    app = DockerPreviewApp(
        workspace=workspace,
        user_root=user_root,
        telegram_polling=bool(args.telegram_polling),
        telegram_interval=int(args.telegram_interval),
    )
    app.start_background_workers()

    server = ThreadingHTTPServer((args.host, int(args.port)), make_handler(app))
    print(f"AgentOS Docker preview: http://localhost:{args.port}", flush=True)
    print("Docker preview only; this is not ISO/boot proof.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
