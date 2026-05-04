#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload, write_json_file
from status import status_report
from workspace.manager import WorkspaceManager


SCHEMA_VERSION = "agentos-guided-operator-surface.v1"
TASK_VOCABULARY_VERSION = "agentos-task-centric-runtime.v1"
STATE_SUMMARY_VERSION = "agentos-state-summary.v1"
BASELINE_TOP_TASK_IDS = [
    "ask",
    "open_document",
    "fetch_web",
    "review_inbox",
    "export_proof",
    "recover_rejoin",
]
BASELINE_TOP_TASK_LABELS = [
    "Ask",
    "Open Document",
    "Fetch Web",
    "Review Inbox",
    "Export Proof",
    "Recover / Rejoin",
]
BASELINE_TOP_TASK_KINDS = ["ask", "document", "web", "inbox", "proof", "recovery"]
TELEGRAM_TOP_TASK_IDS = ["ask_from_telegram", "search_and_reply", "review_telegram_ingress"]
TELEGRAM_TOP_TASK_LABELS = [
    "Ask from Telegram",
    "Search and Reply",
    "Review Telegram ingress status",
]
TELEGRAM_TOP_TASK_KINDS = ["telegram_ask", "telegram_search_reply", "telegram_ingress_status"]


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _resolve_telegram_ingress_summary(report: dict) -> dict:
    explicit_report = report.get("telegram_ingress", {})
    if not isinstance(explicit_report, dict):
        explicit_report = {}
    summary = explicit_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    polling_summary = summary.get("polling", {})
    if not isinstance(polling_summary, dict):
        polling_summary = {}
    bot_token_summary = summary.get("bot_token", {})
    if not isinstance(bot_token_summary, dict):
        bot_token_summary = {}

    inbox_summary = report.get("inbox_capability", {}).get("summary", {})
    if not isinstance(inbox_summary, dict):
        inbox_summary = {}

    ingress_ready = _coerce_bool(
        summary.get("ingress_ready", summary.get("ready", summary.get("telegram_ready", False)))
    )
    if not summary and not ingress_ready:
        ingress_ready = _coerce_bool(inbox_summary.get("inbox_execution_ready", False))

    polling_enabled = _coerce_bool(
        summary.get(
            "polling_enabled",
            summary.get(
                "telegram_polling_enabled",
                polling_summary.get("enabled", polling_summary.get("polling_enabled", False)),
            ),
        )
    )
    if not summary and not polling_enabled:
        polling_enabled = _coerce_bool(inbox_summary.get("inbox_adapter_required", False))

    bot_token_configured = _coerce_bool(
        summary.get(
            "bot_token_configured",
            summary.get(
                "telegram_bot_token_configured",
                bot_token_summary.get("configured", False),
            ),
        )
    )
    poll_interval_sec = _coerce_int(
        summary.get(
            "poll_interval_sec",
            summary.get(
                "polling_interval_sec",
                polling_summary.get("interval_sec", 0),
            ),
        )
    )
    messages_visible = _coerce_int(summary.get("messages_visible", inbox_summary.get("message_count", 0)))
    threads_visible = _coerce_int(summary.get("threads_visible", inbox_summary.get("thread_count", 0)))

    return {
        "ingress_ready": ingress_ready,
        "polling_enabled": polling_enabled,
        "bot_token_configured": bot_token_configured,
        "poll_interval_sec": poll_interval_sec,
        "messages_visible": messages_visible,
        "threads_visible": threads_visible,
        "source_reported": bool(explicit_report),
        "visibility_label": str(
            summary.get("visibility_label", "telegram ingress")
        ).strip() or "telegram ingress",
    }


def _workspace_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _runtime_entry_mode(report: dict) -> str:
    origin = str(report.get("session_origin", {}).get("category", "")).strip()
    if origin in {
        "live_appliance_boot",
        "installed_appliance_boot",
        "local_managed_tty1",
        "local_tty_unmanaged",
        "root_tty_recovery",
    }:
        return "tty"
    if origin == "ssh":
        return "ssh"
    return "noninteractive"


def _task(
    label: str,
    *,
    task_id: str,
    task_kind: str,
    ready: bool,
    command: str,
    command_argv: list[str],
    command_input: dict,
    execution_mode: str,
    surface: str,
    handoff: dict,
) -> dict:
    blocking_reasons: list[str] = []
    if not ready:
        blocking_reasons.append(f"{task_kind}_not_ready")
    return {
        "id": task_id,
        "task_kind": task_kind,
        "label": label,
        "ready": bool(ready),
        "status": "ready" if ready else "blocked",
        "command_hint": command,
        "command_argv": command_argv,
        "command_input": command_input,
        "execution_mode": execution_mode,
        "blocking_reasons": blocking_reasons,
        "surface": surface,
        "handoff": handoff,
    }


def build_payload(wm: WorkspaceManager) -> dict:
    report = status_report(wm)
    workspace = Path(str(report["workspace"]))
    documents_dir = workspace / "documents"
    default_document = documents_dir / "agentos-first-run.md"
    workspace_writable = _workspace_writable(workspace)
    provider = str(report.get("kernel_engine_provider") or report.get("checked_provider") or "ollama")
    model = str(report.get("engine_model") or "").strip()
    provider_ready = str(report.get("engine_status", "")).upper() == "PASS"
    document_ready = bool("file" in report.get("tools_enabled", []) and default_document.exists())
    web_ready = bool("web" in report.get("tools_enabled", []))
    inbox_summary = report.get("inbox_capability", {}).get("summary", {})
    inbox_ready = bool(inbox_summary.get("inbox_execution_ready", False))
    telegram_ingress = _resolve_telegram_ingress_summary(report)
    proof_export_ready = bool(workspace_writable and provider_ready)
    telegram_ask_ready = provider_ready and workspace_writable and telegram_ingress["ingress_ready"]
    telegram_search_reply_ready = telegram_ask_ready
    telegram_ingress_status_ready = provider_ready and workspace_writable
    recovery_path = report.get("recovery_path", {})
    recovery_affordance_visible = bool(
        recovery_path.get("label") and recovery_path.get("recommended_rejoin_path")
    )
    recovery_entry_points = list(recovery_path.get("entry_points", []))
    recovery_rejoin_summary = list(recovery_path.get("recommended_rejoin_summary", []))
    recovery_rejoin_path = list(recovery_path.get("recommended_rejoin_path", []))
    recovery_label = str(recovery_path.get("label", "AgentOS Recovery"))
    recovery_runtime_target = str(recovery_path.get("runtime_rejoin_target", ""))
    recovery_rejoin_target = str(recovery_path.get("rejoin_target", ""))
    recovery_description = str(
        recovery_path.get(
            "description",
            "Use AgentOS Recovery when you need a safe shell, then return to AgentOS and continue to the managed session.",
        )
    )
    runtime_entry_mode = _runtime_entry_mode(report)

    if not workspace_writable:
        operator_state = "workspace_blocked"
        default_next_action = "Repair workspace ownership and retry managed entry."
    elif not provider_ready:
        operator_state = "provider_unavailable"
        default_next_action = "Inspect engine availability and restore the bundled local provider."
    elif not proof_export_ready:
        operator_state = "proof_export_unavailable"
        default_next_action = "Repair proof export readiness before running handoff or signoff."
    else:
        operator_state = "runtime_ready"
        default_next_action = "Ask a question or start a top task from the guided operator surface."

    state_summary = {
        "schema_version": STATE_SUMMARY_VERSION,
        "operator_visible_state": operator_state,
        "default_next_action": default_next_action,
        "runtime_entry_mode": runtime_entry_mode,
        "session_origin": report.get("session_origin", {}).get("category", ""),
        "next_managed_entry": report.get("setup_state", {}).get("next_managed_entry", ""),
        "provider_model_ready": provider_ready,
        "workspace_writable": workspace_writable,
        "document_ready": document_ready,
        "web_ready": web_ready,
        "inbox_ready": inbox_ready,
        "proof_export_ready": proof_export_ready,
        "recovery_path_available": recovery_affordance_visible,
        "telegram_ingress_ready": telegram_ingress["ingress_ready"],
        "telegram_messages_visible": telegram_ingress["messages_visible"],
        "telegram_threads_visible": telegram_ingress["threads_visible"],
        "telegram_polling_enabled": telegram_ingress["polling_enabled"],
        "telegram_bot_token_configured": telegram_ingress["bot_token_configured"],
        "telegram_poll_interval_sec": telegram_ingress["poll_interval_sec"],
        "telegram_ingress_visibility_label": telegram_ingress["visibility_label"],
    }

    workspace_str = str(workspace)
    top_tasks = [
        _task(
            "Ask",
            task_id="ask",
            task_kind="ask",
            ready=provider_ready,
            command=f"agentos-shell --workspace {workspace_str} --managed-runtime",
            command_argv=["agentos-shell", "--workspace", workspace_str, "--managed-runtime"],
            command_input={"required": ["prompt"], "optional": []},
            execution_mode="managed_interactive",
            surface="managed_session",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "managed_session",
                "launch_mode": "managed_interactive",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "codex_cli_managed_session",
            },
        ),
        _task(
            "Open Document",
            task_id="open_document",
            task_kind="document",
            ready=document_ready,
            command=(
                f"agentos-kernelctl document-access --workspace {workspace_str} "
                "--path documents/agentos-first-run.md --json"
            ),
            command_argv=[
                "agentos-kernelctl",
                "document-access",
                "--workspace",
                workspace_str,
                "--path",
                "documents/agentos-first-run.md",
                "--json",
            ],
            command_input={"required": ["path"], "optional": []},
            execution_mode="tool_call",
            surface="document_access",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "document_access",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "",
            },
        ),
        _task(
            "Fetch Web",
            task_id="fetch_web",
            task_kind="web",
            ready=web_ready,
            command=(
                f"agentos-kernelctl web-access --workspace {workspace_str} "
                "--url https://example.com --json"
            ),
            command_argv=[
                "agentos-kernelctl",
                "web-access",
                "--workspace",
                workspace_str,
                "--url",
                "https://example.com",
                "--json",
            ],
            command_input={"required": ["url"], "optional": ["allow_domain"]},
            execution_mode="tool_call",
            surface="web_access",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "web_access",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "",
            },
        ),
        _task(
            "Review Inbox",
            task_id="review_inbox",
            task_kind="inbox",
            ready=inbox_ready,
            command=f"agentos-kernelctl inbox-workflow --workspace {workspace_str} --json",
            command_argv=[
                "agentos-kernelctl",
                "inbox-workflow",
                "--workspace",
                workspace_str,
                "--json",
            ],
            command_input={"required": [], "optional": ["maildir", "session_id"]},
            execution_mode="tool_call",
            surface="inbox_workflow",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "inbox_workflow",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "",
            },
        ),
        _task(
            "Export Proof",
            task_id="export_proof",
            task_kind="proof",
            ready=proof_export_ready,
            command=f"agentos-kernelctl vm-e2e-proof --workspace {workspace_str} --json",
            command_argv=[
                "agentos-kernelctl",
                "vm-e2e-proof",
                "--workspace",
                workspace_str,
                "--json",
            ],
            command_input={"required": [], "optional": ["session_id", "output"]},
            execution_mode="tool_call",
            surface="proof_export",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "proof_export",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "",
            },
        ),
        _task(
            "Recover / Rejoin",
            task_id="recover_rejoin",
            task_kind="recovery",
            ready=recovery_affordance_visible,
            command="agentos-kernelctl runtime-entry --json",
            command_argv=["agentos-kernelctl", "runtime-entry", "--json"],
            command_input={"required": [], "optional": []},
            execution_mode="tool_call",
            surface="recovery_path",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "recovery_path",
                "launch_mode": "tool_call",
                "continuity": "rejoin_path",
                "workspace_path": workspace_str,
                "managed_runtime_target": "codex_cli_managed_session",
            },
        ),
        _task(
            "Ask from Telegram",
            task_id="ask_from_telegram",
            task_kind="telegram_ask",
            ready=telegram_ask_ready,
            command=f"agentos-shell --workspace {workspace_str} --managed-runtime --telegram-ask",
            command_argv=[
                "agentos-shell",
                "--workspace",
                workspace_str,
                "--managed-runtime",
                "--telegram-ask",
            ],
            command_input={"required": [], "optional": []},
            execution_mode="managed_interactive",
            surface="telegram_ask",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "telegram_ask",
                "launch_mode": "managed_interactive",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "codex_cli_managed_session",
            },
        ),
        _task(
            "Search and Reply",
            task_id="search_and_reply",
            task_kind="telegram_search_reply",
            ready=telegram_search_reply_ready,
            command=(
                f"agentos-kernelctl research-workflow --workspace {workspace_str} "
                "--message-text 'search agentos roadmap' --chat-id 1001 --json"
            ),
            command_argv=[
                "agentos-kernelctl",
                "research-workflow",
                "--workspace",
                workspace_str,
                "--message-text",
                "search agentos roadmap",
                "--chat-id",
                "1001",
                "--json",
            ],
            command_input={"required": ["message_text", "chat_id"], "optional": ["request_id", "message_id", "allow_domain"]},
            execution_mode="tool_call",
            surface="research_workflow",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "research_workflow",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "",
            },
        ),
        _task(
            "Review Telegram ingress status",
            task_id="review_telegram_ingress",
            task_kind="telegram_ingress_status",
            ready=telegram_ingress_status_ready,
            command=(
                f"agentos-shell --workspace {workspace_str} "
                "--managed-runtime --telegram-ingress-status"
            ),
            command_argv=[
                "agentos-shell",
                "--workspace",
                workspace_str,
                "--managed-runtime",
                "--telegram-ingress-status",
            ],
            command_input={"required": [], "optional": []},
            execution_mode="tool_call",
            surface="telegram_ingress_status",
            handoff={
                "entry_surface": "guided_operator",
                "target_surface": "telegram_ingress_status",
                "launch_mode": "tool_call",
                "continuity": "same_workspace",
                "workspace_path": workspace_str,
                "managed_runtime_target": "codex_cli_managed_session",
            },
        ),
    ]

    priority_actions = list(
        report.get("user_space_sovereignty", {}).get("summary", {}).get("priority_actions", [])
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "guided_operator_surface_reachable": True,
        "runtime_entry_mode": runtime_entry_mode,
        "workspace_writable": workspace_writable,
        "recovery_affordance_visible": recovery_affordance_visible,
        "state": operator_state,
        "default_next_action": default_next_action,
        "task_vocabulary_version": TASK_VOCABULARY_VERSION,
        "state_summary_version": STATE_SUMMARY_VERSION,
        "runtime_summary": {
            "provider": provider,
            "model": model,
            "runtime_ready": provider_ready and workspace_writable,
            "provider_ready": provider_ready,
            "workspace_path": workspace_str,
            "workspace_writable": workspace_writable,
            "document_ready": document_ready,
            "web_ready": web_ready,
            "inbox_ready": inbox_ready,
            "proof_export_ready": proof_export_ready,
            "telegram_ingress_ready": telegram_ingress["ingress_ready"],
            "telegram_messages_visible": telegram_ingress["messages_visible"],
            "telegram_threads_visible": telegram_ingress["threads_visible"],
            "telegram_polling_enabled": telegram_ingress["polling_enabled"],
            "telegram_bot_token_configured": telegram_ingress["bot_token_configured"],
            "telegram_poll_interval_sec": telegram_ingress["poll_interval_sec"],
            "telegram_ingress_visibility_label": telegram_ingress["visibility_label"],
        },
        "state_summary": state_summary,
        "task_readiness_hint": {
            "workspace_writable": workspace_writable,
            "provider_ready": provider_ready,
            "document_ready": document_ready,
            "web_ready": web_ready,
            "inbox_ready": inbox_ready,
            "proof_export_ready": proof_export_ready,
            "recovery_affordance_visible": recovery_affordance_visible,
            "telegram_ingress_ready": telegram_ingress["ingress_ready"],
            "telegram_messages_visible": telegram_ingress["messages_visible"],
            "telegram_threads_visible": telegram_ingress["threads_visible"],
            "telegram_polling_enabled": telegram_ingress["polling_enabled"],
            "telegram_bot_token_configured": telegram_ingress["bot_token_configured"],
            "telegram_poll_interval_sec": telegram_ingress["poll_interval_sec"],
        },
        "top_tasks": top_tasks,
        "task_vocabulary": {
            "baseline_labels": BASELINE_TOP_TASK_LABELS,
            "baseline_task_kinds": BASELINE_TOP_TASK_KINDS,
            "telegram_labels": TELEGRAM_TOP_TASK_LABELS,
            "telegram_task_kinds": TELEGRAM_TOP_TASK_KINDS,
            "telegram_task_ids": TELEGRAM_TOP_TASK_IDS,
            "execution_modes": [item["execution_mode"] for item in top_tasks],
            "task_count": len(top_tasks),
        },
        "recovery_affordance": {
            "visible": recovery_affordance_visible,
            "label": recovery_label,
            "description": recovery_description,
            "rejoin_summary": recovery_rejoin_summary,
            "rejoin_path": recovery_rejoin_path,
            "rejoin_target": recovery_rejoin_target,
            "default_shell_target": recovery_path.get("default_shell_target", ""),
            "runtime_rejoin_target": recovery_runtime_target,
            "entry_points": recovery_entry_points,
            "default_action_label": "Return to AgentOS",
            "default_action_command": "agentos-kernelctl runtime-entry --json",
            "degraded_preview_label": "Degraded preview mode",
            "workspace_repair_guidance": "Use a writable interactive workspace before running guided tasks.",
        },
        "operator_context": {
            "current_mode": report.get("operator_mode", {}).get("current_mode", ""),
            "recommended_surface": report.get("operator_mode", {}).get("recommended_surface", ""),
            "session_origin": report.get("session_origin", {}).get("category", ""),
            "next_managed_entry": report.get("setup_state", {}).get("next_managed_entry", ""),
            "priority_actions": priority_actions,
        },
        "source_status": {
            "engine_status": report.get("engine_status", ""),
            "engine_reason": report.get("engine_reason", ""),
            "setup_status": report.get("setup_state", {}).get("status", ""),
        },
    }
    return payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "guided_operator_surface_reachable",
        "runtime_entry_mode",
        "workspace_writable",
        "recovery_affordance_visible",
        "state",
        "default_next_action",
        "task_vocabulary_version",
        "state_summary_version",
        "runtime_summary",
        "state_summary",
        "task_readiness_hint",
        "top_tasks",
        "task_vocabulary",
        "recovery_affordance",
        "operator_context",
        "source_status",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("runtime_entry_mode") not in {"tty", "ssh", "noninteractive"}:
        errors.append("runtime_entry_mode must be tty/ssh/noninteractive")
    if payload.get("task_vocabulary_version") != TASK_VOCABULARY_VERSION:
        errors.append(f"task_vocabulary_version must be {TASK_VOCABULARY_VERSION}")
    if payload.get("state_summary_version") != STATE_SUMMARY_VERSION:
        errors.append(f"state_summary_version must be {STATE_SUMMARY_VERSION}")
    if payload.get("state") not in {
        "runtime_ready",
        "runtime_degraded",
        "workspace_blocked",
        "provider_unavailable",
        "proof_export_unavailable",
    }:
        errors.append("state must be a supported guided operator state")
    top_tasks = payload.get("top_tasks")
    if not isinstance(top_tasks, list) or len(top_tasks) != 9:
        errors.append("top_tasks must contain the nine guided operator task entries")
    if isinstance(top_tasks, list):
        expected_labels = BASELINE_TOP_TASK_LABELS + TELEGRAM_TOP_TASK_LABELS
        expected_task_kinds = BASELINE_TOP_TASK_KINDS + TELEGRAM_TOP_TASK_KINDS
        expected_task_ids = BASELINE_TOP_TASK_IDS + TELEGRAM_TOP_TASK_IDS
        expected_surfaces = [
            "managed_session",
            "document_access",
            "web_access",
            "inbox_workflow",
            "proof_export",
            "recovery_path",
            "telegram_ask",
            "research_workflow",
            "telegram_ingress_status",
        ]
        labels = [str(item.get("label", "")) for item in top_tasks]
        if labels != expected_labels:
            errors.append("top_tasks labels must match the guided operator task vocabulary")
        kinds = [str(item.get("task_kind", "")) for item in top_tasks]
        if kinds != expected_task_kinds:
            errors.append("top_tasks task kinds must match the guided operator runtime vocabulary")
        ids = [str(item.get("id", "")) for item in top_tasks]
        if ids != expected_task_ids:
            errors.append("top_tasks ids must match the guided operator vocabulary")
        surfaces = [str(item.get("surface", "")) for item in top_tasks]
        if surfaces != expected_surfaces:
            errors.append("top_tasks surfaces must match the guided operator surface vocabulary")
    runtime_summary = payload.get("runtime_summary")
    if not isinstance(runtime_summary, dict):
        errors.append("runtime_summary must be an object")
    state_summary = payload.get("state_summary")
    if not isinstance(state_summary, dict):
        errors.append("state_summary must be an object")
    else:
        if state_summary.get("schema_version") != STATE_SUMMARY_VERSION:
            errors.append(f"state_summary.schema_version must be {STATE_SUMMARY_VERSION}")
        if state_summary.get("operator_visible_state") != payload.get("state"):
            errors.append("state_summary.operator_visible_state must match state")
    task_readiness_hint = payload.get("task_readiness_hint")
    if not isinstance(task_readiness_hint, dict):
        errors.append("task_readiness_hint must be an object")
    task_vocabulary = payload.get("task_vocabulary")
    if not isinstance(task_vocabulary, dict):
        errors.append("task_vocabulary must be an object")
    else:
        if task_vocabulary.get("baseline_task_kinds") != BASELINE_TOP_TASK_KINDS:
            errors.append("task_vocabulary.baseline_task_kinds must match baseline runtime vocabulary")
        if task_vocabulary.get("telegram_task_kinds") != TELEGRAM_TOP_TASK_KINDS:
            errors.append("task_vocabulary.telegram_task_kinds must match telegram task vocabulary")
        if task_vocabulary.get("telegram_task_ids") != TELEGRAM_TOP_TASK_IDS:
            errors.append("task_vocabulary.telegram_task_ids must match telegram task identifiers")
        if task_vocabulary.get("execution_modes") != [item["execution_mode"] for item in top_tasks]:
            errors.append("task_vocabulary.execution_modes must match top task execution modes")
        if task_vocabulary.get("task_count") != len(top_tasks):
            errors.append("task_vocabulary.task_count must match top task count")
    recovery_affordance = payload.get("recovery_affordance")
    if not isinstance(recovery_affordance, dict):
        errors.append("recovery_affordance must be an object")
    else:
        if not isinstance(recovery_affordance.get("entry_points", []), list):
            errors.append("recovery_affordance.entry_points must be a list")
        if not isinstance(recovery_affordance.get("description", ""), str):
            errors.append("recovery_affordance.description must be a string")
    return errors


def _print_text(payload: dict) -> None:
    runtime = payload["runtime_summary"]
    recovery = payload["recovery_affordance"]
    print("AgentOS Guided Operator")
    print("=======================")
    print(f"State: {payload['state']}")
    print(
        "Runtime summary: "
        f"provider={runtime['provider']}, "
        f"model={runtime['model'] or '(default)'}, "
        f"ready={runtime['runtime_ready']}, "
        f"workspace={runtime['workspace_path']}, "
        f"workspace_writable={runtime['workspace_writable']}, "
        f"document_ready={runtime['document_ready']}, "
        f"web_ready={runtime['web_ready']}, "
        f"inbox_ready={runtime['inbox_ready']}, "
        f"proof_export_ready={runtime['proof_export_ready']}, "
        f"telegram_ingress_ready={runtime['telegram_ingress_ready']}, "
        f"telegram_messages_visible={runtime['telegram_messages_visible']}, "
        f"telegram_threads_visible={runtime['telegram_threads_visible']}, "
        f"telegram_polling_enabled={runtime['telegram_polling_enabled']}, "
        f"telegram_bot_token_configured={runtime['telegram_bot_token_configured']}, "
        f"telegram_poll_interval_sec={runtime['telegram_poll_interval_sec']}"
    )
    print(
        "State summary: "
        f"state={payload['state_summary']['operator_visible_state']}, "
        f"provider_model_ready={payload['state_summary']['provider_model_ready']}, "
        f"workspace_writable={payload['state_summary']['workspace_writable']}, "
        f"document_ready={payload['state_summary']['document_ready']}, "
        f"web_ready={payload['state_summary']['web_ready']}, "
        f"inbox_ready={payload['state_summary']['inbox_ready']}, "
        f"proof_export_ready={payload['state_summary']['proof_export_ready']}, "
        f"telegram_ingress_ready={payload['state_summary']['telegram_ingress_ready']}, "
        f"telegram_messages_visible={payload['state_summary']['telegram_messages_visible']}, "
        f"telegram_threads_visible={payload['state_summary']['telegram_threads_visible']}, "
        f"telegram_polling_enabled={payload['state_summary']['telegram_polling_enabled']}, "
        f"telegram_bot_token_configured={payload['state_summary']['telegram_bot_token_configured']}, "
        f"telegram_poll_interval_sec={payload['state_summary']['telegram_poll_interval_sec']}, "
        f"telegram_ingress_visibility_label={payload['state_summary']['telegram_ingress_visibility_label']}, "
        f"recovery_path_available={payload['state_summary']['recovery_path_available']}"
    )
    print("Top tasks:")
    for item in payload["top_tasks"]:
        print(f"- {item['label']}: {item['status']} ({item['command_hint']})")
    print(
        "Recovery affordance: "
        f"{recovery['label']} -> {' -> '.join(recovery['rejoin_path']) if recovery['rejoin_path'] else 'n/a'}"
    )
    if recovery.get("description"):
        print(f"Recovery guidance: {recovery['description']}")
    if recovery.get("rejoin_target"):
        print(
            "Recovery rejoin target: "
            f"{recovery['rejoin_target']} -> {recovery.get('runtime_rejoin_target', '') or 'codex_cli_managed_session'}"
        )
    print(f"Next action: {payload['default_next_action']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the guided operator surface contract")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("guided operator contract: PASS" if result["ok"] else "guided operator contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    if not args.workspace:
        if args.json:
            print(json.dumps({"ok": False, "errors": ["--workspace is required unless --validate is used"]}, ensure_ascii=True))
        else:
            print("--workspace is required unless --validate is used")
        return 2

    wm = WorkspaceManager(args.workspace)
    payload = build_payload(wm)
    errors = validate_payload(payload)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        else:
            for error in errors:
                print(error)
        return 1

    if args.output:
        write_json_file(args.output, payload)
    if args.json:
        print(json.dumps(scrub_payload(payload), ensure_ascii=True))
    else:
        _print_text(scrub_payload(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
