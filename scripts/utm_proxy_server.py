#!/usr/bin/env python3
"""
utm_proxy_server.py — launchd user agent that proxies utmctl calls.

WHY THIS EXISTS
---------------
utmctl uses XPC/Apple Events, which macOS blocks outside a GUI session
(errAEEventNotPermitted, OSStatus -1743).  Codex and other subprocess
callers run without a GUI session, so utmctl fails for them.

This server runs as a launchd *user agent* (LaunchAgents), which means it
starts inside the user's GUI session and therefore has permission to call
utmctl.  Codex communicates with it over a plain HTTP socket on localhost.

INSTALL (one-time, run as your user — NOT sudo)
------------------------------------------------
    python3 scripts/utm_proxy_server.py --install
    launchctl load ~/Library/LaunchAgents/com.agentos.utm-proxy.plist

UNINSTALL
---------
    launchctl unload ~/Library/LaunchAgents/com.agentos.utm-proxy.plist
    python3 scripts/utm_proxy_server.py --uninstall

API
---
    GET  /health            → {"ok": true, "utmctl": "<path>"}
    GET  /vms               → {"vms": [...lines...], "raw": "..."}
    POST /vms/{name}/start  → {"ok": true|false, "output": "..."}
    POST /vms/{name}/stop   → {"ok": true|false, "output": "..."}
    GET  /vms/{name}/status → {"running": true|false, "output": "..."}
    GET  /vms/{name}/ip     → {"ip": "1.2.3.4", "ips": [...], "output": "..."}
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import unquote

# ── constants ─────────────────────────────────────────────────────────────────

DEFAULT_PORT = 49201          # high port, unlikely to conflict
PLIST_LABEL  = "com.agentos.utm-proxy"
PLIST_PATH   = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_DIR      = Path.home() / "Library" / "Logs" / "AgentOS"
SCRIPT_PATH  = Path(__file__).resolve()


# ── utmctl helpers ────────────────────────────────────────────────────────────

def _utmctl() -> str:
    return shutil.which("utmctl") or "utmctl"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _vm_is_running(text: str) -> bool:
    low = text.lower()
    if any(t in low for t in ("not running", "stopped", "shutdown", "powered off")):
        return False
    return bool(
        re.search(r"(?:state|status)\s*:\s*(running|suspended)", text, re.I)
        or re.search(r"^\s*(running|suspended)\s*$", text, re.I | re.M)
    )


# ── request handler ───────────────────────────────────────────────────────────

class _Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # quiet by default
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(self.path).rstrip("/")

        if path == "/health":
            utmctl = _utmctl()
            rc, out, err = _run([utmctl, "list"])
            self._send_json(200, {
                "ok": rc == 0,
                "utmctl": utmctl,
                "utmctl_ok": rc == 0,
                "error": err if rc != 0 else "",
            })
            return

        if path == "/vms":
            rc, out, err = _run([_utmctl(), "list"])
            if rc != 0:
                self._send_json(500, {"error": err or out})
                return
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            self._send_json(200, {"vms": lines, "raw": out})
            return

        # /vms/{name}/status
        m = re.match(r"^/vms/(.+)/status$", path)
        if m:
            name = m.group(1)
            rc, out, err = _run([_utmctl(), "status", "--hide", name])
            if rc != 0:
                self._send_json(500, {"error": err or out})
                return
            self._send_json(200, {"running": _vm_is_running(out), "output": out})
            return

        # /vms/{name}/ip
        m = re.match(r"^/vms/(.+)/ip$", path)
        if m:
            name = m.group(1)
            rc, out, err = _run([_utmctl(), "ip-address", "--hide", name])
            if rc != 0:
                self._send_json(500, {"error": err or out})
                return
            ips = [l.strip() for l in out.splitlines() if l.strip()]
            self._send_json(200, {"ip": ips[0] if ips else "", "ips": ips, "output": out})
            return

        self._send_json(404, {"error": f"not found: {path}"})

    def do_POST(self):
        path = unquote(self.path).rstrip("/")

        # /vms/{name}/start
        m = re.match(r"^/vms/(.+)/start$", path)
        if m:
            name = m.group(1)
            rc, out, err = _run([_utmctl(), "start", "--hide", name])
            ok = rc == 0
            self._send_json(200 if ok else 500, {"ok": ok, "output": out, "error": err if not ok else ""})
            return

        # /vms/{name}/stop
        m = re.match(r"^/vms/(.+)/stop$", path)
        if m:
            name = m.group(1)
            rc, out, err = _run([_utmctl(), "stop", "--hide", name])
            ok = rc == 0
            self._send_json(200 if ok else 500, {"ok": ok, "output": out, "error": err if not ok else ""})
            return

        self._send_json(404, {"error": f"not found: {path}"})


# ── plist install / uninstall ─────────────────────────────────────────────────

def _plist_content(port: int) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_LABEL}</string>
            <key>ProgramArguments</key>
            <array>
                <string>{sys.executable}</string>
                <string>{SCRIPT_PATH}</string>
                <string>--serve</string>
                <string>--port</string>
                <string>{port}</string>
            </array>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <true/>
            <key>StandardOutPath</key>
            <string>{LOG_DIR}/utm-proxy.log</string>
            <key>StandardErrorPath</key>
            <string>{LOG_DIR}/utm-proxy.err</string>
            <key>EnvironmentVariables</key>
            <dict>
                <key>PATH</key>
                <string>/usr/local/bin:/usr/bin:/bin:/Applications/UTM.app/Contents/MacOS</string>
            </dict>
        </dict>
        </plist>
    """)


def cmd_install(port: int) -> int:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist_content(port), encoding="utf-8")
    print(f"Installed: {PLIST_PATH}")
    print(f"Load with:   launchctl load {PLIST_PATH}")
    print(f"Proxy URL:   http://localhost:{port}")
    return 0


def cmd_uninstall() -> int:
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
        print(f"Removed: {PLIST_PATH}")
    else:
        print(f"Not found: {PLIST_PATH}")
    return 0


# ── server ────────────────────────────────────────────────────────────────────

def cmd_serve(port: int) -> int:
    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    print(f"utm-proxy listening on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="UTM utmctl proxy server for non-GUI contexts")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serve",     action="store_true", help="Start the proxy server")
    group.add_argument("--install",   action="store_true", help="Install launchd user agent plist")
    group.add_argument("--uninstall", action="store_true", help="Remove launchd user agent plist")
    args = parser.parse_args()

    if args.install:
        return cmd_install(args.port)
    if args.uninstall:
        return cmd_uninstall()
    return cmd_serve(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
