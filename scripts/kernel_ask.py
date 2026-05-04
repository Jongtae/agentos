#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload, write_json_file
from kernel.engine import ensure_provider_ready
from main import _apply_default_network_policy_env, _build_engine_router, _maybe_wrap_agent_runner, build_runtime
from workspace.manager import WorkspaceManager


SCHEMA_VERSION = "agentos-ask-response.v1"


def build_payload(workspace_dir: str | Path, message: str) -> dict:
    workspace = Path(workspace_dir).resolve()
    wm = WorkspaceManager(workspace)
    _apply_default_network_policy_env(wm)
    provider = str(wm.kernel_engine_provider or "ollama").strip() or "ollama"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "capability": "ask",
        "ok": False,
        "message": message,
        "response": "",
        "provider": provider,
        "model": "",
        "workspace": str(workspace),
        "failure_class": "",
    }
    if not message.strip():
        payload["failure_class"] = "empty_message"
        return payload

    if provider != "none":
        readiness = ensure_provider_ready(wm, provider)
        if not readiness.ok:
            payload["failure_class"] = readiness.reason or "provider_unavailable"
            return payload

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            engine = _build_engine_router(wm).get_engine(provider)
            payload["model"] = str(getattr(engine, "model", "") or "")
            runtime, _memory, wm = build_runtime(wm, planner_backend=engine)
            runtime = _maybe_wrap_agent_runner(runtime, wm)
            result = runtime.run(message)
    except Exception as exc:  # keep the operator bridge truthful, not pretty.
        payload["failure_class"] = "runtime_ask_failure"
        payload["response"] = str(exc)
        return payload

    payload["ok"] = True
    payload["response"] = str(result)
    return payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("capability") != "ask":
        errors.append("capability must be ask")
    for key in ("ok",):
        if not isinstance(payload.get(key), bool):
            errors.append(f"{key} must be a boolean")
    for key in ("message", "response", "provider", "workspace", "failure_class"):
        if not isinstance(payload.get(key), str):
            errors.append(f"{key} must be a string")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one AgentOS ask request and emit JSON")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("ask: PASS" if result["ok"] else "ask: FAIL"))
        return 0 if result["ok"] else 1

    payload = build_payload(args.workspace, args.message)
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", SCHEMA_VERSION)}, ensure_ascii=True))
        return 1
    scrubbed = scrub_payload(payload)
    if args.output:
        write_json_file(args.output, scrubbed)
    if args.json or not args.output:
        print(json.dumps(scrubbed, ensure_ascii=True))
    return 0 if scrubbed.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
