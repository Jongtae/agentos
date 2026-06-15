#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
for candidate in (SRC_DIR, SCRIPTS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from io_utils import scrub_payload, write_json_file
from kernel.intent_dispatch import build_intent_dispatch_report, classify_intent
from kernel.operator_activity import append_activity_event, build_activity_feed_payload
from kernel_gmail_setup import build_gmail_read_report, build_gmail_status_report
from kernel_phase2_calendar_fixture import build_calendar_fixture_report
from kernel_phase2_gmail_fixture import build_gmail_fixture_report
from kernel_phase2_lifecycle_recovery import build_lifecycle_recovery_report
from kernel_phase2_records import append_record, find_records

SCHEMA_VERSION = "agentos-phase2-run.v1"

DEFAULT_GMAIL_FIXTURE = {
    "messages": [
        {
            "id": "sample-roadmap-1",
            "from": "Mina <mina@example.com>",
            "to": "operator@example.com",
            "subject": "AgentOS Phase 2 roadmap review",
            "body": "Can you review the Phase 2 local-first runtime roadmap and draft a concise reply?",
            "labels": ["INBOX", "IMPORTANT"],
        },
        {
            "id": "sample-status-1",
            "from": "Ops <ops@example.com>",
            "to": "operator@example.com",
            "subject": "Runtime smoke status",
            "body": "The latest local smoke logs are ready for review.",
            "labels": ["INBOX"],
        },
    ]
}

DEFAULT_CALENDAR_FIXTURE = {
    "events": [
        {
            "id": "sample-calendar-roadmap-1",
            "title": "AgentOS roadmap review",
            "start": "2026-06-16T09:00:00+09:00",
            "end": "2026-06-16T09:30:00+09:00",
            "location": "local VM",
            "description": "Review Phase 2 closeout and pick the next safe completion track.",
            "attendees": ["operator@example.com"],
        },
        {
            "id": "sample-calendar-runtime-1",
            "title": "Runtime smoke review",
            "start": "2026-06-16T10:00:00+09:00",
            "end": "2026-06-16T10:15:00+09:00",
            "location": "workspace",
            "description": "Check the latest hardening loop output.",
            "attendees": [],
        },
    ]
}


def default_user_root() -> Path:
    return Path(os.environ.get("AGENTOS_USER_DATA_ROOT", "./agentos-data/user")).expanduser()


def run_phase2(
    *,
    workspace: str | Path,
    user_root: str | Path,
    prompt: str,
    gmail_fixture: str | Path = "",
    calendar_fixture: str | Path = "",
    gmail_live: bool = False,
    gmail_credentials: str | Path = "",
    gmail_token: str | Path = "",
    gmail_mock_response: str | Path = "",
    allow_domains: list[str] | None = None,
) -> dict:
    workspace_path = Path(workspace).resolve()
    user_root_path = Path(user_root).expanduser().resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    user_root_path.mkdir(parents=True, exist_ok=True)

    request_id = f"phase2-run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    prompt = str(prompt or "").strip()
    classification = classify_intent(prompt, source="operator")
    intent = str(classification.get("intent", "unknown_needs_clarification"))
    capability = str(classification.get("capability", "direct_reply"))
    custom_activity = intent in {"gmail_read_or_draft", "calendar_readonly", "record_lookup", "lifecycle_recovery"}

    if custom_activity:
        _event(workspace_path, "operator.request_received", request_id, "Operator", f"Operator received: {_preview(prompt)}")
        _event(
            workspace_path,
            "intent.classified",
            request_id,
            "AgentOS",
            f"Understood as: {intent}",
            intent=intent,
            capability=capability,
            state="classified",
        )
        _event(
            workspace_path,
            "capability.started",
            request_id,
            "AgentOS",
            f"Running {capability}",
            intent=intent,
            capability=capability,
            state="running",
        )

    status = "completed"
    response = ""
    artifacts: dict = {}
    blockers: list[dict] = []
    capability_result: dict = {}

    try:
        if intent == "gmail_read_or_draft":
            query = _query_from_prompt(prompt, fallback="roadmap")
            if gmail_live:
                capability_result = build_gmail_read_report(
                    workspace_path,
                    query=query,
                    credentials_path=gmail_credentials or None,
                    token_path=gmail_token or None,
                    mock_response=gmail_mock_response,
                )
                artifacts["gmail_credentials_path"] = capability_result.get("credentials_path", "")
                artifacts["gmail_token_path"] = capability_result.get("token_path", "")
                if capability_result.get("proof", {}).get("ok"):
                    response = _gmail_live_response(capability_result)
                else:
                    status = "blocked"
                    response = _gmail_live_blocked_response(workspace_path, capability_result)
                    setup_url = _gmail_setup_url()
                    blockers.append(
                        {
                            "id": "gmail-live-oauth-required",
                            "reason": str(capability_result.get("proof", {}).get("reason", "gmail_live_read_not_ready")),
                            "recovery_action": (
                                "Run agentos-kernelctl gmail-setup --serve-http"
                                + (f" and open {setup_url}" if setup_url else "")
                                + ", then retry with --gmail-live."
                            ),
                            "setup_page_url": setup_url,
                        }
                    )
            else:
                fixture = _gmail_fixture_path(workspace_path, gmail_fixture)
                capability_result = build_gmail_fixture_report(fixture, query=query, action="draft")
                response = _gmail_response(capability_result)
                artifacts["gmail_fixture"] = str(fixture)
                blockers.append(
                    {
                        "id": "gmail-oauth-live",
                        "reason": "This run used fixture-backed Gmail data, not real Gmail OAuth.",
                        "recovery_action": "Configure the read-only Gmail setup page and rerun with --gmail-live before claiming real mailbox access.",
                    }
                )
        elif intent == "calendar_readonly":
            query = _query_from_prompt(prompt, fallback="roadmap")
            fixture = _calendar_fixture_path(workspace_path, calendar_fixture)
            capability_result = build_calendar_fixture_report(fixture, query=query, action="summarize")
            response = _calendar_response(capability_result)
            artifacts["calendar_fixture"] = str(fixture)
            blockers.append(
                {
                    "id": "calendar-live-oauth",
                    "reason": "This run used fixture-backed Calendar data, not live Calendar OAuth.",
                    "recovery_action": "Keep Calendar read-only in fixture mode until a live adapter and explicit OAuth setup are designed.",
                }
            )
        elif intent == "record_lookup":
            query = _query_from_prompt(prompt, fallback="roadmap")
            capability_result = find_records(user_root_path, query=query, limit=10)
            response = _records_response(capability_result, query=query)
            artifacts["records_path"] = capability_result.get("records_path", "")
        elif intent == "lifecycle_recovery":
            action = _lifecycle_action(prompt)
            capability_result = build_lifecycle_recovery_report(workspace_path, action=action, confirmed=False)
            status = "blocked" if capability_result.get("needs_confirmation") else "completed"
            response = _lifecycle_response(capability_result)
            artifacts["lifecycle_manifest"] = capability_result.get("manifest_path", "")
            if capability_result.get("needs_confirmation"):
                blockers.append(
                    {
                        "id": "lifecycle-confirmation-required",
                        "reason": f"{action} requires explicit confirmation and was not executed.",
                        "recovery_action": "Review the recovery steps and rerun a future confirmed control surface if appropriate.",
                    }
                )
        else:
            dispatch = build_intent_dispatch_report(
                workspace_path,
                source="operator",
                message_text=prompt,
                request_id=request_id,
                domain_allowlist=allow_domains or None,
                write_manifest=True,
            )
            capability_result = dispatch
            capability = str(dispatch.get("capability_executed", capability))
            response = str(dispatch.get("response", "")).strip()
            if not dispatch.get("proof", {}).get("ok", False):
                status = "failed"

        if not response:
            response = "I need one more detail before I can run that safely."
        record_payload = append_record(
            user_root_path,
            title=f"Phase 2 run: {intent}",
            body=_record_body(prompt=prompt, intent=intent, capability=capability, status=status, response=response),
            source="phase2_run",
            tags=["phase-2", intent, capability, status],
        )
        record = record_payload["records"][0]
        record_path = record_payload.get("records_path", "")
        artifacts["record_path"] = record_path

        if custom_activity:
            final_kind = "capability.blocked" if status == "blocked" else ("capability.failed" if status == "failed" else "capability.completed")
            final_state = "blocked" if status == "blocked" else ("failed" if status == "failed" else "completed")
            _event(
                workspace_path,
                final_kind,
                request_id,
                "AgentOS",
                f"{capability} {final_state}",
                intent=intent,
                capability=capability,
                state=final_state,
            )
        if custom_activity and status == "blocked":
            _event(
                workspace_path,
                "recovery.suggested",
                request_id,
                "AgentOS",
                blockers[0]["recovery_action"] if blockers else "Review recovery guidance.",
                intent=intent,
                capability=capability,
                state="suggested",
            )
    except Exception as exc:
        status = "failed"
        response = f"Phase 2 run failed: {exc}"
        record_payload = append_record(
            user_root_path,
            title="Phase 2 run failed",
            body=_record_body(prompt=prompt, intent=intent, capability=capability, status=status, response=response),
            source="phase2_run",
            tags=["phase-2", intent, capability, "failed"],
        )
        record = record_payload["records"][0]
        artifacts["record_path"] = record_payload.get("records_path", "")
        blockers.append({"id": "phase2-run-failure", "reason": str(exc), "recovery_action": "Inspect the JSON output and activity feed."})
        _event(workspace_path, "capability.failed", request_id, "AgentOS", response, intent=intent, capability=capability, state="failed")

    activity = build_activity_feed_payload(workspace_path, limit=20)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "user_data_root": str(user_root_path),
        "prompt": prompt,
        "request_id": request_id,
        "intent": intent,
        "classifier": classification.get("classifier", ""),
        "capability": capability,
        "status": status,
        "response": response,
        "activity_feed": activity,
        "record": record,
        "artifacts": artifacts,
        "capability_result": capability_result,
        "blockers": blockers,
        "proof": {
            "ok": status in {"completed", "blocked"},
            "testable_cli_surface": True,
            "gmail_fixture_mode": bool(intent == "gmail_read_or_draft" and not gmail_live),
            "calendar_fixture_mode": bool(intent == "calendar_readonly"),
            "gmail_live_read_completed": bool(gmail_live and intent == "gmail_read_or_draft" and capability_result.get("proof", {}).get("ok")),
            "live_gmail_oauth_completed": bool(
                gmail_live
                and intent == "gmail_read_or_draft"
                and capability_result.get("proof", {}).get("ok")
                and capability_result.get("adapter") == "gmail_oauth_readonly"
            ),
            "vm_iso_proof_completed": False,
            "destructive_action_executed": False,
        },
    }
    return scrub_payload(payload)


def _event(
    workspace: Path,
    kind: str,
    request_id: str,
    source_label: str,
    human_message: str,
    *,
    intent: str = "",
    capability: str = "",
    state: str = "observed",
) -> None:
    append_activity_event(
        workspace,
        kind=kind,
        source_label=source_label,
        human_message=human_message,
        request_id=request_id,
        intent=intent,
        capability=capability,
        decision={"state": state},
    )


def _gmail_fixture_path(workspace: Path, fixture: str | Path) -> Path:
    if str(fixture or "").strip():
        return Path(fixture).expanduser().resolve()
    path = workspace / "artifacts" / "phase2-run" / "default-gmail-fixture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_GMAIL_FIXTURE, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _calendar_fixture_path(workspace: Path, fixture: str | Path) -> Path:
    if str(fixture or "").strip():
        return Path(fixture).expanduser().resolve()
    path = workspace / "artifacts" / "phase2-run" / "default-calendar-fixture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CALENDAR_FIXTURE, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _query_from_prompt(prompt: str, *, fallback: str) -> str:
    normalized = str(prompt or "").lower()
    for token in ("roadmap", "agentos", "runtime", "status", "smoke"):
        if token in normalized:
            return token
    return fallback


def _lifecycle_action(prompt: str) -> str:
    normalized = str(prompt or "").lower()
    if "reboot" in normalized:
        return "reboot"
    if "shutdown" in normalized:
        return "shutdown"
    if "rejoin" in normalized or "recover" in normalized:
        return "rejoin-session"
    if "restart" in normalized or "재시작" in normalized:
        return "restart-runtime"
    return "suggest-recovery"


def _gmail_response(result: dict) -> str:
    summary = str(result.get("summary", "")).strip()
    draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    body = str(draft.get("body", "")).strip()
    pieces = []
    if summary:
        pieces.append("Gmail fixture summary:\n" + summary)
    if body:
        pieces.append("Draft reply:\n" + body)
    return "\n\n".join(pieces).strip()


def _calendar_response(result: dict) -> str:
    summary = str(result.get("summary", "")).strip()
    if summary:
        return "Calendar fixture summary:\n" + summary
    return "No Calendar events matched."


def _gmail_live_response(result: dict) -> str:
    summary = str(result.get("summary", "")).strip()
    return "Gmail read-only summary:\n" + (summary or "No Gmail messages matched.")


def _gmail_live_blocked_response(workspace: Path, result: dict) -> str:
    setup_url = _gmail_setup_url()
    reason = str(result.get("proof", {}).get("reason", "gmail_live_read_not_ready"))
    action = str(result.get("operator_action_required", "")).strip()
    if not action:
        action = "Run agentos-kernelctl gmail-setup --serve-http, complete read-only OAuth, then retry with --gmail-live."
    lines = [
        f"Live Gmail read is blocked: {reason}",
        action,
        f"Credential path: {result.get('credentials_path', '')}",
        f"Token path: {result.get('token_path', '')}",
    ]
    if setup_url:
        lines.append(f"Setup page: {setup_url}")
    else:
        lines.append("Start setup page: agentos-kernelctl gmail-setup --serve-http --host 0.0.0.0 --display-host <vm-ip>")
    return "\n".join(lines)


def _gmail_setup_url() -> str:
    return os.environ.get("AGENTOS_GMAIL_SETUP_URL", "").strip()


def _records_response(result: dict, *, query: str) -> str:
    records = result.get("records") if isinstance(result.get("records"), list) else []
    if not records:
        return f"No user-owned records matched: {query}"
    lines = [f"Found {len(records)} user-owned record(s) for: {query}"]
    for record in records[:5]:
        lines.append(f"- {record.get('title', 'untitled')}: {_preview(record.get('body', ''))}")
    return "\n".join(lines)


def _lifecycle_response(result: dict) -> str:
    steps = result.get("recovery_steps") if isinstance(result.get("recovery_steps"), list) else []
    header = "Lifecycle action needs confirmation." if result.get("needs_confirmation") else "Lifecycle recovery guidance ready."
    return header + ("\n" + "\n".join(f"- {step}" for step in steps) if steps else "")


def _record_body(*, prompt: str, intent: str, capability: str, status: str, response: str) -> str:
    return "\n".join(
        [
            f"prompt: {prompt}",
            f"intent: {intent}",
            f"capability: {capability}",
            f"status: {status}",
            "",
            response,
        ]
    )


def _preview(text: object, limit: int = 160) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _print_human(payload: dict) -> None:
    print("AgentOS Phase 2 run")
    print(f"intent: {payload.get('intent', '')}")
    print(f"capability: {payload.get('capability', '')}")
    print(f"status: {payload.get('status', '')}")
    print("")
    print(str(payload.get("response", "")).strip())
    record_path = str(payload.get("artifacts", {}).get("record_path", "")).strip()
    if record_path:
        print("")
        print(f"record: {record_path}")
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    if blockers:
        print("")
        print("next:")
        for blocker in blockers:
            print(f"- {blocker.get('id', 'blocker')}: {blocker.get('recovery_action', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a user-testable Phase 2 local-first runtime loop")
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--user-root", default=str(default_user_root()))
    parser.add_argument("--message", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--gmail-fixture", default="")
    parser.add_argument("--calendar-fixture", default="")
    parser.add_argument("--gmail-live", action="store_true")
    parser.add_argument("--gmail-credentials", default="")
    parser.add_argument("--gmail-token", default="")
    parser.add_argument("--gmail-mock-response", default="")
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    prompt = args.message or args.prompt
    if not prompt.strip():
        raise SystemExit("--message or --prompt is required")
    payload = run_phase2(
        workspace=args.workspace,
        user_root=args.user_root,
        prompt=prompt,
        gmail_fixture=args.gmail_fixture,
        calendar_fixture=args.calendar_fixture,
        gmail_live=args.gmail_live,
        gmail_credentials=args.gmail_credentials,
        gmail_token=args.gmail_token,
        gmail_mock_response=args.gmail_mock_response,
        allow_domains=args.allow_domain,
    )
    if args.output:
        write_json_file(args.output, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    elif not args.output:
        _print_human(payload)
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
