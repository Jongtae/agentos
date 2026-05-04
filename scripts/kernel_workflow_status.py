#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from io_utils import write_json_file
from kernel.capability_substrate import build_built_in_workflow_contract
from kernel.capability_substrate import build_telegram_status_report
from kernel_guided_operator import build_payload as build_guided_operator_payload
from workspace.manager import WorkspaceManager


SCHEMA_VERSION = "agentos-workflow-status.v1"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _artifact(workspace: Path, relative: str) -> dict:
    return _read_json(workspace / relative)


def _task_by_id(guided: dict) -> dict[str, dict]:
    tasks = guided.get("top_tasks", [])
    if not isinstance(tasks, list):
        return {}
    return {str(task.get("id", "")): task for task in tasks if isinstance(task, dict)}


def _workflow_entry(
    *,
    workflow_id: str,
    label: str,
    task: dict,
    proof: dict,
    ready_keys: list[str],
    command: str,
    native_default: str,
    external_secret_required: bool = False,
    require_operator_task_ready: bool = True,
) -> dict:
    summary = proof.get("summary", {}) if isinstance(proof.get("summary"), dict) else proof
    proof_ready = all(bool(summary.get(key, False)) for key in ready_keys)
    task_ready = bool(task.get("ready", False))
    workflow_ready = bool(proof_ready and (task_ready or not require_operator_task_ready))
    return {
        "workflow_id": workflow_id,
        "label": label,
        "operator_task_id": str(task.get("id", "")),
        "operator_task_ready": task_ready,
        "workflow_ready": workflow_ready,
        "proof_ready": bool(proof_ready),
        "ready_fields": {key: bool(summary.get(key, False)) for key in ready_keys},
        "command_hint": command,
        "native_default": native_default,
        "external_secret_required": external_secret_required,
    }


def build_payload(workspace_dir: str | Path, *, session_id: str = "") -> dict:
    workspace = Path(workspace_dir).resolve()
    wm = WorkspaceManager(workspace)
    guided = build_guided_operator_payload(wm)
    contract = build_built_in_workflow_contract(workspace, session_id=session_id)
    telegram_status = build_telegram_status_report(workspace, session_id=session_id, write_manifest=False)
    tasks = _task_by_id(guided)

    telegram_proof = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-telegram-proof-baseline.json",
    )
    telegram_reply = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-telegram-reply-surface.json",
    )
    inbox_workflow = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-inbox-triage-summary-response-workflow.json",
    )
    telegram_thread = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-telegram-thread-status.json",
    )
    inbox_reply = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-inbox-reply-workflow.json",
    )
    research_brief = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-research-brief-response.json",
    )
    telegram_live_loop = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-telegram-live-loop.json",
    )
    telegram_webhookd = _artifact(
        workspace,
        "artifacts/capability-substrate/latest-telegram-webhookd.json",
    )

    telegram_summary = telegram_proof.get("summary", {}) if isinstance(telegram_proof.get("summary"), dict) else {}
    reply_summary = telegram_reply if isinstance(telegram_reply, dict) else {}
    live_loop_summary = telegram_live_loop.get("summary", {}) if isinstance(telegram_live_loop.get("summary"), dict) else telegram_live_loop
    webhook_summary = telegram_webhookd.get("summary", {}) if isinstance(telegram_webhookd.get("summary"), dict) else telegram_webhookd
    live_send_ready = bool(
        reply_summary.get("reply_sent", False)
        or live_loop_summary.get("telegram_reply_sent", False)
        or webhook_summary.get("telegram_reply_sent", False)
    )
    secret_readiness = dict(telegram_status.get("runtime_secret_readiness") or {})
    webhook_ready = bool(
        webhook_summary.get("telegram_webhook_update_received", False)
        and webhook_summary.get("telegram_webhook_search_success", False)
        and webhook_summary.get("telegram_reply_sent", False)
    )
    polling_ready = bool(
        live_loop_summary.get("telegram_live_update_received", False)
        and live_loop_summary.get("telegram_live_search_success", False)
        and live_loop_summary.get("telegram_reply_sent", False)
    )

    workflows = [
        _workflow_entry(
            workflow_id="research_request_response",
            label="Search and Reply",
            task=tasks.get("search_and_reply", {}),
            proof=telegram_proof,
            ready_keys=[
                "telegram_ingress_received",
                "telegram_chat_allowed",
                "telegram_request_routed",
                "telegram_web_execution_ok",
                "telegram_reply_ready",
            ],
            command="agentos-kernelctl research-workflow --workspace <workspace> --message-text 'search agentos roadmap' --chat-id <chat-id> --json",
            native_default="internal_web_access",
            external_secret_required=False,
            require_operator_task_ready=False,
        ),
        _workflow_entry(
            workflow_id="inbox_triage_summary_response",
            label="Review Inbox",
            task=tasks.get("review_inbox", {}),
            proof=inbox_workflow,
            ready_keys=["workflow_ready"],
            command="agentos-kernelctl inbox-workflow --workspace <workspace> --json",
            native_default="native_inbox_path_or_maildir_adapter",
            external_secret_required=False,
            require_operator_task_ready=False,
        ),
        _workflow_entry(
            workflow_id="telegram_thread_continuity",
            label="Telegram Thread Continuity",
            task=tasks.get("ask_from_telegram", {}),
            proof=telegram_thread,
            ready_keys=["telegram_thread_continuity_ready"],
            command="agentos-kernelctl telegram-thread-status --workspace <workspace> --message-text '<follow-up>' --chat-id <chat-id> --follow-up --json",
            native_default="telegram_thread_context_artifact",
            external_secret_required=False,
            require_operator_task_ready=False,
        ),
        _workflow_entry(
            workflow_id="inbox_reply_workflow",
            label="Inbox Reply Workflow",
            task=tasks.get("review_inbox", {}),
            proof=inbox_reply,
            ready_keys=["inbox_reply_workflow_ready"],
            command="agentos-kernelctl inbox-reply-workflow --workspace <workspace> --json",
            native_default="native_inbox_path_or_maildir_adapter",
            external_secret_required=False,
            require_operator_task_ready=False,
        ),
        _workflow_entry(
            workflow_id="research_brief_response",
            label="Research Brief",
            task=tasks.get("search_and_reply", {}),
            proof=research_brief,
            ready_keys=[
                "research_brief_ready",
                "internal_web_query_success",
                "brief_artifact_exported",
                "telegram_reply_ready",
            ],
            command="agentos-kernelctl research-brief --workspace <workspace> --message-text 'fetch https://example.com' --chat-id <chat-id> --json",
            native_default="internal_web_access",
            external_secret_required=False,
            require_operator_task_ready=False,
        ),
        {
            "workflow_id": "live_telegram_reply_send",
            "label": "Live Telegram Search Reply",
            "operator_task_id": "search_and_reply",
            "operator_task_ready": bool(tasks.get("search_and_reply", {}).get("ready", False)),
            "workflow_ready": bool(webhook_ready or polling_ready),
            "proof_ready": bool(webhook_ready or polling_ready),
            "ready_fields": {
                "telegram_webhook_update_received": bool(webhook_summary.get("telegram_webhook_update_received", False)),
                "telegram_webhook_message_routed": bool(webhook_summary.get("telegram_webhook_message_routed", False)),
                "telegram_webhook_search_success": bool(webhook_summary.get("telegram_webhook_search_success", False)),
                "telegram_polling_attempted": bool(live_loop_summary.get("telegram_polling_attempted", False)),
                "telegram_live_update_received": bool(live_loop_summary.get("telegram_live_update_received", False)),
                "telegram_live_message_routed": bool(live_loop_summary.get("telegram_live_message_routed", False)),
                "telegram_live_search_success": bool(live_loop_summary.get("telegram_live_search_success", False)),
                "telegram_reply_ready": bool(telegram_summary.get("telegram_reply_ready", False) or reply_summary.get("reply_ready", False)),
                "telegram_reply_sent": live_send_ready,
                "telegram_update_offset_persisted": bool(live_loop_summary.get("telegram_update_offset_persisted", False)),
                "telegram_token_configured": bool(reply_summary.get("transport", {}).get("bot_token_configured", False))
                if isinstance(reply_summary.get("transport"), dict)
                else bool(secret_readiness.get("telegram_token_configured", False)),
                "telegram_allowed_chat_configured": bool(secret_readiness.get("telegram_allowed_chat_configured", False)),
                "telegram_live_send_ready": bool(secret_readiness.get("telegram_live_send_ready", False)),
            },
            "command_hint": "systemctl status agentos-telegram-webhookd.service --no-pager; fallback: agentos-kernelctl telegram-live-loop --workspace <workspace> --once --send --json",
            "native_default": "telegram_webhook_internal_web_send_message",
            "external_secret_required": True,
        },
    ]

    ready_workflows = [item["workflow_id"] for item in workflows if item.get("workflow_ready")]
    blocked_workflows = [item["workflow_id"] for item in workflows if not item.get("workflow_ready")]
    next_actions = [
        "Run `agentos-kernelctl guided-operator --workspace <workspace> --json` to inspect top tasks.",
        "Run `agentos-kernelctl research-workflow --workspace <workspace> --message-text 'search agentos roadmap' --chat-id <chat-id> --json` for internal search/reply-ready proof.",
        "Run `agentos-kernelctl inbox-workflow --workspace <workspace> --json` for inbox triage proof.",
        "Run `agentos-kernelctl telegram-thread-status --workspace <workspace> --message-text '<follow-up>' --chat-id <chat-id> --follow-up --json` for continuity proof.",
        "Run `agentos-kernelctl inbox-reply-workflow --workspace <workspace> --json` for reply-ready inbox proof.",
        "Run `agentos-kernelctl research-brief --workspace <workspace> --message-text 'fetch https://example.com' --chat-id <chat-id> --json` for structured brief proof.",
    ]
    if "live_telegram_reply_send" in blocked_workflows:
        next_actions.append(
            "Provide runtime Telegram bot token/chat id and public webhook URL, then keep `agentos-telegram-webhookd.service` active. Use `agentos-kernelctl telegram-live-loop --once --send --json` only as fallback/manual queue drain."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "capability": "workflow_status",
        "workspace": str(workspace),
        "session_id": session_id,
        "runtime_entry_mode": guided.get("runtime_entry_mode", ""),
        "operator_visible_state": guided.get("state", ""),
        "guided_operator_surface_reachable": bool(guided.get("guided_operator_surface_reachable", False)),
        "top_tasks": [
            {
                "id": task.get("id", ""),
                "label": task.get("label", ""),
                "ready": bool(task.get("ready", False)),
                "surface": task.get("surface", ""),
                "command_hint": task.get("command_hint", ""),
            }
            for task in guided.get("top_tasks", [])
            if isinstance(task, dict)
        ],
        "workflow_contract": {
            "schema_version": contract.get("schema_version", ""),
            "workflow_count": len(contract.get("workflows", [])) if isinstance(contract.get("workflows"), list) else 0,
            "telegram_bot_token_configured": bool(
                contract.get("runtime_identity", {}).get("telegram_bot_token_configured", False)
            ),
        },
        "runtime_secret_readiness": {
            "telegram_token_configured": bool(secret_readiness.get("telegram_token_configured", False)),
            "telegram_allowed_chat_configured": bool(secret_readiness.get("telegram_allowed_chat_configured", False)),
            "telegram_live_send_ready": bool(secret_readiness.get("telegram_live_send_ready", False)),
            "telegram_secret_source": str(secret_readiness.get("telegram_secret_source", "none")),
        },
        "workflows": workflows,
        "summary": {
            "workflow_status_ready": bool(guided.get("guided_operator_surface_reachable", False) and workflows),
            "ready_workflows": ready_workflows,
            "blocked_workflows": blocked_workflows,
            "external_secret_blocked": any(item.get("external_secret_required") and not item.get("workflow_ready") for item in workflows),
            "telegram_thread_continuity_ready": bool(
                (telegram_thread.get("summary") or telegram_thread).get("telegram_thread_continuity_ready", False)
            ),
            "inbox_reply_workflow_ready": bool(
                (inbox_reply.get("summary") or inbox_reply).get("inbox_reply_workflow_ready", False)
            ),
            "research_brief_ready": bool(
                (research_brief.get("summary") or research_brief).get("research_brief_ready", False)
            ),
            "brief_artifact_exported": bool(
                (research_brief.get("summary") or research_brief).get("brief_artifact_exported", False)
            ),
            "telegram_polling_attempted": bool(live_loop_summary.get("telegram_polling_attempted", False)),
            "telegram_webhook_update_received": bool(webhook_summary.get("telegram_webhook_update_received", False)),
            "telegram_webhook_message_routed": bool(webhook_summary.get("telegram_webhook_message_routed", False)),
            "telegram_webhook_search_success": bool(webhook_summary.get("telegram_webhook_search_success", False)),
            "telegram_live_update_received": bool(live_loop_summary.get("telegram_live_update_received", False)),
            "telegram_live_message_routed": bool(live_loop_summary.get("telegram_live_message_routed", False)),
            "telegram_live_search_success": bool(live_loop_summary.get("telegram_live_search_success", False)),
            "telegram_update_offset_persisted": bool(
                live_loop_summary.get("telegram_update_offset_persisted", False)
                or webhook_summary.get("telegram_update_offset_persisted", False)
            ),
            "telegram_reply_sent": bool(
                live_loop_summary.get("telegram_reply_sent", False)
                or webhook_summary.get("telegram_reply_sent", False)
            ),
        },
        "next_actions": next_actions,
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("capability") != "workflow_status":
        errors.append("capability must be workflow_status")
    if not isinstance(payload.get("top_tasks"), list):
        errors.append("top_tasks must be a list")
    if not isinstance(payload.get("workflows"), list):
        errors.append("workflows must be a list")
    if not isinstance(payload.get("summary"), dict):
        errors.append("summary must be a dict")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS operator workflow status")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("workflow status: PASS" if result["ok"] else "workflow status: FAIL"))
        return 0 if result["ok"] else 1

    payload = build_payload(args.workspace, session_id=args.session_id)
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", SCHEMA_VERSION)}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        write_json_file(args.output, payload)
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
