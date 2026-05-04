from __future__ import annotations

import json

from io_utils import scrub_payload, scrub_sensitive_text, write_json_file
from kernel.engine import (
    CodexCliEngine,
    ClaudeEngineStub,
    EngineRouter,
    GeminiEngineStub,
    OllamaEngine,
    SetupGuideEngine,
)


def doctor_report(wm) -> dict:
    router = EngineRouter(
        mode=wm.kernel_engine_mode,
        engines={
            "codex": CodexCliEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.codex_command,
                timeout_sec=wm.codex_timeout_sec,
                model=wm.codex_model,
            ),
            "ollama": OllamaEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.ollama_command,
                timeout_sec=wm.ollama_timeout_sec,
                model=wm.ollama_model,
            ),
            "none": SetupGuideEngine(),
            "claude": ClaudeEngineStub(),
            "gemini": GeminiEngineStub(),
        },
    )

    provider = wm.kernel_engine_provider or "ollama"

    try:
        engine = router.get_engine(provider)
    except ValueError as e:
        return {
            "ok": False,
            "exit_code": 2,
            "workspace": str(wm.workspace_dir),
            "kernel_engine_mode": wm.kernel_engine_mode,
            "kernel_engine_provider": wm.kernel_engine_provider or "",
            "checked_provider": provider,
            "reason": "invalid_provider",
            "detail": scrub_sensitive_text(str(e)),
        }

    health = engine.health_check()
    return {
        "ok": bool(health.ok),
        "exit_code": 0 if health.ok else 1,
        "workspace": str(wm.workspace_dir),
        "kernel_engine_mode": wm.kernel_engine_mode,
        "kernel_engine_provider": wm.kernel_engine_provider or "",
        "checked_provider": provider,
        "reason": health.reason,
        "detail": health.detail,
    }


def run_doctor(wm, as_json: bool = False, output_file: str = "") -> int:
    """Run environment checks and print diagnostics. Returns process exit code."""
    report = doctor_report(wm)
    if output_file:
        write_json_file(output_file, report)
    if as_json:
        print(json.dumps(scrub_payload(report), ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Doctor")
    print("=============")
    print(f"Workspace: {report['workspace']}")
    print(f"Kernel engine mode: {report['kernel_engine_mode']}")
    print(f"Kernel engine provider: {report['kernel_engine_provider'] or '(not selected)'}")
    print(f"Checking provider: {report['checked_provider']}")

    if report["ok"]:
        print("[PASS] Engine health check")
        print(f"Reason: {report['reason']}")
        if report["detail"]:
            print(f"Detail: {report['detail']}")
        return 0

    if report["reason"] == "invalid_provider":
        print(f"[FAIL] Invalid provider: {report['detail']}")
        return 2

    print("[FAIL] Engine health check")
    print(f"Reason: {report['reason']}")
    if report["detail"]:
        print(f"Detail: {report['detail']}")
    return 1
