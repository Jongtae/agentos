#!/usr/bin/env python3
"""
utm_client.py — unified UTM control client for AgentOS scripts.

PROBLEM
-------
utmctl uses XPC/Apple Events → fails with OSStatus -1743 in non-GUI sessions
(Codex subprocess, SSH, launchd Background agents).

SOLUTION: three-tier fallback
  1. UTM built-in REST API  (UTM 4.x Settings → Server → Enable)
  2. AgentOS utm-proxy       (scripts/utm_proxy_server.py launchd agent)
  3. utmctl direct           (works only in GUI session — kept as last resort)

Usage as library
----------------
    from utm_client import UTMClient, UTMError

    client = UTMClient()          # auto-discovers backend
    vms = client.list_vms()       # → ["AgentOS Preview", "Ubuntu 24.04"]
    client.start("AgentOS Preview")
    ip = client.ip("AgentOS Preview")

Usage as CLI
------------
    python3 scripts/utm_client.py list
    python3 scripts/utm_client.py start  "AgentOS Preview"
    python3 scripts/utm_client.py stop   "AgentOS Preview"
    python3 scripts/utm_client.py status "AgentOS Preview"
    python3 scripts/utm_client.py ip     "AgentOS Preview"
    python3 scripts/utm_client.py --backend proxy list
    python3 scripts/utm_client.py --json status "AgentOS Preview"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from urllib.error import URLError
from urllib.request import Request, urlopen

# ── ports / env ───────────────────────────────────────────────────────────────

# UTM built-in REST API — enable via UTM → Preferences → Server
UTM_API_PORT  = int(os.environ.get("AGENTOS_UTM_API_PORT",  "34722"))
# AgentOS utm-proxy launchd agent
PROXY_PORT    = int(os.environ.get("AGENTOS_UTM_PROXY_PORT", "49201"))

BACKEND_ORDER = ["utm_api", "proxy", "utmctl"]


class UTMError(RuntimeError):
    pass


# ── helper: check VM running from text ───────────────────────────────────────

def _vm_is_running(text: str) -> bool:
    low = text.lower()
    if any(t in low for t in ("not running", "stopped", "shutdown", "powered off")):
        return False
    return bool(
        re.search(r"(?:state|status)\s*:\s*(started|running|suspended)", text, re.I)
        or re.search(r"^\s*(started|running|suspended)\s*$", text, re.I | re.M)
    )


def _strip_event_noise(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("error from event:"):
            continue
        if low.startswith("note:"):
            continue
        lines.append(line)
    return "\n".join(lines)


# ── HTTP helper (no requests dependency) ─────────────────────────────────────

def _http(method: str, url: str, timeout: int = 10) -> dict:
    req = Request(url, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        raise UTMError(f"HTTP {method} {url}: {e}") from e
    except TimeoutError as e:
        raise UTMError(f"HTTP {method} {url}: timed out") from e
    except json.JSONDecodeError as e:
        raise UTMError(f"Invalid JSON from {url}: {e}") from e


# ── Backend implementations ───────────────────────────────────────────────────

class _UTMApiBackend:
    """
    UTM 4.x built-in REST API.
    Enable: UTM → Preferences → Server → Enable Server (default port 34722).
    """
    name = "utm_api"

    def __init__(self, port: int = UTM_API_PORT):
        self._base = f"http://127.0.0.1:{port}"

    def is_available(self) -> bool:
        try:
            _http("GET", f"{self._base}/api/v1/vms", timeout=2)
            return True
        except UTMError:
            return False

    def list_vms(self) -> list[str]:
        data = _http("GET", f"{self._base}/api/v1/vms")
        vms = data.get("data") or data.get("vms") or []
        return [v.get("name", str(v)) if isinstance(v, dict) else str(v) for v in vms]

    def start(self, name: str) -> None:
        # UTM API uses vm ID; we look it up by name first
        vm_id = self._resolve_id(name)
        _http("POST", f"{self._base}/api/v1/vms/{vm_id}/start")

    def stop(self, name: str) -> None:
        vm_id = self._resolve_id(name)
        _http("POST", f"{self._base}/api/v1/vms/{vm_id}/stop")

    def status(self, name: str) -> bool:
        vm_id = self._resolve_id(name)
        data = _http("GET", f"{self._base}/api/v1/vms/{vm_id}")
        state = (data.get("data") or data).get("status", "").lower()
        return state in ("started", "running", "suspended")

    def ip(self, name: str) -> list[str]:
        vm_id = self._resolve_id(name)
        data = _http("GET", f"{self._base}/api/v1/vms/{vm_id}/ips")
        ips = (data.get("data") or data).get("ips") or []
        return ips

    def _resolve_id(self, name: str) -> str:
        data = _http("GET", f"{self._base}/api/v1/vms")
        vms = data.get("data") or data.get("vms") or []
        for v in vms:
            if isinstance(v, dict) and v.get("name") == name:
                return str(v.get("id") or v.get("uuid") or name)
        return name  # fall through with name if no ID found


class _ProxyBackend:
    """
    AgentOS utm-proxy launchd agent (utm_proxy_server.py).
    Runs in GUI session, proxies utmctl over HTTP.
    Install: python3 scripts/utm_proxy_server.py --install
    """
    name = "proxy"

    def __init__(self, port: int = PROXY_PORT):
        self._base = f"http://127.0.0.1:{port}"

    def is_available(self) -> bool:
        try:
            data = _http("GET", f"{self._base}/health", timeout=2)
            return bool(data.get("ok"))
        except UTMError:
            return False

    def list_vms(self) -> list[str]:
        data = _http("GET", f"{self._base}/vms")
        return data.get("vms", [])

    def start(self, name: str) -> None:
        from urllib.parse import quote
        data = _http("POST", f"{self._base}/vms/{quote(name, safe='')}/start")
        if not data.get("ok"):
            raise UTMError(f"start failed: {data.get('error', data)}")

    def stop(self, name: str) -> None:
        from urllib.parse import quote
        data = _http("POST", f"{self._base}/vms/{quote(name, safe='')}/stop")
        if not data.get("ok"):
            raise UTMError(f"stop failed: {data.get('error', data)}")

    def status(self, name: str) -> bool:
        from urllib.parse import quote
        data = _http("GET", f"{self._base}/vms/{quote(name, safe='')}/status")
        return bool(data.get("running"))

    def ip(self, name: str) -> list[str]:
        from urllib.parse import quote
        data = _http("GET", f"{self._base}/vms/{quote(name, safe='')}/ip")
        return data.get("ips", [])


class _UtmctlBackend:
    """Direct utmctl — works only in GUI session.

    utmctl quirk: when Apple Events are blocked (-1743), it may still exit 0
    but emit "Error from event: ... (OSStatus error -1743.)" on stdout.
    We check both stdout+stderr for the error signature.
    """
    name = "utmctl"

    def __init__(self):
        bundled = Path("/Applications/UTM.app/Contents/MacOS/utmctl")
        if bundled.is_file():
            self._exe = str(bundled)
        else:
            self._exe = shutil.which("utmctl") or "utmctl"

    def _run(self, *args: str) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                [self._exe, *args],
                capture_output=True, text=True, check=False, timeout=30,
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except subprocess.TimeoutExpired as exc:
            raise UTMError(f"utmctl {' '.join(args)} timed out after 30 seconds") from exc

    @staticmethod
    def _is_blocked(out: str, err: str) -> bool:
        """Return True when the -1743 Apple Events block is present."""
        return "-1743" in out or "-1743" in err

    def is_available(self) -> bool:
        rc, out, err = self._run("list")
        if self._is_blocked(out, err):
            return False
        return rc == 0

    def list_vms(self) -> list[str]:
        rc, out, err = self._run("list")
        if self._is_blocked(out, err):
            raise UTMError(
                "utmctl blocked (OSStatus -1743): not in a GUI session.\n"
                "Fix A: UTM → Preferences → Server → Enable Server\n"
                "Fix B: python3 scripts/utm_proxy_server.py --install\n"
                "       launchctl load ~/Library/LaunchAgents/com.agentos.utm-proxy.plist"
            )
        if rc != 0:
            raise UTMError(f"utmctl list failed: {err or out}")
        # Filter out any residual error lines and the header line
        skip = {"uuid", "status", "name"}
        return [
            l for l in (l.strip() for l in out.splitlines())
            if l and not l.lower().startswith(tuple(skip))
            and "error from event" not in l.lower()
            and "note:" not in l.lower()
        ]

    def start(self, name: str) -> None:
        rc, out, err = self._run("start", "--hide", name)
        if self._is_blocked(out, err) or rc != 0:
            raise UTMError(f"utmctl start failed: {err or out}")

    def stop(self, name: str) -> None:
        rc, out, err = self._run("stop", "--hide", name)
        if self._is_blocked(out, err) or rc != 0:
            raise UTMError(f"utmctl stop failed: {err or out}")

    def status(self, name: str) -> bool:
        rc, out, err = self._run("status", "--hide", name)
        if self._is_blocked(out, err) or rc != 0:
            raise UTMError(f"utmctl status failed: {err or out}")
        return _vm_is_running(_strip_event_noise(out))

    def ip(self, name: str) -> list[str]:
        rc, out, err = self._run("ip-address", "--hide", name)
        if self._is_blocked(out, err) or rc != 0:
            raise UTMError(f"utmctl ip-address failed: {err or out}")
        cleaned = _strip_event_noise(out)
        return [l.strip() for l in cleaned.splitlines() if l.strip()]


# ── Client ────────────────────────────────────────────────────────────────────

_ALL_BACKENDS = {
    "utm_api": lambda: _UTMApiBackend(),
    "proxy":   lambda: _ProxyBackend(),
    "utmctl":  lambda: _UtmctlBackend(),
}


class UTMClient:
    """
    Auto-discovering UTM client.

    Priority: utm_api → proxy → utmctl
    Force a backend with backend="proxy" etc.
    """

    def __init__(self, backend: str | None = None):
        self._backend = self._pick(backend)

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def _pick(self, prefer: str | None):
        order = [prefer] if prefer else BACKEND_ORDER
        for name in order:
            factory = _ALL_BACKENDS.get(name)
            if not factory:
                raise UTMError(f"Unknown backend: {name}")
            b = factory()
            if b.is_available():
                return b
        raise UTMError(
            "No UTM backend available.\n"
            "Solutions:\n"
            "  1. Enable UTM REST API: UTM → Preferences → Server → Enable Server\n"
            "  2. Install utm-proxy:   python3 scripts/utm_proxy_server.py --install\n"
            "                          launchctl load ~/Library/LaunchAgents/com.agentos.utm-proxy.plist\n"
            "  3. Run from a GUI session where utmctl has permission."
        )

    def list_vms(self) -> list[str]:
        return self._backend.list_vms()

    def start(self, name: str) -> None:
        return self._backend.start(name)

    def stop(self, name: str) -> None:
        return self._backend.stop(name)

    def status(self, name: str) -> bool:
        """Returns True if VM is running or suspended."""
        return self._backend.status(name)

    def ip(self, name: str) -> list[str]:
        """Returns list of IP addresses for a running VM."""
        return self._backend.ip(name)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS UTM control client")
    parser.add_argument("--backend", choices=list(_ALL_BACKENDS), help="Force a specific backend")
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List VMs")
    sub.add_parser("backends", help="Show available backends")

    for op in ("start", "stop", "status", "ip"):
        p = sub.add_parser(op, help=f"{op.capitalize()} a VM")
        p.add_argument("vm_name")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 2

    if args.cmd == "backends":
        results = {}
        for name, factory in _ALL_BACKENDS.items():
            try:
                avail = factory().is_available()
            except Exception as e:
                avail = False
            results[name] = avail
        if args.as_json:
            print(json.dumps(results))
        else:
            for name, avail in results.items():
                print(f"  {'✓' if avail else '✗'} {name}")
        return 0

    try:
        client = UTMClient(backend=args.backend)
    except UTMError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    try:
        if args.cmd == "list":
            vms = client.list_vms()
            if args.as_json:
                print(json.dumps({"vms": vms, "backend": client.backend_name}))
            else:
                print(f"Backend: {client.backend_name}")
                for v in vms:
                    print(f"  {v}")

        elif args.cmd == "start":
            client.start(args.vm_name)
            result = {"ok": True, "vm": args.vm_name, "backend": client.backend_name}
            if args.as_json:
                print(json.dumps(result))
            else:
                print(f"Started: {args.vm_name}  (via {client.backend_name})")

        elif args.cmd == "stop":
            client.stop(args.vm_name)
            result = {"ok": True, "vm": args.vm_name, "backend": client.backend_name}
            if args.as_json:
                print(json.dumps(result))
            else:
                print(f"Stopped: {args.vm_name}  (via {client.backend_name})")

        elif args.cmd == "status":
            running = client.status(args.vm_name)
            state = "running" if running else "stopped"
            if args.as_json:
                print(json.dumps({"vm": args.vm_name, "running": running, "state": state, "backend": client.backend_name}))
            else:
                print(f"{args.vm_name}: {state}  (via {client.backend_name})")

        elif args.cmd == "ip":
            ips = client.ip(args.vm_name)
            if args.as_json:
                print(json.dumps({"vm": args.vm_name, "ips": ips, "ip": ips[0] if ips else "", "backend": client.backend_name}))
            else:
                if ips:
                    for ip in ips:
                        print(ip)
                else:
                    print("(no IP — is the VM running?)")

    except UTMError as e:
        if args.as_json:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"[error] {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
