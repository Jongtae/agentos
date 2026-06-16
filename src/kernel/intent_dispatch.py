from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from kernel.capability_substrate import _build_telegram_config, _post_json, _trim_output
from kernel.capability_substrate import build_research_brief_response_report
from kernel.operator_activity import append_activity_event

INTENT_DISPATCH_SCHEMA_VERSION = "agentos-intent-dispatch.v1"
MEMORY_NOTES_PATH = "messages/agentos-memory-notes.jsonl"

GREETING_TEXTS = {"hi", "hello", "hey", "안녕", "안녕하세요", "하이"}
STATUS_TEXTS = {"/status", "status", "상태", "현재 상태", "runtime status"}
HELP_TEXTS = {"/help", "help", "도움말"}
START_TEXTS = {"/start", "start"}


def classify_intent(message: str, *, source: str = "operator") -> dict:
    raw = str(message or "").strip()
    normalized = re.sub(r"\s+", " ", raw.lower()).strip()
    if any(token in normalized for token in ("delete all emails", "delete all mail", "메일 전부 삭제", "전부 삭제")):
        return _intent("unknown_needs_clarification", "direct_reply", "deterministic_safety")
    if normalized in START_TEXTS:
        return _intent("telegram_start", "direct_reply", "deterministic_command")
    if normalized in HELP_TEXTS:
        return _intent("telegram_help", "direct_reply", "deterministic_command")
    if normalized in STATUS_TEXTS or ("status" in normalized and "agentos" in normalized) or "상태" in normalized:
        return _intent("runtime_status", "runtime_status", "deterministic_command")
    if normalized in GREETING_TEXTS:
        return _intent("greeting", "direct_reply", "deterministic_greeting")
    if any(token in normalized for token in ("setup", "set up", "설정", "configure", "config")):
        return _intent("setup_help", "direct_reply", "deterministic_setup")
    if any(token in normalized for token in ("gmail", "email", "mail", "메일", "inbox", "답장 초안", "draft a reply")):
        return _intent("gmail_read_or_draft", "gmail_read_or_draft", "deterministic_gmail")
    if any(
        token in normalized
        for token in (
            "restart",
            "reboot",
            "recovery",
            "recover",
            "rejoin",
            "update agentos",
            "upgrade agentos",
            "rollback",
            "roll back",
            "서비스 재시작",
            "재시작",
            "업데이트",
            "롤백",
        )
    ):
        return _intent("lifecycle_recovery", "lifecycle_recovery", "deterministic_lifecycle")
    if any(token in normalized for token in ("지난번", "회의 기록", "record", "records", "prior note", "last agentos meeting")):
        return _intent("record_lookup", "record_lookup", "deterministic_record")
    if any(token in normalized for token in ("calendar", "schedule", "meeting", "캘린더", "일정", "미팅")):
        return _intent("calendar_readonly", "calendar_readonly", "deterministic_calendar")
    if any(token in normalized for token in ("파일", "디렉토리", "directory", "folder", "workspace", "목록", "list files", "ls ")):
        return _intent("local_workspace_search", "local_workspace_search", "deterministic_workspace")
    if any(token in normalized for token in ("기억", "remember", "메모", "note this")):
        return _intent("memory_note", "memory_note", "deterministic_memory")
    if any(token in normalized for token in ("search", "검색", "찾아", "찾기", "summarize", "요약", "roadmap", "http://", "https://")):
        return _intent("web_search_summary", "research_brief_response", "deterministic_web")
    if source == "telegram":
        return _intent("unknown_needs_clarification", "direct_reply", "deterministic_fallback")
    return _intent("unknown_needs_clarification", "direct_reply", "deterministic_fallback")


def build_intent_dispatch_report(
    workspace_dir: str | Path,
    *,
    source: str = "operator",
    message_text: str = "",
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    send_reply: bool = False,
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    request_id = request_id or f"{source}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    source_label = "Telegram" if source == "telegram" else "Operator"
    activity_events: list[dict] = []
    message_preview = _safe_preview(message_text)

    received_kind = "telegram.message_received" if source == "telegram" else "operator.request_received"
    activity_events.append(
        append_activity_event(
            workspace,
            kind=received_kind,
            source_label=source_label,
            human_message=f"{source_label} received: {message_preview}",
            request_id=request_id,
            actor={"surface": source, "chat_id": str(chat_id), "message_id": str(message_id)},
            object={"message_preview": message_preview},
            action="receive_request",
        )
    )

    classification = classify_intent(message_text, source=source)
    intent = classification["intent"]
    capability = classification["capability"]
    activity_events.append(
        append_activity_event(
            workspace,
            kind="intent.classified",
            source_label="AgentOS",
            human_message=f"Understood as: {intent}",
            request_id=request_id,
            intent=intent,
            capability=capability,
            action="classify_intent",
            decision={"state": "classified", "classifier": classification["classifier"]},
        )
    )

    payload = {
        "schema_version": INTENT_DISPATCH_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "capability": "intent_dispatch",
        "source": source,
        "message": message_text,
        "chat_id": str(chat_id),
        "request_id": request_id,
        "message_id": str(message_id),
        "session_id": str(session_id),
        "intent": intent,
        "classifier": classification["classifier"],
        "capability_executed": capability,
        "response": "",
        "telegram_reply_sent": False,
        "telegram_send_attempted": False,
        "web_search_used": False,
        "activity_events_written": 0,
        "research_brief": {},
        "proof": {"ok": False, "reason": "", "session_id": str(session_id)},
        "summary": {},
    }

    try:
        activity_events.append(_capability_event(workspace, "capability.started", request_id, capability, f"Running {capability}"))
        result = _run_capability(
            workspace,
            intent=intent,
            capability=capability,
            message_text=message_text,
            chat_id=chat_id,
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            send_reply=send_reply,
            domain_allowlist=domain_allowlist,
            write_manifest=write_manifest,
        )
        payload.update(result)
        activity_events.append(
            _capability_event(
                workspace,
                "capability.completed",
                request_id,
                capability,
                _completion_message(intent, result),
                intent=intent,
            )
        )
        if payload.get("telegram_reply_sent"):
            activity_events.append(
                append_activity_event(
                    workspace,
                    kind="telegram.reply_sent",
                    source_label="Telegram",
                    human_message="Reply sent to Telegram",
                    request_id=request_id,
                    intent=intent,
                    capability=capability,
                    action="send_reply",
                    decision={"state": "sent"},
                )
            )
        payload["proof"]["ok"] = True
    except Exception as exc:
        payload["proof"]["reason"] = f"intent_dispatch_failure:{exc}"
        activity_events.append(
            _capability_event(
                workspace,
                "capability.failed",
                request_id,
                capability,
                f"{capability} failed: {exc}",
                intent=intent,
                state="failed",
            )
        )

    payload["activity_events_written"] = len(activity_events)
    payload["summary"] = {
        "intent": intent,
        "capability": capability,
        "web_search_used": bool(payload.get("web_search_used", False)),
        "telegram_reply_sent": bool(payload.get("telegram_reply_sent", False)),
        "ok": bool(payload.get("proof", {}).get("ok", False)),
        "failure_class": "" if payload.get("proof", {}).get("ok", False) else str(payload.get("proof", {}).get("reason", "")),
    }
    return payload


def _run_capability(
    workspace: Path,
    *,
    intent: str,
    capability: str,
    message_text: str,
    chat_id: str,
    request_id: str,
    message_id: str,
    session_id: str,
    send_reply: bool,
    domain_allowlist: list[str] | None,
    write_manifest: bool,
) -> dict:
    if intent == "web_search_summary":
        brief = build_research_brief_response_report(
            workspace,
            message_text=message_text,
            chat_id=chat_id,
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            send_reply=send_reply,
            domain_allowlist=domain_allowlist,
            write_manifest=write_manifest,
        )
        response = str(brief.get("brief", {}).get("summary", "") or brief.get("research_workflow", {}).get("reply_report", {}).get("reply_text", "")).strip()
        return {
            "response": response,
            "telegram_reply_sent": bool(brief.get("telegram_reply_sent", False)),
            "telegram_send_attempted": bool(send_reply),
            "web_search_used": True,
            "research_brief": brief,
        }
    if intent == "runtime_status":
        response = _runtime_status_summary(workspace)
    elif intent == "local_workspace_search":
        response = _workspace_listing(workspace)
    elif intent == "memory_note":
        response = _write_memory_note(workspace, message_text, request_id=request_id)
    else:
        response = _direct_response(intent)
    sent = _send_telegram_reply(workspace, chat_id, response) if send_reply and chat_id else False
    return {
        "response": response,
        "telegram_reply_sent": bool(sent),
        "telegram_send_attempted": bool(send_reply and chat_id),
        "web_search_used": False,
    }


def _send_telegram_reply(workspace: Path, chat_id: str, text: str) -> bool:
    config = _build_telegram_config(workspace)
    token = str(config.get("bot_token_value", "")).strip()
    if not token or not str(chat_id).strip():
        return False
    api_base = str(config.get("api_base_url", "https://api.telegram.org")).rstrip("/")
    _status, response = _post_json(
        f"{api_base}/bot{token}/sendMessage",
        {"chat_id": str(chat_id).strip(), "text": text, "disable_web_page_preview": True},
    )
    return bool(response.get("ok", False)) if isinstance(response, dict) else False


def _direct_response(intent: str) -> str:
    if intent == "telegram_start":
        return (
            "AgentOS is connected.\n"
            "You can ask me to search the web, inspect the workspace, summarize files, or show runtime status.\n"
            "Try: status or search AgentOS roadmap and summarize"
        )
    if intent == "telegram_help":
        return (
            "AgentOS commands:\n"
            "- status: show runtime status\n"
            "- search <topic> and summarize: use internal web/search\n"
            "- workspace file list: inspect local workspace\n"
            "- remember <note>: save a memory note"
        )
    if intent == "greeting":
        return "Hi. AgentOS is online. Try: status, or search AgentOS roadmap and summarize."
    return "I need one more detail. Do you want me to search the web, inspect the workspace, summarize a file, or show status?"


def _runtime_status_summary(workspace: Path) -> str:
    config = _build_telegram_config(workspace)
    telegram = "ready" if config.get("telegram_live_send_ready") else "setup needed"
    return "\n".join(
        [
            "AgentOS runtime status",
            f"Workspace: {workspace}",
            f"Telegram: {telegram}",
            "Web: ready",
            "LLM: see TUI status bar or run /setup llm",
        ]
    )


def _workspace_listing(workspace: Path) -> str:
    items = []
    for path in sorted(workspace.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:20]:
        suffix = "/" if path.is_dir() else ""
        items.append(f"- {path.name}{suffix}")
    if not items:
        return f"Workspace is empty: {workspace}"
    return "Workspace items:\n" + "\n".join(items)


def _write_memory_note(workspace: Path, message_text: str, *, request_id: str) -> str:
    path = workspace / MEMORY_NOTES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    note = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "text": str(message_text).strip(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(note, ensure_ascii=True) + "\n")
    return "Memory note saved in the AgentOS workspace."


def _capability_event(
    workspace: Path,
    kind: str,
    request_id: str,
    capability: str,
    human_message: str,
    *,
    intent: str = "",
    state: str = "observed",
) -> dict:
    return append_activity_event(
        workspace,
        kind=kind,
        source_label="AgentOS",
        human_message=human_message,
        request_id=request_id,
        intent=intent,
        capability=capability,
        action=kind.replace(".", "_"),
        decision={"state": state},
    )


def _completion_message(intent: str, result: dict) -> str:
    if intent == "greeting":
        return "Replied without web search"
    if intent in {"telegram_start", "telegram_help"}:
        return "Sent guidance without web search"
    if intent == "runtime_status":
        return "Prepared runtime status"
    if intent == "local_workspace_search":
        return "Inspected workspace"
    if intent == "web_search_summary":
        return "Completed internal web/search summary"
    return _trim_output(str(result.get("response", "")) or "Completed")


def _intent(intent: str, capability: str, classifier: str) -> dict:
    return {"intent": intent, "capability": capability, "classifier": classifier}


def _safe_preview(message: str) -> str:
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    if len(text) > 120:
        text = text[:117] + "..."
    return text
