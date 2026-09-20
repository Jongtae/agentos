#!/usr/bin/env python3
"""Exercise the installed CLI in foreground using disposable owner data.

This check intentionally does not install or mutate a launchd service. Actual
Homebrew/launchd observation is an owner operating-validation gate.
"""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
from http.client import RemoteDisconnected
import json
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import build_opener, HTTPCookieProcessor, Request


def installed_check(executable: str = "agentos") -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        client = build_opener(HTTPCookieProcessor(CookieJar()))

        def request(path: str, body: dict[str, object] | None = None) -> dict[str, object]:
            encoded = None if body is None else json.dumps(body).encode()
            query = Request(url + path, data=encoded, headers={"Content-Type": "application/json"})
            with client.open(query, timeout=3) as response:
                return json.load(response)

        def start() -> subprocess.Popen[bytes]:
            process = subprocess.Popen(
                [executable, "start", "--no-browser", "--host", "127.0.0.1", "--data", tmp, "--port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(100):
                try:
                    if request("/healthz")["ok"]:
                        return process
                except (OSError, URLError, RemoteDisconnected):
                    pass
                time.sleep(0.1)
            process.terminate()
            process.wait(timeout=10)
            raise RuntimeError("The foreground server did not become healthy; run `agentos start` to inspect the error.")

        process = start()
        try:
            request("/api/claim", {"code": (Path(tmp) / "private/bootstrap").read_text(), "password": secrets.token_urlsafe(24)})
            request("/api/chat", {"message": "/note Installed Homebrew verification", "request_key": "installed-proof"})
            state: dict[str, object] = {}
            for _ in range(50):
                state = request("/api/state")
                if state.get("notes"):
                    break
                time.sleep(0.1)
            assert state["notes"][0]["content"] == "Installed Homebrew verification"  # type: ignore[index]
            second = subprocess.run(
                [executable, "start", "--no-browser", "--host", "127.0.0.1", "--data", tmp, "--port", str(port + 1)],
                capture_output=True,
                timeout=10,
                check=False,
            )
            assert second.returncode == 1
            process.terminate()
            process.wait(timeout=10)
            process = start()
            assert request("/api/state")["notes"][0]["content"] == "Installed Homebrew verification"  # type: ignore[index]
            return {
                "installed_cli": True,
                "foreground_start": True,
                "loopback_host": "127.0.0.1",
                "http_setup": True,
                "authenticated_note": True,
                "restart_persistence": True,
                "single_instance": True,
                "background_service": "owner_validation_pending",
                "service_mutated": False,
                "evidence": "installed_foreground_smoke",
                "limitations": "No live Homebrew install or launchd lifecycle was performed by this check.",
            }
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default="agentos")
    args = parser.parse_args(argv)
    try:
        result = installed_check(args.executable)
    except (AssertionError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {
            "installed_cli": False,
            "background_service": "owner_validation_pending",
            "service_mutated": False,
            "error": str(exc),
            "next_action": "Run the installed `agentos start` command in a terminal to inspect the foreground startup failure.",
        }
        print(json.dumps(result))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
