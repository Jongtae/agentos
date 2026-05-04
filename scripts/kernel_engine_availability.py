#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload
from kernel.engine import CodexCliEngine, OllamaEngine, ensure_provider_ready
from workspace.manager import WorkspaceManager


SCHEMA_VERSION = "agentos-kernel-engine-availability.v1"
FIRST_PROMPT_INTENT = "Reply in five words: AgentOS ready."


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(json.dumps(payload, ensure_ascii=True) + "\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _prompt_probe(engine, *, retries: int = 3, delay_sec: int = 5):
    last = None
    for attempt in range(1, max(1, retries) + 1):
        last = engine.run_intent(FIRST_PROMPT_INTENT)
        if last.ok:
            return last, attempt
        if attempt < retries:
            time.sleep(max(0, delay_sec))
    return last, max(1, retries)


def build_report(wm: WorkspaceManager, *, allow_bootstrap: bool = True) -> dict:
    provider = wm.kernel_engine_provider or "ollama"
    bootstrap = ensure_provider_ready(wm, provider, allow_bootstrap=allow_bootstrap)

    first_prompt_ok = False
    first_prompt_content = ""
    first_prompt_error_type = ""
    first_prompt_error_message = ""
    first_prompt_attempts = 0
    if bootstrap.ok and provider == "ollama":
        engine = OllamaEngine(
            workspace_dir=wm.workspace_dir,
            command=wm.ollama_command,
            timeout_sec=wm.ollama_timeout_sec,
            model=wm.ollama_model,
        )
        run, first_prompt_attempts = _prompt_probe(engine)
        first_prompt_ok = bool(run.ok)
        first_prompt_content = run.content
        first_prompt_error_type = run.error_type
        first_prompt_error_message = run.error_message
    elif bootstrap.ok and provider == "codex":
        engine = CodexCliEngine(
            workspace_dir=wm.workspace_dir,
            command=wm.codex_command,
            timeout_sec=wm.codex_timeout_sec,
            model=wm.codex_model,
        )
        run, first_prompt_attempts = _prompt_probe(engine)
        first_prompt_ok = bool(run.ok)
        first_prompt_content = run.content
        first_prompt_error_type = run.error_type
        first_prompt_error_message = run.error_message

    managed_reentry_ready = bool(bootstrap.ok and first_prompt_ok)
    summary = {
        "provider": provider,
        "provider_ready": bool(bootstrap.ok),
        "bootstrap_attempted": bool(bootstrap.bootstrap_attempted),
        "first_prompt_success": first_prompt_ok,
        "managed_reentry_ready": managed_reentry_ready,
        "usable_runtime_entry": bool(bootstrap.ok and first_prompt_ok),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(wm.workspace_dir),
        "provider": provider,
        "selected_model": bootstrap.selected_model,
        "bootstrap_attempted": bootstrap.bootstrap_attempted,
        "bootstrap_performed": bootstrap.bootstrap_performed,
        "install_strategy": bootstrap.install_strategy,
        "reason": bootstrap.reason,
        "detail": bootstrap.detail,
        "first_prompt_success": first_prompt_ok,
        "first_prompt_attempts": first_prompt_attempts,
        "first_prompt_preview": first_prompt_content[:240],
        "first_prompt_error_type": first_prompt_error_type,
        "first_prompt_error_message": first_prompt_error_message,
        "managed_reentry_ready": managed_reentry_ready,
        "summary": summary,
        "artifacts": {
            "latest_kernel_engine_availability_json": str(
                wm.workspace_dir / "artifacts" / "kernel-engine" / "latest-kernel-engine-availability.json"
            )
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report kernel engine bootstrap and prompt readiness")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--no-bootstrap", action="store_true")
    args = parser.parse_args()

    wm = WorkspaceManager(args.workspace)
    payload = build_report(wm, allow_bootstrap=not args.no_bootstrap)
    out_path = Path(payload["artifacts"]["latest_kernel_engine_availability_json"])
    _atomic_write_json(out_path, payload)

    if args.output:
        _atomic_write_json(Path(args.output), payload)

    if args.json:
        print(json.dumps(scrub_payload(payload), ensure_ascii=True))
    else:
        print("AgentOS Kernel Engine Availability")
        print("================================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Provider: {payload['provider']}")
        print(f"Model: {payload['selected_model'] or '(n/a)'}")
        print(f"Bootstrap attempted: {'yes' if payload['bootstrap_attempted'] else 'no'}")
        print(f"Ready: {'PASS' if payload['summary']['provider_ready'] else 'FAIL'}")
        print(f"First prompt: {'PASS' if payload['first_prompt_success'] else 'FAIL'}")
        print(f"Managed re-entry ready: {'PASS' if payload['managed_reentry_ready'] else 'FAIL'}")
        print(f"Reason: {payload['reason']}")
        if payload["detail"]:
            print(f"Detail: {payload['detail']}")

    return 0 if payload["summary"]["usable_runtime_entry"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
