#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload
from kernel.engine import ensure_provider_ready
from workspace.manager import WorkspaceManager


SCHEMA_VERSION = "agentos-llm-setup.v1"
DEFAULT_CODEX_MODEL = "gpt-4o-mini"


def _default_env_file() -> Path:
    home = Path(os.environ.get("HOME") or "/home/ubuntu").expanduser()
    return home / ".config" / "agentos" / "env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = _read_env_file(path)
    existing.update({key: value for key, value in updates.items() if value})
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in sorted(existing.items())]
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write("\n".join(lines) + "\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    path.chmod(0o600)


def _selected_model(wm: WorkspaceManager, provider: str) -> str:
    if provider == "codex":
        return wm.codex_model or DEFAULT_CODEX_MODEL
    if provider == "ollama":
        return wm.ollama_model
    return ""


def _force_codex_model(wm: WorkspaceManager) -> None:
    kernel = wm.spec.setdefault("kernel_engine", {})
    codex = kernel.setdefault("codex", {})
    if codex.get("model") != DEFAULT_CODEX_MODEL:
        codex["model"] = DEFAULT_CODEX_MODEL
        wm.save_spec()


def _set_provider(wm: WorkspaceManager, provider: str) -> None:
    normalized = provider.strip().lower()
    if normalized == "guide":
        normalized = "none"
    if normalized == "codex":
        _force_codex_model(wm)
    wm.set_kernel_engine_provider(normalized)


def _build_status(workspace: str | Path, *, env_file: str | Path | None = None) -> dict:
    wm = WorkspaceManager(str(workspace))
    _force_codex_model(wm)
    env_path = Path(env_file).expanduser() if env_file else _default_env_file()
    env_values = _read_env_file(env_path)
    provider = wm.kernel_engine_provider or "ollama"
    openai_key_configured = bool(
        os.environ.get("OPENAI_API_KEY", "").strip()
        or env_values.get("OPENAI_API_KEY", "").strip()
    )
    readiness = None
    provider_ready = provider == "none"
    reason = ""
    detail = ""
    if provider == "codex":
        provider_ready = openai_key_configured
        if not openai_key_configured:
            reason = "openai_api_key_missing"
            detail = "OPENAI_API_KEY is required for the Codex/OpenAI path."
    elif provider != "none":
        try:
            readiness = ensure_provider_ready(wm, provider, allow_bootstrap=False)
            provider_ready = bool(readiness.ok)
            reason = readiness.reason
            detail = readiness.detail
        except Exception as exc:
            provider_ready = False
            reason = "provider_status_failed"
            detail = str(exc)
    model = _selected_model(wm, provider)
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(wm.workspace_dir),
        "provider": provider,
        "selected_model": model,
        "codex_model": DEFAULT_CODEX_MODEL,
        "openai_key_configured": openai_key_configured,
        "env_file": str(env_path),
        "provider_ready": provider_ready,
        "reason": reason,
        "detail": detail,
        "setup_page_url": "",
        "setup_page_started": False,
        "setup_page_background": False,
        "setup_page_already_running": False,
        "completed": provider_ready,
        "failure_class": "" if provider_ready else "provider_unavailable",
        "summary": {
            "llm_setup_ready": provider_ready,
            "provider": provider,
            "selected_model": model,
            "openai_key_configured": openai_key_configured,
            "secret_source": "runtime_env",
        },
    }


def _display_setup_url(host: str, display_host: str, port: int) -> str:
    url_host = (display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host)).strip()
    return f"http://{url_host}:{port}/setup"


def _port_accepts_connections(host: str, port: int) -> bool:
    import socket

    probe_host = "127.0.0.1" if host in {"", "0.0.0.0"} else host
    try:
        with socket.create_connection((probe_host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _render_setup_page(status: dict, message: str = "") -> bytes:
    provider = html.escape(str(status.get("provider", "")))
    model = html.escape(str(status.get("selected_model", "")))
    openai_ready = "yes" if status.get("openai_key_configured") else "no"
    msg = f"<p class='msg'>{html.escape(message)}</p>" if message else ""
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AgentOS LLM Setup</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px; background: #0b0f0c; color: #eef7ee; }}
    .card {{ border: 1px solid #2f6f3b; border-radius: 18px; padding: 24px; background: #101812; box-shadow: 0 20px 60px rgba(0,0,0,.35); }}
    h1 {{ margin-top: 0; color: #8cff9a; }}
    label {{ display:block; margin-top: 16px; color: #b9cdbb; }}
    input, select {{ width: 100%; box-sizing: border-box; padding: 12px; margin-top: 6px; border-radius: 10px; border: 1px solid #385840; background: #050705; color: #fff; }}
    button {{ margin-top: 18px; padding: 12px 16px; border: 0; border-radius: 999px; background: #34c759; color: #061006; font-weight: 700; }}
    .muted {{ color: #9baa9d; }}
    .msg {{ color: #8cff9a; font-weight: 700; }}
    code {{ color: #d7ff8c; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>AgentOS LLM Setup</h1>
    <p>Current provider: <code>{provider}</code></p>
    <p>Current model: <code>{model}</code></p>
    <p>OpenAI key configured: <code>{openai_ready}</code></p>
    {msg}
    <form method="post" action="/setup">
      <label>Provider</label>
      <select name="provider">
        <option value="ollama">Bundled local Ollama</option>
        <option value="codex">OpenAI/Codex (gpt-4o-mini)</option>
        <option value="none">Later / guide fallback</option>
      </select>
      <label>OpenAI API key (only for OpenAI/Codex)</label>
      <input name="openai_api_key" type="password" autocomplete="off" placeholder="sk-...">
      <p class="muted">Secrets are saved only to <code>$HOME/.config/agentos/env</code> in the VM and are redacted from artifacts.</p>
      <button type="submit">Save LLM setup</button>
    </form>
  </div>
</body>
</html>"""
    return body.encode("utf-8")


def serve_llm_setup_page(
    workspace: str | Path,
    *,
    env_file: str | Path | None = None,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8788,
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
) -> dict:
    state: dict[str, object] = {"completed": False, "payload": _build_status(workspace, env_file=env_file)}
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
            self._send(200, _render_setup_page(dict(state["payload"])))

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/setup":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
            provider = form.get("provider", ["ollama"])[0].strip().lower()
            api_key = form.get("openai_api_key", [""])[0].strip()
            wm = WorkspaceManager(str(workspace))
            try:
                _set_provider(wm, provider)
                if api_key:
                    _write_env_file(Path(env_file).expanduser() if env_file else _default_env_file(), {"OPENAI_API_KEY": api_key})
                payload = _build_status(workspace, env_file=env_file)
                payload["completed"] = True
                payload["failure_class"] = ""
                state["payload"] = payload
                state["completed"] = True
                done.set()
                self._send(200, _render_setup_page(payload, "LLM setup saved. Return to AgentOS and run /status."))
            except Exception as exc:
                payload = _build_status(workspace, env_file=env_file)
                payload["completed"] = False
                payload["failure_class"] = "llm_setup_failed"
                payload["detail"] = str(exc)
                state["payload"] = payload
                self._send(200, _render_setup_page(payload, f"Setup failed: {exc}"))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    actual_port = int(server.server_address[1])
    setup_url = _display_setup_url(host, display_host, actual_port)
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
    payload = dict(state["payload"])
    payload.update(
        {
            "setup_page_started": True,
            "setup_page_url": setup_url,
            "setup_page_bound_host": host,
            "setup_page_display_host": display_host or ("127.0.0.1" if host in {"", "0.0.0.0"} else host),
            "setup_page_bound_port": actual_port,
            "completed": bool(state["completed"]),
        }
    )
    if not payload["completed"] and not payload.get("failure_class"):
        payload["failure_class"] = "llm_setup_page_timeout"
    return payload


def serve_llm_setup_page_background(
    workspace: str | Path,
    *,
    env_file: str | Path | None = None,
    host: str = "0.0.0.0",
    display_host: str = "",
    port: int = 8788,
    timeout_sec: int = 600,
    url_file: str | Path | None = None,
) -> dict:
    workspace_path = Path(workspace).expanduser()
    artifacts = workspace_path / "artifacts" / "llm-setup"
    artifacts.mkdir(parents=True, exist_ok=True)
    setup_url = _display_setup_url(host, display_host, port)
    url_path = Path(url_file).expanduser() if url_file else artifacts / "setup-page-url.txt"
    log_path = artifacts / "setup-page-server.log"
    pid_path = artifacts / "setup-page-server.pid"
    if _port_accepts_connections(host, port):
        url_path.write_text(setup_url + "\n", encoding="utf-8")
        payload = _build_status(workspace_path, env_file=env_file)
        payload.update(
            {
                "setup_page_started": True,
                "setup_page_background": True,
                "setup_page_already_running": True,
                "setup_page_url": setup_url,
                "operator_action_required": "open_setup_page",
                "log_path": str(log_path),
                "pid_path": str(pid_path),
            }
        )
        return payload

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
        if url_path.exists() or _port_accepts_connections(host, port):
            url_path.write_text(setup_url + "\n", encoding="utf-8")
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    payload = _build_status(workspace_path, env_file=env_file)
    payload.update(
        {
            "setup_page_started": proc.poll() is None,
            "setup_page_background": True,
            "setup_page_already_running": False,
            "setup_page_url": setup_url if proc.poll() is None else "",
            "operator_action_required": "open_setup_page" if proc.poll() is None else "check_log",
            "log_path": str(log_path),
            "pid_path": str(pid_path),
        }
    )
    if proc.poll() is not None:
        payload["failure_class"] = "llm_setup_page_start_failed"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS LLM setup surface")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--set-provider", default="")
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--serve-http", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--display-host", default="")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--url-file", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser() if args.env_file else _default_env_file()
    if args.serve_http and args.background:
        payload = serve_llm_setup_page_background(
            args.workspace,
            env_file=env_file,
            host=args.host,
            display_host=args.display_host,
            port=args.port,
            timeout_sec=args.timeout_sec,
            url_file=args.url_file or None,
        )
    elif args.serve_http:
        payload = serve_llm_setup_page(
            args.workspace,
            env_file=env_file,
            host=args.host,
            display_host=args.display_host,
            port=args.port,
            timeout_sec=args.timeout_sec,
            url_file=args.url_file or None,
        )
    else:
        wm = WorkspaceManager(args.workspace)
        if args.set_provider:
            _set_provider(wm, args.set_provider)
        if args.openai_api_key:
            _write_env_file(env_file, {"OPENAI_API_KEY": args.openai_api_key})
        payload = _build_status(args.workspace, env_file=env_file)

    scrubbed = scrub_payload(payload)
    if args.json:
        print(json.dumps(scrubbed, ensure_ascii=True))
    else:
        print("AgentOS LLM Setup")
        print(f"Provider: {scrubbed.get('provider')}")
        print(f"Model: {scrubbed.get('selected_model')}")
        print(f"Ready: {'yes' if scrubbed.get('provider_ready') else 'no'}")
        if scrubbed.get("setup_page_url"):
            print(f"Setup page: {scrubbed['setup_page_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
