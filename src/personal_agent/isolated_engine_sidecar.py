"""HTTP worker that runs Codex in an empty per-request working directory."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


MAX_REQUEST_BYTES = 65_536
MAX_OUTPUT_BYTES = 1_048_576
MAX_PROMPT_BYTES = 48_000


class SidecarError(ValueError):
    """Safe failure at the isolated engine process boundary."""


def _decode_object(raw: bytes) -> dict:
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise SidecarError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SidecarError("invalid JSON request") from exc
    if not isinstance(value, dict):
        raise SidecarError("JSON object required")
    return value


class IsolatedEngineSidecar:
    """Execute the sole supported subscription engine with one MCP bridge."""

    def __init__(self, callback_url: str, *, codex_binary: str = "codex", timeout: float = 120.0):
        if not isinstance(callback_url, str) or not callback_url:
            raise ValueError("callback_url is required")
        if not isinstance(codex_binary, str) or not codex_binary:
            raise ValueError("codex_binary is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.callback_url = callback_url
        self.codex_binary = codex_binary
        self.timeout = timeout

    @staticmethod
    def _validate(payload: dict) -> tuple[str, str, str]:
        if set(payload) != {"prompt", "engine_id", "token", "task_id"}:
            raise SidecarError("invalid execution request")
        if payload["engine_id"] != "codex":
            raise SidecarError("unsupported engine")
        prompt, token, task_id = payload["prompt"], payload["token"], payload["task_id"]
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES
            or not isinstance(token, str)
            or not token
            or not isinstance(task_id, str)
            or not task_id
        ):
            raise SidecarError("invalid execution request")
        return prompt, token, task_id

    @staticmethod
    def _result(stdout: str) -> str:
        if len(stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise SidecarError("engine output exceeded limit")
        try:
            records = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise SidecarError("engine returned invalid JSON") from exc
        for record in reversed(records):
            if not isinstance(record, dict):
                continue
            item = record.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    return text[:24_000]
            text = record.get("content") or record.get("output")
            if isinstance(text, str) and text.strip():
                return text[:24_000]
        raise SidecarError("engine returned no final result")

    def execute(self, payload: dict) -> str:
        prompt, token, task_id = self._validate(payload)
        with tempfile.TemporaryDirectory(prefix="agentos-isolated-") as folder:
            root = Path(folder)
            cwd = root / "work"
            cwd.mkdir(mode=0o700)
            config = root / "agentos-mcp.json"
            bridge_args = [
                "-m",
                "personal_agent.isolated_engine_mcp_bridge",
                "--callback",
                self.callback_url,
                f"--token={token}",
                "--task-id",
                task_id,
            ]
            config.write_text(
                json.dumps(
                    {"mcpServers": {"agentos": {"command": sys.executable, "args": bridge_args}}},
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            bridge = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["agentos"]
            command = [
                self.codex_binary,
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-c",
                "mcp_servers.agentos.command=" + json.dumps(bridge["command"]),
                "-c",
                "mcp_servers.agentos.args=" + json.dumps(bridge["args"]),
                prompt,
            ]
            environment = os.environ.copy()
            package_root = str(Path(__file__).resolve().parents[1])
            prior_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                package_root + os.pathsep + prior_pythonpath if prior_pythonpath else package_root
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    shell=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SidecarError("engine execution failed") from exc
            if completed.returncode != 0:
                diagnostic = " ".join((completed.stderr or "").split()).lower()
                if "--token" in diagnostic and "expected one argument" in diagnostic:
                    reason = "MCP bridge argument parsing failed"
                elif "usage:" in diagnostic or "error:" in diagnostic:
                    reason = "engine command-line invocation failed"
                else:
                    reason = f"engine process exited with status {completed.returncode}"
                raise SidecarError(f"engine execution failed: {reason}")
            return self._result(completed.stdout)


def make_handler(sidecar: IsolatedEngineSidecar):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, value: dict) -> None:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if self.path != "/execute":
                return self._reply(404, {"error": "not found"})
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                return self._reply(415, {"error": "JSON request required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise SidecarError("invalid request size")
                payload = _decode_object(self.rfile.read(length))
                result = sidecar.execute(payload)
            except SidecarError as exc:
                return self._reply(400, {"error": str(exc)})
            return self._reply(200, {"result": result})

        def log_message(self, *_args):
            pass

    return Handler


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--callback", default=os.environ.get("AGENTOS_INTERNAL_MCP_URL"))
    parser.add_argument("--codex-binary", default=os.environ.get("AGENTOS_CODEX_BINARY", "codex"))
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    if not args.callback:
        parser.error("--callback or AGENTOS_INTERNAL_MCP_URL is required")
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(IsolatedEngineSidecar(args.callback, codex_binary=args.codex_binary, timeout=args.timeout)),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
