from __future__ import annotations

import json

from doctor import doctor_report
from io_utils import scrub_payload, write_json_file
from status import status_report


def _recommended_actions(setup_required: bool, doctor: dict, status: dict) -> list[str]:
    actions: list[str] = []

    if setup_required:
        actions.append("python src/main.py --setup-engine")

    reason = doctor.get("reason", "")
    if reason == "missing_api_key":
        actions.append("export OPENAI_API_KEY=<your_api_key>")
    elif reason == "binary_not_found":
        provider = (doctor.get("checked_provider") or "").strip().lower()
        if provider == "ollama":
            actions.append("Install Ollama and ensure `ollama` is available on PATH")
        else:
            actions.append("Install Codex CLI and ensure `codex` is available on PATH")
    elif reason == "model_not_found":
        actions.append("ollama pull <model_name>")
        actions.append("Set kernel_engine.ollama.model to an installed local model")
    elif reason == "timeout":
        provider = (doctor.get("checked_provider") or "").strip().lower()
        if provider == "ollama":
            actions.append("Increase kernel_engine.ollama.timeout_sec in spec.yaml")
        else:
            actions.append("Increase kernel_engine.codex.timeout_sec in spec.yaml")
    elif reason == "setup_required":
        actions.append("python src/main.py --set-engine ollama")

    status_reason = status.get("engine_reason", "")
    if status_reason == "invalid_provider":
        actions.append("python src/main.py --set-engine ollama")

    # Preserve order, remove duplicates.
    deduped: list[str] = []
    seen = set()
    for item in actions:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def preflight_report(wm) -> dict:
    doctor = doctor_report(wm)
    status = status_report(wm)
    setup_required = not bool((wm.kernel_engine_provider or "").strip())
    ready = bool(doctor.get("ok", False)) and bool(status.get("ok", False))
    actions = _recommended_actions(setup_required, doctor, status)

    return {
        "ready": ready,
        "exit_code": 0 if ready else 1,
        "workspace": str(wm.workspace_dir),
        "kernel_engine_provider": wm.kernel_engine_provider or "",
        "setup_required": setup_required,
        "actions": actions,
        "doctor": doctor,
        "status": status,
    }


def run_preflight(wm, as_json: bool = False, output_file: str = "") -> int:
    report = preflight_report(wm)
    if output_file:
        write_json_file(output_file, report)

    if as_json:
        print(json.dumps(scrub_payload(report), ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Preflight")
    print("=================")
    print(f"Workspace: {report['workspace']}")
    print(f"Kernel engine provider: {report['kernel_engine_provider'] or '(not selected)'}")
    print(f"Setup required: {'yes' if report['setup_required'] else 'no'}")
    print(f"Ready: {'PASS' if report['ready'] else 'FAIL'}")

    if not report["doctor"]["ok"]:
        print(f"Doctor reason: {report['doctor']['reason']}")
        if report["doctor"].get("detail"):
            print(f"Doctor detail: {report['doctor']['detail']}")
    if not report["status"]["ok"]:
        print(f"Status reason: {report['status']['engine_reason']}")
        if report["status"].get("engine_detail"):
            print(f"Status detail: {report['status']['engine_detail']}")

    if report["setup_required"]:
        print("Tip: run `python src/main.py --setup-engine` to persist provider selection.")
    if report["actions"]:
        print("Recommended actions:")
        for action in report["actions"]:
            print(f"- {action}")

    return int(report["exit_code"])
