from __future__ import annotations

import mailbox
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote_plus, urlencode, urlparse

from workspace.sandbox import safe_path
from workspace.manager import WorkspaceManager

from kernel.event_fabric.report import query_events, query_session_timeline
from kernel.event_fabric.session_contract import session_correlation_contract

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


CAPABILITY_ARTIFACT_DIRNAME = "capability-substrate"
DOCUMENT_ACCESS_SCHEMA = "agentos-document-access.v1"
WEB_ACCESS_SCHEMA = "agentos-web-access.v1"
INTAKE_SURFACE_SCHEMA = "agentos-intake-surface.v1"
INBOX_CAPABILITY_SCHEMA = "agentos-inbox-capability.v1"
INBOX_ROUTING_CONTRACT_SCHEMA = "agentos-inbox-routing-contract.v1"
INBOX_PROOF_BASELINE_SCHEMA = "agentos-inbox-proof-baseline.v1"
INBOX_NORMALIZED_INTAKE_SCHEMA = "agentos-inbox-normalized-intake.v1"
VERIFIED_BOOT_ATTESTATION_SCHEMA = "agentos-verified-boot-attestation-nonclaim.v1"
OBSERVED_PROOF_INTAKE_STATUS_SCHEMA = "agentos-observed-proof-intake-status.v1"
CALENDAR_READONLY_STATUS_SCHEMA = "agentos-calendar-readonly-status.v1"
CAPABILITY_PROOF_SCHEMA = "agentos-capability-proof-surface.v1"
TELEGRAM_INGRESS_SCHEMA = "agentos-telegram-ingress-contract.v1"
TELEGRAM_ROUTING_SCHEMA = "agentos-telegram-request-routing-contract.v1"
TELEGRAM_STATUS_SCHEMA = "agentos-telegram-status.v1"
TELEGRAM_PROOF_SCHEMA = "agentos-telegram-proof-baseline.v1"
TELEGRAM_WEB_EXECUTION_SCHEMA = "agentos-telegram-web-execution-surface.v1"
TELEGRAM_REPLY_SCHEMA = "agentos-telegram-reply-surface.v1"
TELEGRAM_LIVE_LOOP_SCHEMA = "agentos-telegram-live-loop.v1"
BUILT_IN_WORKFLOW_CONTRACT_SCHEMA = "agentos-built-in-workflow-contract.v1"
RESEARCH_WORKFLOW_SCHEMA = "agentos-research-request-response-workflow.v1"
INBOX_WORKFLOW_SCHEMA = "agentos-inbox-triage-summary-response-workflow.v1"
TELEGRAM_THREAD_STATUS_SCHEMA = "agentos-telegram-thread-status.v1"
INBOX_REPLY_WORKFLOW_SCHEMA = "agentos-inbox-reply-workflow.v1"
RESEARCH_BRIEF_SCHEMA = "agentos-research-brief-response.v1"
TELEGRAM_POLL_INTERVAL_DEFAULT = 5
TELEGRAM_POLL_INTERVAL_MIN = 3
TELEGRAM_POLL_INTERVAL_MAX = 120
TELEGRAM_INGRESS_MANIFEST = "latest-telegram-ingress-contract.json"
TELEGRAM_ROUTING_MANIFEST = "latest-telegram-request-routing.json"
TELEGRAM_STATUS_MANIFEST = "latest-telegram-status.json"
TELEGRAM_PROOF_MANIFEST = "latest-telegram-proof-baseline.json"
TELEGRAM_WEB_EXECUTION_MANIFEST = "latest-telegram-web-execution.json"
TELEGRAM_REPLY_MANIFEST = "latest-telegram-reply-surface.json"
TELEGRAM_LIVE_LOOP_MANIFEST = "latest-telegram-live-loop.json"
TELEGRAM_LIVE_LOOP_OFFSET = "latest-telegram-live-loop-offset.json"
BUILT_IN_WORKFLOW_CONTRACT_MANIFEST = "latest-built-in-workflow-contract.json"
RESEARCH_WORKFLOW_MANIFEST = "latest-research-request-response-workflow.json"
INBOX_WORKFLOW_MANIFEST = "latest-inbox-triage-summary-response-workflow.json"
TELEGRAM_THREAD_STATUS_MANIFEST = "latest-telegram-thread-status.json"
INBOX_REPLY_WORKFLOW_MANIFEST = "latest-inbox-reply-workflow.json"
RESEARCH_BRIEF_MANIFEST = "latest-research-brief-response.json"
RESEARCH_BRIEF_ARTIFACT = "latest-research-brief.json"
TELEGRAM_ENV_KEYS = {
    "allowed_chat_ids": (
        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS",
        "TELEGRAM_ALLOWED_CHAT_IDS",
    ),
    "poll_interval_sec": (
        "AGENTOS_TELEGRAM_POLL_INTERVAL_SEC",
        "TELEGRAM_POLL_INTERVAL_SEC",
    ),
    "polling_enabled": (
        "AGENTOS_TELEGRAM_POLLING_ENABLED",
        "TELEGRAM_POLLING_ENABLED",
    ),
    "bot_token": (
        "AGENTOS_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "AGENTOS_TELEGRAM_TOKEN",
    ),
    "api_base_url": (
        "AGENTOS_TELEGRAM_API_BASE_URL",
        "TELEGRAM_API_BASE_URL",
    ),
    "transport": (
        "AGENTOS_TELEGRAM_TRANSPORT",
        "TELEGRAM_TRANSPORT",
    ),
}

SUPPORTED_DOCUMENT_CLASSES = ("text", "markdown", "json", "html")
SUPPORTED_INTAKE_KINDS = (
    "event_intake",
    "message_intake",
    "feedback_intake",
    "operator_intake",
    "manual_intake",
)
ESCALATION_REASONS = (
    "requires_authentication",
    "interactive_or_js_heavy",
    "compatibility_required",
    "browser_navigation_required",
)
TELEGRAM_BROWSER_FALLBACK_REASONS = ESCALATION_REASONS

_MAX_READ_BYTES = 100_000
_MAX_OUTPUT_CHARS = 4_000
_WEB_TIMEOUT_SEC = 10
_WEB_MAX_BYTES = 50_000
DEFAULT_INBOX_FIXTURE_PATH = "messages/inbox-fixture.json"


def _fetch_web_payload(url: str) -> tuple[bytes, str]:
    if _HTTPX_AVAILABLE:
        with httpx.Client(timeout=_WEB_TIMEOUT_SEC, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "AgentOS/0.1"})
            response.raise_for_status()
            return response.content[:_WEB_MAX_BYTES], str(response.headers.get("content-type", "")).lower()

    request = urllib_request.Request(url, headers={"User-Agent": "AgentOS/0.1"})
    with urllib_request.urlopen(request, timeout=_WEB_TIMEOUT_SEC) as response:
        return response.read(_WEB_MAX_BYTES), str(response.headers.get("content-type", "")).lower()


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    if _HTTPX_AVAILABLE:
        with httpx.Client(timeout=_WEB_TIMEOUT_SEC, follow_redirects=True) as client:
            response = client.post(url, json=payload, headers={"User-Agent": "AgentOS/0.1"})
            response.raise_for_status()
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, {"raw_text": response.text}

    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        headers={"User-Agent": "AgentOS/0.1", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=_WEB_TIMEOUT_SEC) as response:
        raw = response.read()
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception:
            decoded = {"raw_text": raw.decode("utf-8", errors="replace")}
        return int(getattr(response, "status", 200)), decoded


def _get_json(url: str) -> tuple[int, dict]:
    if _HTTPX_AVAILABLE:
        with httpx.Client(timeout=_WEB_TIMEOUT_SEC, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "AgentOS/0.1"})
            response.raise_for_status()
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, {"raw_text": response.text}

    request = urllib_request.Request(url, headers={"User-Agent": "AgentOS/0.1"})
    with urllib_request.urlopen(request, timeout=_WEB_TIMEOUT_SEC) as response:
        raw = response.read()
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception:
            decoded = {"raw_text": raw.decode("utf-8", errors="replace")}
        return int(getattr(response, "status", 200)), decoded


def _looks_like_telegram_polling_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return "409" in text and "conflict" in text


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def capability_artifact_root(workspace_dir: str | Path) -> Path:
    return Path(workspace_dir).resolve() / "artifacts" / CAPABILITY_ARTIFACT_DIRNAME


def _manifest_path(workspace_dir: str | Path, name: str) -> Path:
    root = capability_artifact_root(workspace_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def _read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]
        values[key] = value
    return values


def _env_lookup(env_map: dict[str, str], key_family: tuple[str, ...], default: str = "") -> tuple[str, str]:
    for key in key_family:
        if key in env_map and str(env_map[key]).strip():
            return key, str(env_map[key]).strip()
    return "", default


def _to_bool(value: str, default: bool) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(parsed, minimum)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _normalize_chat_id_list(values: list | tuple | str | int | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, int):
        values = [values]
    if isinstance(values, str):
        normalized = [item.strip() for item in values.split(",")]
    else:
        normalized = [str(item).strip() for item in values]
    return sorted({item for item in normalized if item})


def is_telegram_chat_allowed(chat_id: str, allowed_chat_ids: list[str]) -> bool:
    if not allowed_chat_ids:
        return True
    return str(chat_id).strip() in {str(item).strip() for item in allowed_chat_ids}


def _extract_first_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    if not match:
        return ""
    return match.group(0).rstrip(").,!?")


def _build_telegram_config(workspace_dir: str | Path) -> dict:
    workspace = Path(workspace_dir).resolve()
    wm = WorkspaceManager(workspace)
    spec: dict = wm.spec.get("telegram", {}) if isinstance(wm.spec, dict) else {}

    if not isinstance(spec, dict):
        spec = {}
    polling_cfg = spec.get("polling", {}) if isinstance(spec.get("polling", {}), dict) else {}

    env_file = Path(os.environ.get("AGENTOS_ENV_FILE", Path.home() / ".config" / "agentos" / "env"))
    env_map = {key: str(value) for key, value in os.environ.items()}
    env_map.update(_read_env_file(env_file))

    allowed_key, allowed_raw = _env_lookup(env_map, TELEGRAM_ENV_KEYS["allowed_chat_ids"], default="")
    polling_key, polling_interval_raw = _env_lookup(
        env_map,
        TELEGRAM_ENV_KEYS["poll_interval_sec"],
        default=str(int(polling_cfg.get("interval_sec", TELEGRAM_POLL_INTERVAL_DEFAULT)) if isinstance(polling_cfg.get("interval_sec", TELEGRAM_POLL_INTERVAL_DEFAULT), (int, str)) else TELEGRAM_POLL_INTERVAL_DEFAULT),
    )
    enabled_key, polling_enabled_raw = _env_lookup(
        env_map,
        TELEGRAM_ENV_KEYS["polling_enabled"],
        default="",  # set from spec when empty
    )
    token_key, token_raw = _env_lookup(env_map, TELEGRAM_ENV_KEYS["bot_token"], default="")
    transport_key, transport_raw = _env_lookup(env_map, TELEGRAM_ENV_KEYS["transport"], default="")

    if not allowed_raw:
        allowed_ids = _normalize_chat_id_list(spec.get("allowed_chat_ids", []))
        allowed_source = "spec" if allowed_ids else "default"
    else:
        allowed_ids = _normalize_chat_id_list(allowed_raw)
        allowed_source = f"env:{allowed_key}"

    if polling_key:
        polling_interval = _to_int(
            polling_interval_raw,
            TELEGRAM_POLL_INTERVAL_DEFAULT,
            minimum=TELEGRAM_POLL_INTERVAL_MIN,
            maximum=TELEGRAM_POLL_INTERVAL_MAX,
        )
        polling_interval_source = f"env:{polling_key}"
    else:
        polling_interval = _to_int(
            str(polling_cfg.get("interval_sec", TELEGRAM_POLL_INTERVAL_DEFAULT)),
            TELEGRAM_POLL_INTERVAL_DEFAULT,
            minimum=TELEGRAM_POLL_INTERVAL_MIN,
            maximum=TELEGRAM_POLL_INTERVAL_MAX,
        )
        polling_interval_source = "spec" if polling_cfg.get("interval_sec") is not None else "default"

    if enabled_key:
        polling_enabled = _to_bool(polling_enabled_raw, True)
        polling_enabled_source = f"env:{enabled_key}"
    elif isinstance(polling_cfg, dict) and "enabled" in polling_cfg:
        polling_enabled = _to_bool(str(polling_cfg.get("enabled")), True)
        polling_enabled_source = "spec"
    else:
        polling_enabled = True
        polling_enabled_source = "default"

    if token_key:
        bot_token = token_raw
        bot_token_source = f"env:{token_key}"
    elif isinstance(spec.get("bot_token"), str):
        bot_token = str(spec.get("bot_token", ""))
        bot_token_source = "spec"
    else:
        bot_token = ""
        bot_token_source = "default"

    spec_transport = spec.get("transport") if isinstance(spec.get("transport"), str) else ""
    if transport_key:
        transport = transport_raw.strip().lower()
        transport_source = f"env:{transport_key}"
    elif spec_transport:
        transport = str(spec_transport).strip().lower()
        transport_source = "spec"
    else:
        transport = "polling"
        transport_source = "default"
    if transport not in {"polling", "webhook"}:
        transport = "polling"
        transport_source = f"{transport_source}:invalid_fallback"

    return {
        "workspace": str(workspace),
        "env_file": str(env_file),
        "spec_has_telegram": bool(spec),
        "transport": transport,
        "transport_source": transport_source,
        "allowed_chat_ids": allowed_ids,
        "allowed_chat_ids_source": allowed_source,
        "polling_interval_sec": polling_interval,
        "polling_interval_source": polling_interval_source,
        "polling_enabled": polling_enabled,
        "polling_enabled_source": polling_enabled_source,
        "bot_token_configured": bool(bot_token),
        "bot_token_source": bot_token_source,
        "telegram_secret_source": "runtime_env" if token_key else ("workspace_spec" if bot_token else "none"),
        "telegram_allowed_chat_configured": bool(allowed_ids),
        "telegram_live_send_ready": bool(bot_token and allowed_ids),
        "bot_token_masked": "***" if bot_token else "",
        "bot_token_value": bot_token,
        "api_base_url": str(
            _env_lookup(
                env_map,
                TELEGRAM_ENV_KEYS["api_base_url"],
                default=str(spec.get("api_base_url", "https://api.telegram.org")),
            )[1]
        ).strip()
        or "https://api.telegram.org",
    }


def _coercive_int(value: object, default: int) -> int:
    try:
        return _to_int(str(value), default)
    except (TypeError, ValueError):
        return default


def _build_telegram_contract_payload(base_config: dict) -> dict:
    allowed_count = len(base_config.get("allowed_chat_ids") or [])
    return {
        "default_selected_path": "native_telegram_path",
        "paths": [
            {
                "path_id": "native_telegram_path",
                "path_kind": "native",
                "source_kind": "spec_or_env_config",
                "relative_path": "capability_substrate.telegram_ingress_contract",
                "mediation_cost": "low",
                "native_telegram_handled": True,
                "telegram_adapter_required": False,
                "chat_policy": "allow_list" if allowed_count else "allow_all",
            },
            {
                "path_id": "telegram_api_adapter_path",
                "path_kind": "adapter",
                "source_kind": "telegram_api_adapter",
                "relative_path": "<telegram_api_adapter>",
                "mediation_cost": "medium",
                "native_telegram_handled": False,
                "telegram_adapter_required": True,
                "chat_policy": "allow_list" if allowed_count else "allow_all",
            },
        ],
        "selection_rules": [
            "prefer native_telegram_path when local config is available",
            "select telegram_api_adapter_path when provider-side mediation is required",
            "default allowed-chat policy permits all when no explicit allow list is configured",
        ],
        "proof_fields": [
            "allowed_chat_ids_source",
            "polling_enabled",
            "polling_interval_sec",
            "bot_token_configured",
            "polling_interval_source",
            "polling_enabled_source",
            "bot_token_source",
        ],
    }


def _telegram_polling_status(base_config: dict) -> tuple[bool, str]:
    if str(base_config.get("transport", "polling")) == "webhook":
        return True, "webhook_transport"
    if not bool(base_config.get("polling_enabled", True)):
        return True, "polling_disabled"
    if not bool(base_config.get("bot_token_configured", False)):
        return False, "missing_bot_token"
    if _coercive_int(base_config.get("polling_interval_sec"), TELEGRAM_POLL_INTERVAL_DEFAULT) <= 0:
        return False, "invalid_poll_interval"
    return True, ""


def build_telegram_ingress_contract(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    contract_payload = _build_telegram_contract_payload(config)
    ok, reason = _telegram_polling_status(config)

    payload = {
        "schema_version": TELEGRAM_INGRESS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_ingress_contract",
        "default_selected_path": contract_payload["default_selected_path"],
        "paths": contract_payload["paths"],
        "selection_rules": contract_payload["selection_rules"],
        "allowed_chat_ids": list(config.get("allowed_chat_ids") or []),
        "allowed_chat_ids_source": config.get("allowed_chat_ids_source", "default"),
        "polling_interval_sec": _coercive_int(config.get("polling_interval_sec"), TELEGRAM_POLL_INTERVAL_DEFAULT),
        "polling_interval_source": str(config.get("polling_interval_source", "default")),
        "polling_enabled": bool(config.get("polling_enabled", True)),
        "polling_enabled_source": str(config.get("polling_enabled_source", "default")),
        "bot_token_configured": bool(config.get("bot_token_configured", False)),
        "bot_token_source": str(config.get("bot_token_source", "default")),
        "bot_token_masked": str(config.get("bot_token_masked", "")),
        "spec_has_telegram": bool(config.get("spec_has_telegram", False)),
        "proof_fields": contract_payload["proof_fields"],
        "proof": {
            "ok": bool(ok),
            "not_ready_reason": reason,
            "chat_policy": "allow_list" if (config.get("allowed_chat_ids") or []) else "allow_all",
            "polling_interval_min": TELEGRAM_POLL_INTERVAL_MIN,
            "polling_interval_max": TELEGRAM_POLL_INTERVAL_MAX,
            "session_id": str(session_id).strip(),
        },
        "session_contract": session_correlation_contract(),
        "correlation": {
            "session_id": str(session_id).strip(),
            "request_id": "",
            "approval_id": "",
            "trace_id": "",
            "run_id": "",
            "boot_id": "",
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_ingress_contract_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_INGRESS_MANIFEST,
            payload,
        )
    return payload


def build_built_in_workflow_contract(workspace_dir: str | Path, *, session_id: str = "") -> dict:
    workspace = Path(workspace_dir).resolve()
    wm = WorkspaceManager(workspace)
    config = _build_telegram_config(workspace)
    manifest_path = _manifest_path(workspace, BUILT_IN_WORKFLOW_CONTRACT_MANIFEST)

    workflows = [
        {
            "id": "research_request_response",
            "label": "Research Request Response",
            "status": "baseline_ready",
            "goal": "Accept an external request, perform native internal web research, summarize the result, and prepare a reply.",
            "advances": [
                "capability ownership",
                "OS-native defaults for Codex",
                "mediation cost reduction",
            ],
            "entry_surfaces": [
                "guided_operator.ask_from_telegram",
                "telegram_ingress",
            ],
            "primary_runtime_path": [
                "telegram_ingress",
                "telegram_request_routing",
                "telegram_web_execution",
                "telegram_reply",
            ],
            "required_surfaces": [
                "telegram-status",
                "telegram-proof",
                "telegram-web-execution",
                "telegram-reply",
                "web-access",
                "guided-operator",
            ],
            "links": {
                "proof": "agentos-kernelctl telegram-proof --json",
                "task": "guided_operator.ask_from_telegram",
                "runtime": "agentos-kernelctl telegram-web-execution --json",
            },
            "proof_fields": [
                "telegram_ingress_received",
                "telegram_request_routed",
                "internal_web_query_success",
                "telegram_reply_ready",
            ],
            "acceptance_focus": "Telegram ingress to native internal web query to reply-ready output",
        },
        {
            "id": "inbox_triage_summary_response",
            "label": "Inbox Triage Summary Response",
            "status": "contract_ready",
            "goal": "Review built-in inbox intake, summarize the message state, and prepare an operator-visible response path.",
            "advances": [
                "capability ownership",
                "default OS event/message/document visibility for Codex",
            ],
            "entry_surfaces": [
                "guided_operator.review_inbox",
                "inbox_intake",
            ],
            "primary_runtime_path": [
                "inbox_intake",
                "inbox_proof",
                "first_run_summary",
            ],
            "required_surfaces": [
                "inbox-capability",
                "inbox-intake",
                "inbox-proof",
                "guided-operator",
                "status",
            ],
            "links": {
                "proof": "agentos-kernelctl inbox-proof --json",
                "task": "guided_operator.review_inbox",
                "runtime": "agentos-kernelctl inbox-intake --json",
            },
            "proof_fields": [
                "message_thread_correlated",
                "attachment_visibility_ok",
                "inbox_execution_ready",
            ],
            "acceptance_focus": "Built-in inbox visibility to summary-ready state inside the managed runtime",
        },
    ]

    payload = {
        "schema_version": BUILT_IN_WORKFLOW_CONTRACT_SCHEMA,
        "capability": "built_in_workflow_contract",
        "generated_at": _utc_now(),
        "workspace": str(workspace),
        "session_id": session_id,
        "runtime_identity": {
            "runtime_family": "kernel_mediated_codex_runtime",
            "interactive_workspace": str(workspace),
            "telegram_polling_transport": "bot_polling",
            "telegram_bot_token_configured": bool(config["bot_token_configured"]),
            "allowed_chat_count": len(config["allowed_chat_ids"]),
        },
        "workflow_policy": {
            "strategy": "agentos_first_built_in_functions",
            "operator_model": "task_centric_terminal_first",
            "browser_role": "escalated_fallback_only",
            "guide_mode_role": "fallback_only",
        },
        "workflows": workflows,
        "artifacts": {
            "latest_built_in_workflow_contract_manifest_json": str(manifest_path),
        },
    }

    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_research_request_response_workflow_report(
    workspace_dir: str | Path,
    *,
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
    routing_report = build_telegram_request_routing_contract(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        write_manifest=False,
    )
    execution_report = build_telegram_web_execution_report(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        routing_report=routing_report,
        domain_allowlist=domain_allowlist,
        write_manifest=False,
    )
    reply_report = build_telegram_reply_surface_report(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        send_reply=send_reply,
        routing_report=routing_report,
        execution_report=execution_report,
        domain_allowlist=domain_allowlist,
        write_manifest=False,
    )
    manifest_path = _manifest_path(workspace, RESEARCH_WORKFLOW_MANIFEST)
    browser_escalation_used = bool(execution_report.get("browser_escalation_used", False))
    payload = {
        "schema_version": RESEARCH_WORKFLOW_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "workflow",
        "capability": "research_request_response_workflow",
        "workflow_id": "research_request_response",
        "workflow_label": "Research Request Response",
        "telegram_request_id": str(routing_report.get("telegram_request_id", "")).strip() or str(request_id).strip(),
        "telegram_chat_id": str(routing_report.get("telegram_chat_id", "")).strip() or str(chat_id).strip(),
        "entry_surface": "guided_operator.ask_from_telegram",
        "selected_intent": str(routing_report.get("selected_intent", "")),
        "selected_path": str(routing_report.get("selected_path", "")),
        "browser_escalation_used": browser_escalation_used,
        "browser_escalation_reason": str(execution_report.get("browser_escalation_reason", "")),
        "workflow_ready": bool(
            routing_report.get("telegram_request_routed", False)
            and execution_report.get("native_handled", False)
            and reply_report.get("reply_ready", False)
        ),
        "steps": [
            {
                "id": "telegram_request_routing",
                "ok": bool(routing_report.get("telegram_request_routed", False)),
                "surface": "telegram-routing",
            },
            {
                "id": "internal_web_execution",
                "ok": bool(execution_report.get("native_handled", False)),
                "surface": "telegram-web-execution",
            },
            {
                "id": "telegram_reply",
                "ok": bool(reply_report.get("reply_ready", False)),
                "surface": "telegram-reply",
            },
        ],
        "summary": {
            "telegram_ingress_received": bool(routing_report.get("telegram_chat_allowed", False)),
            "telegram_request_routed": bool(routing_report.get("telegram_request_routed", False)),
            "internal_web_query_success": bool(execution_report.get("native_handled", False)),
            "telegram_reply_ready": bool(reply_report.get("reply_ready", False)),
            "telegram_reply_sent": bool(reply_report.get("reply_sent", False)),
            "browser_escalation_used": browser_escalation_used,
        },
        "links": {
            "proof": "agentos-kernelctl telegram-proof --json",
            "task": "guided_operator.ask_from_telegram",
            "runtime": "agentos-kernelctl telegram-web-execution --json",
            "reply": "agentos-kernelctl telegram-reply --json",
        },
        "routing_report": routing_report,
        "execution_report": execution_report,
        "reply_report": reply_report,
        "artifacts": {
            "latest_research_request_response_workflow_manifest_json": str(manifest_path),
        },
    }
    if write_manifest:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_telegram_thread_status_report(
    workspace_dir: str | Path,
    *,
    message_text: str = "",
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    follow_up: bool = False,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    manifest_path = _manifest_path(workspace, TELEGRAM_THREAD_STATUS_MANIFEST)
    previous: dict = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    request_identifier = str(request_id).strip() or str(message_id).strip() or "telegram-request-pending"
    previous_context = dict(previous.get("current_context") or {})
    same_chat = bool(previous_context and str(previous_context.get("chat_id", "")) == str(chat_id).strip())
    follow_up_linked = bool(follow_up and same_chat)
    current_context = {
        "chat_id": str(chat_id).strip(),
        "request_id": request_identifier,
        "message_id": str(message_id).strip(),
        "session_id": str(session_id).strip() or f"telegram-chat-{str(chat_id).strip() or 'unknown'}",
        "message_text": str(message_text).strip(),
        "previous_request_id": str(previous_context.get("request_id", "")) if same_chat else "",
    }
    payload = {
        "schema_version": TELEGRAM_THREAD_STATUS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_thread_status",
        "telegram_chat_id": current_context["chat_id"],
        "telegram_request_id": current_context["request_id"],
        "thread_key": f"telegram:{current_context['chat_id'] or 'unknown'}",
        "current_context": current_context,
        "previous_context": previous_context if same_chat else {},
        "first_request_created": bool(current_context["chat_id"] and current_context["request_id"]),
        "follow_up_requested": bool(follow_up),
        "follow_up_linked": follow_up_linked,
        "rejoin_lookup_succeeded": bool(previous_context) if follow_up else bool(current_context["chat_id"]),
        "telegram_thread_continuity_ready": bool(
            current_context["chat_id"]
            and current_context["request_id"]
            and ((not follow_up) or follow_up_linked)
        ),
        "artifacts": {
            "latest_telegram_thread_status_manifest_json": str(manifest_path),
        },
    }
    if write_manifest:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_inbox_triage_summary_response_workflow_report(
    workspace_dir: str | Path,
    *,
    maildir_path: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    intake_report = build_inbox_normalized_intake_report(
        workspace,
        maildir_path=maildir_path,
        session_id=session_id,
        write_manifest=False,
    )
    proof_report = build_inbox_proof_baseline_report(
        workspace,
        maildir_path=maildir_path,
        session_id=session_id,
        write_manifest=False,
    )
    from kernel.first_run_summary import build_first_run_summary_report

    summary_report = build_first_run_summary_report(
        workspace,
        write_manifest=False,
    )
    manifest_path = _manifest_path(workspace, INBOX_WORKFLOW_MANIFEST)
    intake_summary = dict(intake_report.get("summary") or {})
    proof_summary = dict(proof_report.get("summary") or {})
    first_run_summary = dict(summary_report.get("summary") or {})
    workflow_ready = bool(
        intake_summary.get("inbox_execution_ready", False)
        and proof_summary.get("inbox_execution_ready", False)
        and first_run_summary.get("capability_proof_ready", False)
    )
    payload = {
        "schema_version": INBOX_WORKFLOW_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "workflow",
        "capability": "inbox_triage_summary_response_workflow",
        "workflow_id": "inbox_triage_summary_response",
        "workflow_label": "Inbox Triage Summary Response",
        "entry_surface": "guided_operator.review_inbox",
        "selected_path": str(intake_report.get("selected_path", "")),
        "path_kind": str(intake_report.get("path_kind", "")),
        "source_kind": str(intake_report.get("source_kind", "")),
        "workflow_ready": workflow_ready,
        "steps": [
            {
                "id": "inbox_intake",
                "ok": bool(intake_summary.get("inbox_execution_ready", False)),
                "surface": "inbox-intake",
            },
            {
                "id": "inbox_proof",
                "ok": bool(proof_summary.get("inbox_execution_ready", False)),
                "surface": "inbox-proof",
            },
            {
                "id": "first_run_summary",
                "ok": bool(first_run_summary.get("capability_proof_ready", False)),
                "surface": "first-run-summary",
            },
        ],
        "summary": {
            "message_thread_correlated": bool(proof_summary.get("message_thread_correlated", False)),
            "attachment_visibility_ok": bool(proof_summary.get("attachment_visibility_ok", False)),
            "inbox_execution_ready": bool(proof_summary.get("inbox_execution_ready", False)),
            "summary_response_ready": bool(first_run_summary.get("capability_proof_ready", False)),
            "native_inbox_handled": bool(proof_summary.get("native_inbox_handled", False)),
            "inbox_adapter_required": bool(proof_summary.get("inbox_adapter_required", False)),
        },
        "links": {
            "proof": "agentos-kernelctl inbox-proof --json",
            "task": "guided_operator.review_inbox",
            "runtime": "agentos-kernelctl inbox-intake --json",
            "reply": "agentos-kernelctl first-run-summary --json",
        },
        "intake_report": intake_report,
        "proof_report": proof_report,
        "summary_report": summary_report,
        "artifacts": {
            "latest_inbox_triage_summary_response_workflow_manifest_json": str(manifest_path),
        },
    }
    if write_manifest:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_inbox_reply_workflow_report(
    workspace_dir: str | Path,
    *,
    maildir_path: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    inbox_workflow = build_inbox_triage_summary_response_workflow_report(
        workspace,
        maildir_path=maildir_path,
        session_id=session_id,
        write_manifest=False,
    )
    summary = dict(inbox_workflow.get("summary") or {})
    selected_path = str(inbox_workflow.get("selected_path", ""))
    source_kind = str(inbox_workflow.get("source_kind", ""))
    reply_draft = (
        "AgentOS inbox summary is ready. Suggested response: acknowledge receipt, summarize the request, "
        "and ask for approval before taking external action."
    )
    manifest_path = _manifest_path(workspace, INBOX_REPLY_WORKFLOW_MANIFEST)
    payload = {
        "schema_version": INBOX_REPLY_WORKFLOW_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "workflow",
        "capability": "inbox_reply_workflow",
        "workflow_id": "inbox_reply_workflow",
        "entry_surface": "guided_operator.review_inbox",
        "selected_path": selected_path,
        "source_kind": source_kind,
        "inbox_reply_workflow_ready": bool(inbox_workflow.get("workflow_ready", False) and reply_draft),
        "reply_draft_ready": bool(reply_draft),
        "reply_draft": reply_draft,
        "source_status": {
            "native_fixture_ready": bool(summary.get("native_inbox_handled", False)),
            "maildir_adapter_ready": bool(source_kind == "maildir"),
            "imap_adapter_ready": False,
            "imap_adapter_blocked_reason": "runtime_credentials_not_configured",
            "gmail_adapter_path": "imap_adapter_shape",
        },
        "summary": {
            "message_thread_correlated": bool(summary.get("message_thread_correlated", False)),
            "attachment_visibility_ok": bool(summary.get("attachment_visibility_ok", False)),
            "inbox_execution_ready": bool(summary.get("inbox_execution_ready", False)),
            "native_vs_adapter_split_recorded": True,
            "inbox_reply_workflow_ready": bool(inbox_workflow.get("workflow_ready", False) and reply_draft),
        },
        "links": {
            "triage": "agentos-kernelctl inbox-workflow --json",
            "proof": "agentos-kernelctl inbox-proof --json",
            "operator": "agentos-kernelctl workflow-status --json",
        },
        "inbox_workflow": inbox_workflow,
        "artifacts": {
            "latest_inbox_reply_workflow_manifest_json": str(manifest_path),
        },
    }
    if write_manifest:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_research_brief_response_report(
    workspace_dir: str | Path,
    *,
    message_text: str = "search agentos roadmap",
    chat_id: str = "1001",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    send_reply: bool = False,
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    research = build_research_request_response_workflow_report(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        send_reply=send_reply,
        domain_allowlist=domain_allowlist,
        write_manifest=False,
    )
    execution = dict(research.get("execution_report") or {})
    reply = dict(research.get("reply_report") or {})
    preview = str(execution.get("proof", {}).get("text_preview", "")).strip()
    source = str(execution.get("execution_url", "")).strip()
    brief = {
        "title": "AgentOS Research Brief",
        "request": str(message_text).strip(),
        "summary": _trim_output(preview.replace("\n", " ").strip() or str(reply.get("reply_text", "")).strip()),
        "source": source,
        "proof_pointer": "agentos-kernelctl research-workflow --json",
    }
    manifest_path = _manifest_path(workspace, RESEARCH_BRIEF_MANIFEST)
    brief_path = _manifest_path(workspace, RESEARCH_BRIEF_ARTIFACT)
    brief_artifact_exported = False
    if write_manifest and brief["summary"]:
        brief_path.write_text(json.dumps(brief, ensure_ascii=True) + "\n", encoding="utf-8")
        brief_artifact_exported = brief_path.is_file() and brief_path.stat().st_size > 0
    payload = {
        "schema_version": RESEARCH_BRIEF_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "workflow",
        "capability": "research_brief_response",
        "workflow_id": "research_brief_response",
        "telegram_chat_id": str(chat_id).strip(),
        "telegram_request_id": str(research.get("telegram_request_id", "")).strip(),
        "research_brief_ready": bool(research.get("workflow_ready", False) and brief["summary"]),
        "internal_web_query_success": bool(research.get("summary", {}).get("internal_web_query_success", False)),
        "brief_artifact_exported": bool(brief_artifact_exported),
        "telegram_reply_ready": bool(reply.get("reply_ready", False)),
        "telegram_reply_sent": bool(reply.get("reply_sent", False)),
        "browser_escalation_used": bool(research.get("browser_escalation_used", False)),
        "brief": brief,
        "summary": {
            "research_brief_ready": bool(research.get("workflow_ready", False) and brief["summary"]),
            "internal_web_query_success": bool(research.get("summary", {}).get("internal_web_query_success", False)),
            "brief_artifact_exported": bool(brief_artifact_exported),
            "telegram_reply_ready": bool(reply.get("reply_ready", False)),
            "telegram_reply_sent": bool(reply.get("reply_sent", False)),
        },
        "links": {
            "workflow": "agentos-kernelctl research-workflow --json",
            "reply": "agentos-kernelctl telegram-reply --json",
            "operator": "agentos-kernelctl workflow-status --json",
        },
        "research_workflow": research,
        "artifacts": {
            "latest_research_brief_response_manifest_json": str(manifest_path),
            "latest_research_brief_json": str(brief_path) if brief_artifact_exported else "",
        },
    }
    if write_manifest:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def build_telegram_status_report(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    ok, reason = _telegram_polling_status(config)
    chat_policy = "allow_list" if config.get("allowed_chat_ids") else "allow_all"
    payload = {
        "schema_version": TELEGRAM_STATUS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_status",
        "status": "ready" if ok else "watch",
        "reason": reason,
        "capability_native_ready": ok,
        "native_path_default": True,
        "native_handled": bool(config.get("polling_enabled", True)),
        "escalated_handled": not bool(config.get("polling_enabled", True)),
        "unsupported_or_deferred": not ok,
        "mediation_cost": "low" if ok else "deferred",
        "polling": {
            "enabled": bool(config.get("polling_enabled", True)),
            "enabled_source": str(config.get("polling_enabled_source", "default")),
            "interval_sec": _coercive_int(config.get("polling_interval_sec"), TELEGRAM_POLL_INTERVAL_DEFAULT),
            "interval_source": str(config.get("polling_interval_source", "default")),
            "interval_min": TELEGRAM_POLL_INTERVAL_MIN,
            "interval_max": TELEGRAM_POLL_INTERVAL_MAX,
        },
        "chat_policy": {
            "mode": chat_policy,
            "allowed_chat_ids": list(config.get("allowed_chat_ids") or []),
            "allowed_chat_ids_source": str(config.get("allowed_chat_ids_source", "default")),
        },
        "bot_token": {
            "configured": bool(config.get("bot_token_configured", False)),
            "source": str(config.get("bot_token_source", "default")),
            "masked": str(config.get("bot_token_masked", "")),
        },
        "runtime_secret_readiness": {
            "telegram_token_configured": bool(config.get("bot_token_configured", False)),
            "telegram_allowed_chat_configured": bool(config.get("telegram_allowed_chat_configured", False)),
            "telegram_live_send_ready": bool(config.get("telegram_live_send_ready", False)),
            "telegram_secret_source": str(config.get("telegram_secret_source", "none")),
        },
        "proof": {
            "ok": bool(ok),
            "native_path": "spec_or_env_config",
            "artifact_ready": True,
            "session_id": str(session_id).strip(),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_status_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_STATUS_MANIFEST,
            payload,
        )
    return payload


def build_telegram_proof_baseline_report(
    workspace_dir: str | Path,
    *,
    message_text: str = "",
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    reply_sent: bool = False,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    write_nested_manifests = bool(write_manifest)
    status_report = build_telegram_status_report(
        workspace,
        session_id=session_id,
        write_manifest=write_nested_manifests,
    )
    contract_report = build_telegram_ingress_contract(
        workspace,
        session_id=session_id,
        write_manifest=write_nested_manifests,
    )
    routing_report = build_telegram_request_routing_contract(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        write_manifest=write_nested_manifests,
    )
    execution_report = build_telegram_web_execution_report(
        workspace,
        routing_report=routing_report,
        session_id=session_id,
        write_manifest=write_nested_manifests,
    )
    reply_report = build_telegram_reply_surface_report(
        workspace,
        message_text=message_text,
        chat_id=chat_id,
        request_id=request_id,
        message_id=message_id,
        session_id=session_id,
        send_reply=reply_sent,
        routing_report=routing_report,
        execution_report=execution_report,
        write_manifest=write_nested_manifests,
    )
    status_ok = bool(status_report.get("proof", {}).get("ok", False))
    contract_ok = bool(contract_report.get("proof", {}).get("ok", False))
    ingress_received = bool(str(message_text).strip())
    chat_allowed = bool(routing_report.get("telegram_chat_allowed", False))
    request_routed = bool(routing_report.get("telegram_request_routed", False))
    routing_ok = bool(routing_report.get("proof", {}).get("ok", False))
    execution_ok = bool(execution_report.get("proof", {}).get("ok", False))
    execution_browser_escalation = bool(execution_report.get("browser_escalation_used", False))
    execution_browser_reason = str(execution_report.get("browser_escalation_reason", ""))
    execution_browser_allowed = bool(execution_report.get("browser_escalation_allowed", False))
    payload = {
        "schema_version": TELEGRAM_PROOF_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_proof_baseline",
        "status_report": status_report,
        "ingress_contract": contract_report,
        "routing_report": routing_report,
        "execution_report": execution_report,
        "proof_fields": [
            "telegram_ingress_received",
            "telegram_chat_allowed",
            "telegram_request_id",
            "telegram_request_routed",
            "telegram_web_execution_ok",
            "telegram_browser_escalation_used",
            "telegram_browser_escalation_allowed",
            "telegram_browser_escalation_reason",
            "telegram_reply_ready",
            "telegram_reply_sent",
            "ingress_contract.proof.ok",
            "telegram_adapter_readiness",
            "artifact_shape_stable",
        ],
        "summary": {
            "status_ok": bool(status_ok),
            "contract_ok": bool(contract_ok),
            "routing_ok": bool(routing_ok),
            "telegram_ingress_received": ingress_received,
            "telegram_chat_allowed": chat_allowed,
            "telegram_request_id": str(routing_report.get("telegram_request_id", "")),
            "telegram_request_routed": request_routed,
            "telegram_web_execution_ok": execution_ok,
            "telegram_browser_escalation_used": execution_browser_escalation,
            "telegram_browser_escalation_allowed": execution_browser_allowed,
            "telegram_browser_escalation_reason": execution_browser_reason,
            "telegram_reply_ready": bool(reply_report.get("reply_ready", False)),
            "telegram_reply_sent": bool(reply_report.get("reply_sent", False)),
            "telegram_adapter_readiness": bool(status_ok or contract_ok or routing_ok),
            "artifact_shape_stable": bool(
                bool(status_report.get("artifacts", {}).get("latest_telegram_status_manifest_json"))
                and bool(contract_report.get("artifacts", {}).get("latest_telegram_ingress_contract_manifest_json"))
                and bool(routing_report.get("artifacts", {}).get("latest_telegram_request_routing_manifest_json"))
                and bool(execution_report.get("artifacts", {}).get("latest_telegram_web_execution_manifest_json"))
                and bool(reply_report.get("artifacts", {}).get("latest_telegram_reply_surface_manifest_json"))
            ),
        },
        "reply_report": reply_report,
        "artifacts": {
            "latest_telegram_status_manifest_json": str(
                status_report.get("artifacts", {}).get("latest_telegram_status_manifest_json", "")
            ),
            "latest_telegram_ingress_contract_manifest_json": str(
                contract_report.get("artifacts", {}).get("latest_telegram_ingress_contract_manifest_json", "")
            ),
            "latest_telegram_request_routing_manifest_json": str(
                routing_report.get("artifacts", {}).get("latest_telegram_request_routing_manifest_json", "")
            ),
            "latest_telegram_web_execution_manifest_json": str(
                execution_report.get("artifacts", {}).get("latest_telegram_web_execution_manifest_json", "")
            ),
            "latest_telegram_reply_surface_manifest_json": str(
                reply_report.get("artifacts", {}).get("latest_telegram_reply_surface_manifest_json", "")
            ),
        },
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_proof_baseline_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_PROOF_MANIFEST,
            payload,
        )
    return payload


def build_telegram_request_routing_contract(
    workspace_dir: str | Path,
    *,
    message_text: str,
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    normalized_text = str(message_text).strip()
    lowered = normalized_text.lower()
    extracted_url = _extract_first_url(normalized_text)
    allowed_chat_ids = list(config.get("allowed_chat_ids") or [])
    chat_allowed = is_telegram_chat_allowed(chat_id, allowed_chat_ids)

    intent = "search_query"
    target_surface = "web_access"
    selected_path = "internal_web_access"
    command_input: dict[str, object] = {"query": normalized_text}
    routing_reason = "default_search_query"
    if _is_direct_greeting(normalized_text):
        intent = "direct_reply"
        target_surface = "managed_session"
        selected_path = "direct_agentos_reply"
        command_input = {"text": normalized_text}
        routing_reason = "direct_greeting"
    elif extracted_url:
        intent = "fetch_page"
        command_input = {"url": extracted_url}
        routing_reason = "url_detected"
    elif lowered.startswith("summarize "):
        intent = "summarize_result"
        target_surface = "managed_session"
        selected_path = "internal_summary_flow"
        command_input = {"query": normalized_text}
        routing_reason = "summary_prefix"
    elif lowered.startswith("search ") or lowered.startswith("find ") or lowered.startswith("look up "):
        intent = "search_query"
        routing_reason = "search_prefix"

    if not normalized_text:
        selected_path = ""
        target_surface = ""
        routing_reason = "empty_message"

    request_identifier = str(request_id).strip() or str(message_id).strip() or "telegram-request-pending"
    request_routed = bool(normalized_text and chat_allowed)
    payload = {
        "schema_version": TELEGRAM_ROUTING_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_request_routing_contract",
        "telegram_ingress_received": bool(normalized_text),
        "telegram_chat_allowed": bool(chat_allowed),
        "telegram_request_id": request_identifier,
        "telegram_message_id": str(message_id).strip(),
        "telegram_chat_id": str(chat_id).strip(),
        "telegram_request_routed": request_routed,
        "selected_intent": intent if normalized_text else "",
        "selected_path": selected_path,
        "target_surface": target_surface,
        "routing_reason": routing_reason,
        "browser_escalation_allowed": True,
        "browser_escalation_used": False,
        "escalation_reason": "",
        "routing_candidates": [
            {"intent": "search_query", "target_surface": "web_access", "selected_path": "internal_web_access"},
            {"intent": "fetch_page", "target_surface": "web_access", "selected_path": "internal_web_access"},
            {"intent": "summarize_result", "target_surface": "managed_session", "selected_path": "internal_summary_flow"},
            {"intent": "direct_reply", "target_surface": "managed_session", "selected_path": "direct_agentos_reply"},
        ],
        "request": {
            "text": normalized_text,
            "command_input": command_input,
            "dedupe_key": request_identifier,
            "idempotency_key": request_identifier,
        },
        "proof": {
            "ok": bool(normalized_text and chat_allowed),
            "native_path_default": True,
            "native_path": "internal_web_access",
            "fallback_path": "browser_escalation",
            "allowed_chat_ids": allowed_chat_ids,
            "session_id": str(session_id).strip(),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_request_routing_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_ROUTING_MANIFEST,
            payload,
        )
    return payload


def _build_telegram_search_url(query: str) -> str:
    normalized_query = str(query).strip()
    lowered = normalized_query.lower()
    for prefix in ("search ", "find ", "look up "):
        if lowered.startswith(prefix):
            normalized_query = normalized_query[len(prefix) :].strip()
            break
    if not normalized_query:
        return ""
    return "https://duckduckgo.com/html/?q=" + quote_plus(normalized_query)


def _is_direct_greeting(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text).strip().lower())
    normalized = normalized.strip("!.?~")
    return normalized in {
        "hi",
        "hello",
        "hey",
        "yo",
        "안녕",
        "안녕하세요",
        "ㅎㅇ",
        "하이",
    }


def _direct_greeting_reply() -> str:
    return (
        "Hi! AgentOS is online.\n"
        "Try: search AgentOS roadmap and summarize it"
    )


def build_telegram_web_execution_report(
    workspace_dir: str | Path,
    *,
    message_text: str = "",
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    routing_report: dict | None = None,
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    if routing_report is None:
        routing_report = build_telegram_request_routing_contract(
            workspace,
            message_text=message_text,
            chat_id=chat_id,
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            write_manifest=False,
        )
    elif not isinstance(routing_report, dict):
        routing_report = {}
    else:
        routing_report = dict(routing_report)

    selected_intent = str(routing_report.get("selected_intent", ""))
    selected_path = str(routing_report.get("selected_path", ""))
    request_identifier = str(routing_report.get("telegram_request_id", "")) or str(request_id).strip() or str(message_id).strip() or "telegram-request-pending"
    request_routed = bool(routing_report.get("telegram_request_routed", False))
    command_input = routing_report.get("request", {}).get("command_input", {})
    if not isinstance(command_input, dict):
        command_input = {}
    else:
        command_input = dict(command_input)
    execution_url = ""
    if selected_intent == "fetch_page":
        execution_url = str(command_input.get("url", "")).strip()
    elif selected_intent == "search_query":
        execution_url = _build_telegram_search_url(str(command_input.get("query", "")))
    payload = {
        "schema_version": TELEGRAM_WEB_EXECUTION_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_web_execution",
        "telegram_request_id": request_identifier,
        "telegram_chat_id": str(routing_report.get("telegram_chat_id", "")),
        "telegram_chat_allowed": bool(routing_report.get("telegram_chat_allowed", False)),
        "telegram_request_routed": bool(routing_report.get("telegram_request_routed", False)),
        "selected_intent": selected_intent,
        "selected_path": selected_path,
        "execution_target": str(routing_report.get("target_surface", "")),
        "execution_url": execution_url,
        "routing_summary": {
            "routing_reason": str(routing_report.get("routing_reason", "")),
            "request_text": str(routing_report.get("request", {}).get("text", "")),
            "command_input": dict(command_input),
            "browser_escalation_allowed": bool(routing_report.get("browser_escalation_allowed", False)),
        },
        "native_path_default": True,
        "native_handled": False,
        "escalated_handled": False,
        "browser_escalation_used": False,
        "browser_escalation_allowed": False,
        "browser_escalation_required": False,
        "browser_escalation_reason": "",
        "browser_fallback_contract": {
            "fallback_target": "browser_escalated",
            "allowed_reasons": list(TELEGRAM_BROWSER_FALLBACK_REASONS),
            "silent_native_replacement_allowed": False,
        },
        "unsupported_or_deferred": False,
        "mediation_cost": "deferred",
        "proof": {
            "ok": False,
            "native_path": "internal_web_access",
            "execution_selected": False,
            "session_id": str(session_id).strip(),
        },
        "execution_artifacts": {},
        "artifacts": {},
    }

    if not request_routed:
        payload["unsupported_or_deferred"] = True
        payload["proof"]["reason"] = "routing_rejected"
        if write_manifest:
            payload["artifacts"]["latest_telegram_web_execution_manifest_json"] = _write_manifest(
                workspace,
                TELEGRAM_WEB_EXECUTION_MANIFEST,
                payload,
            )
        return payload

    if selected_intent == "direct_reply":
        payload["execution_target"] = "direct_agentos_reply"
        payload["native_handled"] = True
        payload["unsupported_or_deferred"] = False
        payload["mediation_cost"] = "none"
        payload["proof"]["ok"] = True
        payload["proof"]["execution_selected"] = True
        payload["proof"]["text_preview"] = _direct_greeting_reply()
        payload["execution_artifacts"]["direct_reply"] = {
            "reply_kind": "greeting",
            "handled_without_web_search": True,
        }
        if write_manifest:
            payload["artifacts"]["latest_telegram_web_execution_manifest_json"] = _write_manifest(
                workspace,
                TELEGRAM_WEB_EXECUTION_MANIFEST,
                payload,
            )
        return payload

    if selected_path != "internal_web_access":
        payload["unsupported_or_deferred"] = True
        payload["proof"]["reason"] = "non_web_execution_path"
        payload["execution_target"] = "internal_summary_flow"
        if write_manifest:
            payload["artifacts"]["latest_telegram_web_execution_manifest_json"] = _write_manifest(
                workspace,
                TELEGRAM_WEB_EXECUTION_MANIFEST,
                payload,
            )
        return payload

    if not execution_url:
        payload["unsupported_or_deferred"] = True
        payload["proof"]["reason"] = "missing_execution_input"
        if write_manifest:
            payload["artifacts"]["latest_telegram_web_execution_manifest_json"] = _write_manifest(
                workspace,
                TELEGRAM_WEB_EXECUTION_MANIFEST,
                payload,
            )
        return payload

    execution_payload = build_web_access_report(
        workspace,
        execution_url,
        domain_allowlist=domain_allowlist,
        write_manifest=False,
    )
    payload["proof"]["execution_selected"] = True
    payload["proof"]["content_type"] = str(execution_payload.get("proof", {}).get("content_type", ""))
    payload["proof"]["document_class"] = str(execution_payload.get("document_class", ""))
    payload["proof"]["text_preview"] = str(execution_payload.get("proof", {}).get("text_preview", ""))
    payload["execution_artifacts"]["web_access"] = execution_payload
    payload["native_handled"] = bool(execution_payload.get("native_handled", False))
    payload["escalated_handled"] = bool(execution_payload.get("escalated_handled", False))
    payload["browser_escalation_used"] = bool(execution_payload.get("escalated_handled", False))
    payload["browser_escalation_reason"] = str(execution_payload.get("escalation_reason", ""))
    payload["browser_escalation_allowed"] = payload["browser_escalation_reason"] in TELEGRAM_BROWSER_FALLBACK_REASONS
    payload["browser_escalation_required"] = bool(payload["browser_escalation_used"] and payload["browser_escalation_allowed"])
    payload["unsupported_or_deferred"] = bool(execution_payload.get("unsupported_or_deferred", False))
    payload["mediation_cost"] = (
        "low" if payload["native_handled"] else ("medium" if payload["escalated_handled"] else "deferred")
    )
    payload["proof"]["ok"] = bool(payload["native_handled"])
    if not payload["proof"]["ok"]:
        if payload["browser_escalation_required"]:
            payload["proof"]["reason"] = f"browser_escalation_required:{payload['browser_escalation_reason']}"
        else:
            payload["proof"]["reason"] = "execution_deferred"
    payload["proof"]["browser_escalation_allowed"] = payload["browser_escalation_allowed"]
    payload["proof"]["browser_escalation_required"] = payload["browser_escalation_required"]
    payload["proof"]["browser_escalation_reason"] = payload["browser_escalation_reason"]

    if write_manifest:
        payload["artifacts"]["latest_telegram_web_execution_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_WEB_EXECUTION_MANIFEST,
            payload,
        )
    return payload


def _build_telegram_reply_text(execution_report: dict) -> str:
    intent = str(execution_report.get("selected_intent", "")).strip()
    execution_url = str(execution_report.get("execution_url", "")).strip()
    preview = str(execution_report.get("proof", {}).get("text_preview", "")).strip()
    preview = _trim_output(preview).replace("\n", " ").strip()
    if intent == "direct_reply":
        return _direct_greeting_reply()
    if execution_report.get("native_handled", False):
        prefix = "AgentOS search result" if intent == "search_query" else "AgentOS page fetch result"
        lines = [prefix + " (native web)"]
        if preview:
            lines.append(preview)
        if execution_url:
            lines.append(f"Source: {execution_url}")
        return "\n".join(lines)
    if execution_report.get("browser_escalation_required", False):
        reason = str(execution_report.get("browser_escalation_reason", "")).strip() or "browser_fallback_required"
        return (
            "AgentOS needs browser fallback for this request.\n"
            f"Reason: {reason}\n"
            f"Target: {execution_url or '(unspecified)'}"
        )
    return "AgentOS could not complete this Telegram request through the built-in web path yet."


def build_telegram_reply_surface_report(
    workspace_dir: str | Path,
    *,
    message_text: str = "",
    chat_id: str = "",
    request_id: str = "",
    message_id: str = "",
    session_id: str = "",
    send_reply: bool = False,
    routing_report: dict | None = None,
    execution_report: dict | None = None,
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    if routing_report is None:
        routing_report = build_telegram_request_routing_contract(
            workspace,
            message_text=message_text,
            chat_id=chat_id,
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            write_manifest=False,
        )
    if execution_report is None:
        execution_report = build_telegram_web_execution_report(
            workspace,
            message_text=message_text,
            chat_id=chat_id,
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            routing_report=routing_report,
            domain_allowlist=domain_allowlist,
            write_manifest=False,
        )

    request_identifier = str(routing_report.get("telegram_request_id", "")).strip() or str(request_id).strip() or "telegram-request-pending"
    target_chat_id = str(routing_report.get("telegram_chat_id", "")).strip() or str(chat_id).strip()
    reply_text = _build_telegram_reply_text(execution_report)
    reply_ready = bool(routing_report.get("telegram_request_routed", False) and target_chat_id and reply_text)
    payload = {
        "schema_version": TELEGRAM_REPLY_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_reply_surface",
        "telegram_request_id": request_identifier,
        "telegram_chat_id": target_chat_id,
        "reply_ready": reply_ready,
        "reply_text": reply_text,
        "reply_mode": "dry_run",
        "reply_sent": False,
        "send_attempted": False,
        "reply_transport": "telegram_bot_send_message",
        "reply_source_path": "native_web_access" if execution_report.get("native_handled", False) else "degraded_reply_surface",
        "execution_report": execution_report,
        "transport": {
            "api_base_url": str(config.get("api_base_url", "https://api.telegram.org")).rstrip("/"),
            "bot_token_configured": bool(config.get("bot_token_configured", False)),
        },
        "proof": {
            "ok": bool(reply_ready),
            "send_ok": False,
            "session_id": str(session_id).strip(),
        },
        "artifacts": {},
    }

    if send_reply and reply_ready and bool(config.get("bot_token_configured", False)):
        payload["send_attempted"] = True
        payload["reply_mode"] = "send_message"
        token_value = str(config.get("bot_token_value", "")).strip()
        if token_value:
            send_url = str(config.get("api_base_url", "https://api.telegram.org")).rstrip("/") + f"/bot{token_value}/sendMessage"
            try:
                status_code, send_payload = _post_json(
                    send_url,
                    {
                        "chat_id": target_chat_id,
                        "text": reply_text,
                        "disable_web_page_preview": True,
                    },
                )
                payload["reply_sent"] = bool(send_payload.get("ok", False)) if isinstance(send_payload, dict) else status_code < 400
                payload["transport"]["status_code"] = status_code
                payload["transport"]["response"] = send_payload
                payload["proof"]["send_ok"] = payload["reply_sent"]
                if not payload["reply_sent"]:
                    payload["proof"]["reason"] = "telegram_send_failed"
            except Exception as exc:
                payload["transport"]["error"] = str(exc)
                payload["proof"]["reason"] = f"telegram_send_failed:{exc}"
        else:
            payload["proof"]["reason"] = "telegram_bot_token_missing"
    elif send_reply and not bool(config.get("bot_token_configured", False)):
        payload["send_attempted"] = True
        payload["reply_mode"] = "send_message"
        payload["proof"]["reason"] = "telegram_bot_token_missing"

    if not payload["reply_ready"]:
        payload["proof"]["reason"] = "reply_not_ready"

    if write_manifest:
        payload["artifacts"]["latest_telegram_reply_surface_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_REPLY_MANIFEST,
            payload,
        )
    return payload


def _write_manifest(workspace_dir: str | Path, name: str, payload: dict) -> str:
    path = _manifest_path(workspace_dir, name)
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(path)


def _read_manifest(workspace_dir: str | Path, name: str) -> dict:
    path = _manifest_path(workspace_dir, name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_telegram_update(update: dict) -> dict:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    if not message:
        message = update.get("edited_message") if isinstance(update.get("edited_message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    text = str(message.get("text", "") or "").strip()
    update_id = str(update.get("update_id", "")).strip()
    message_id = str(message.get("message_id", "")).strip()
    chat_id = str(chat.get("id", "")).strip()
    return {
        "update_id": update_id,
        "message_id": message_id,
        "chat_id": chat_id,
        "text": text,
        "date": message.get("date", ""),
    }


def build_telegram_live_loop_report(
    workspace_dir: str | Path,
    *,
    once: bool = True,
    send_reply: bool = False,
    session_id: str = "",
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    from kernel.intent_dispatch import build_intent_dispatch_report

    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    offset_state = _read_manifest(workspace, TELEGRAM_LIVE_LOOP_OFFSET)
    last_update_id = str(offset_state.get("last_update_id", "")).strip()
    next_offset = int(last_update_id) + 1 if last_update_id.isdigit() else None
    token_value = str(config.get("bot_token_value", "")).strip()
    api_base_url = str(config.get("api_base_url", "https://api.telegram.org")).rstrip("/")
    allowed_chat_ids = list(config.get("allowed_chat_ids") or [])

    payload = {
        "schema_version": TELEGRAM_LIVE_LOOP_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_live_loop",
        "loop_mode": "once" if once else "continuous",
        "transport": {
            "mode": str(config.get("transport", "polling")),
            "mode_source": str(config.get("transport_source", "default")),
            "api_base_url": api_base_url,
            "bot_token_configured": bool(config.get("bot_token_configured", False)),
            "allowed_chat_configured": bool(allowed_chat_ids),
            "telegram_secret_source": str(config.get("telegram_secret_source", "none")),
            "webhook_clear_attempted": False,
            "webhook_clear_ok": False,
        },
        "telegram_polling_attempted": False,
        "telegram_live_update_received": False,
        "telegram_chat_rejected": False,
        "telegram_live_message_routed": False,
        "telegram_live_search_success": False,
        "telegram_reply_sent": False,
        "telegram_update_offset_persisted": False,
        "telegram_update": {},
        "intent_dispatch": {},
        "research_brief": {},
        "reply": {},
        "proof": {
            "ok": False,
            "session_id": str(session_id).strip(),
            "reason": "",
        },
        "summary": {},
        "artifacts": {},
    }

    if not bool(config.get("bot_token_configured", False)) or not token_value:
        payload["proof"]["reason"] = "telegram_token_missing"
    elif str(config.get("transport", "polling")) == "webhook":
        payload["proof"]["reason"] = "telegram_webhook_transport_active"
    elif not bool(config.get("polling_enabled", True)):
        payload["proof"]["reason"] = "telegram_polling_unavailable"
    else:
        payload["telegram_polling_attempted"] = True
        query = {"limit": 1, "timeout": 0}
        if next_offset is not None:
            query["offset"] = next_offset
        poll_url = f"{api_base_url}/bot{token_value}/getUpdates?{urlencode(query)}"
        try:
            try:
                status_code, poll_payload = _get_json(poll_url)
            except Exception as exc:
                if not _looks_like_telegram_polling_conflict(exc):
                    raise
                payload["transport"]["poll_conflict_detected"] = True
                payload["transport"]["webhook_active"] = True
                payload["proof"]["reason"] = "telegram_webhook_active"
                poll_payload = {"ok": False, "result": []}
                status_code = 409
            payload["transport"]["poll_status_code"] = status_code
            updates = poll_payload.get("result", []) if isinstance(poll_payload, dict) else []
            if payload["proof"].get("reason") == "telegram_webhook_active":
                pass
            elif not bool(poll_payload.get("ok", False)) if isinstance(poll_payload, dict) else status_code >= 400:
                payload["proof"]["reason"] = "telegram_polling_unavailable"
            elif not updates:
                payload["proof"]["reason"] = "telegram_live_update_timeout"
            else:
                update = _normalize_telegram_update(updates[0] if isinstance(updates[0], dict) else {})
                payload["telegram_update"] = update
                payload["telegram_live_update_received"] = bool(update.get("update_id") and update.get("chat_id") and update.get("text"))
                if update.get("update_id"):
                    offset_payload = {
                        "schema_version": "agentos-telegram-live-loop-offset.v1",
                        "updated_at_utc": _utc_now(),
                        "last_update_id": update.get("update_id", ""),
                    }
                    if write_manifest:
                        payload["artifacts"]["latest_telegram_live_loop_offset_json"] = _write_manifest(
                            workspace,
                            TELEGRAM_LIVE_LOOP_OFFSET,
                            offset_payload,
                        )
                        offset_path = Path(payload["artifacts"]["latest_telegram_live_loop_offset_json"])
                        payload["telegram_update_offset_persisted"] = offset_path.is_file() and offset_path.stat().st_size > 0
                if not payload["telegram_live_update_received"]:
                    payload["proof"]["reason"] = "telegram_live_update_timeout"
                elif not is_telegram_chat_allowed(str(update.get("chat_id", "")), allowed_chat_ids):
                    payload["telegram_chat_rejected"] = True
                    payload["proof"]["reason"] = "telegram_chat_rejected"
                else:
                    request_id = f"telegram-live-{update.get('update_id')}"
                    dispatch = build_intent_dispatch_report(
                        workspace,
                        source="telegram",
                        message_text=str(update.get("text", "")),
                        chat_id=str(update.get("chat_id", "")),
                        request_id=request_id,
                        message_id=str(update.get("message_id", "")),
                        session_id=session_id,
                        send_reply=send_reply,
                        domain_allowlist=domain_allowlist,
                        write_manifest=write_manifest,
                    )
                    brief = dict(dispatch.get("research_brief") or {})
                    payload["intent_dispatch"] = dispatch
                    payload["research_brief"] = brief
                    reply = dict(brief.get("research_workflow", {}).get("reply_report") or {})
                    payload["reply"] = reply
                    payload["telegram_live_message_routed"] = bool(dispatch.get("proof", {}).get("ok", False))
                    payload["telegram_live_search_success"] = bool(dispatch.get("web_search_used", False) and brief.get("internal_web_query_success", False))
                    payload["telegram_reply_sent"] = bool(dispatch.get("telegram_reply_sent", False))
                    if not payload["telegram_live_message_routed"]:
                        payload["proof"]["reason"] = str(dispatch.get("proof", {}).get("reason", "")) or "telegram_message_routing_failure"
                    elif dispatch.get("web_search_used", False) and not payload["telegram_live_search_success"]:
                        payload["proof"]["reason"] = "internal_web_query_failure"
                    elif send_reply and not payload["telegram_reply_sent"]:
                        payload["proof"]["reason"] = "telegram_send_failure"
                    else:
                        payload["proof"]["ok"] = True
        except Exception as exc:
            payload["proof"]["reason"] = f"telegram_polling_unavailable:{exc}"

    if not payload["proof"].get("reason"):
        if not payload["telegram_polling_attempted"]:
            payload["proof"]["reason"] = "telegram_polling_unavailable"
        elif not payload["telegram_live_update_received"]:
            payload["proof"]["reason"] = "telegram_live_update_timeout"

    payload["summary"] = {
        "telegram_polling_attempted": bool(payload["telegram_polling_attempted"]),
        "telegram_live_update_received": bool(payload["telegram_live_update_received"]),
        "telegram_chat_rejected": bool(payload["telegram_chat_rejected"]),
        "telegram_live_message_routed": bool(payload["telegram_live_message_routed"]),
        "telegram_live_search_success": bool(payload["telegram_live_search_success"]),
        "telegram_reply_sent": bool(payload["telegram_reply_sent"]),
        "telegram_update_offset_persisted": bool(payload["telegram_update_offset_persisted"]),
        "failure_class": "" if payload["proof"].get("ok", False) else str(payload["proof"].get("reason", "")),
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_live_loop_manifest_json"] = _write_manifest(
            workspace,
            TELEGRAM_LIVE_LOOP_MANIFEST,
            payload,
        )
    return payload


def _workspace_document_probe_path(workspace_dir: str | Path) -> str:
    workspace = Path(workspace_dir).resolve()
    for candidate in ("spec.yaml", "README.md", "docs/index.md", "docs/README.md"):
        if (workspace / candidate).is_file():
            return candidate
    return "spec.yaml"


def _trim_output(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text)} chars total]"


def _decode_text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _extract_html_text(raw: bytes) -> str:
    if _BS4_AVAILABLE:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    text = _decode_text(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _classify_document_class(path: Path, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix in {".html", ".htm"}:
        return "html"
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed == "text/markdown":
        return "markdown"
    if guessed == "application/json":
        return "json"
    if guessed == "text/html":
        return "html"
    if guessed and guessed.startswith("text/"):
        return "text"
    if b"\x00" in raw:
        return "binary"
    try:
        raw.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def _extract_document_text(document_class: str, raw: bytes) -> str:
    if document_class == "html":
        return _extract_html_text(raw)
    return _decode_text(raw).strip()


def build_document_access_report(
    workspace_dir: str | Path,
    user_path: str,
    *,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    payload = {
        "schema_version": DOCUMENT_ACCESS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "document",
        "capability": "document_access",
        "requested_path": str(user_path),
        "resolved_path": "",
        "document_class": "",
        "native_path_default": True,
        "native_handled": False,
        "escalated_handled": False,
        "escalation_reason": "",
        "unsupported_or_deferred": False,
        "mediation_cost": "low",
        "proof": {},
        "artifacts": {},
    }
    try:
        target = safe_path(workspace, user_path)
    except ValueError as exc:
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"] = {"ok": False, "reason": str(exc)}
        if write_manifest:
            payload["artifacts"]["latest_document_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-document-access.json",
                payload,
            )
        return payload

    payload["resolved_path"] = str(target)
    if not target.exists() or not target.is_file():
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"] = {"ok": False, "reason": "file_not_found"}
        if write_manifest:
            payload["artifacts"]["latest_document_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-document-access.json",
                payload,
            )
        return payload

    raw = target.read_bytes()[:_MAX_READ_BYTES]
    document_class = _classify_document_class(target, raw)
    text = _extract_document_text(document_class, raw) if document_class in SUPPORTED_DOCUMENT_CLASSES else ""
    native_handled = document_class in SUPPORTED_DOCUMENT_CLASSES
    payload.update(
        {
            "document_class": document_class,
            "native_handled": native_handled,
            "unsupported_or_deferred": not native_handled,
            "mediation_cost": "low" if native_handled else "deferred",
            "proof": {
                "ok": native_handled,
                "document_classes_supported": list(SUPPORTED_DOCUMENT_CLASSES),
                "compatibility_tools": ["file_read"],
                "document_bytes_read": len(raw),
                "text_preview": _trim_output(text) if text else "",
            },
        }
    )
    if write_manifest:
        payload["artifacts"]["latest_document_access_manifest_json"] = _write_manifest(
            workspace,
            "latest-document-access.json",
            payload,
        )
    return payload


def _host_matches_rule(host: str, rule: str) -> bool:
    if host == rule:
        return True
    return host.endswith("." + rule)


def _validate_web_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "invalid_url"
    if parsed.scheme not in ("http", "https"):
        return False, "unsupported_scheme"
    if not (parsed.hostname or "").strip():
        return False, "invalid_host"
    return True, ""


def _html_needs_browser(raw: bytes) -> bool:
    text = _decode_text(raw).lower()
    script_count = text.count("<script")
    if script_count >= 8:
        return True
    if 'type="password"' in text or "g-recaptcha" in text:
        return True
    if "application/json" in text and "__next_data__" in text:
        return True
    return False


def build_web_access_report(
    workspace_dir: str | Path,
    url: str,
    *,
    domain_allowlist: list[str] | None = None,
    requires_authentication: bool = False,
    interactive: bool = False,
    compatibility_required: bool = False,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    payload = {
        "schema_version": WEB_ACCESS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "web",
        "capability": "web_access",
        "url": str(url),
        "native_path_default": True,
        "native_handled": False,
        "escalated_handled": False,
        "escalation_reason": "",
        "unsupported_or_deferred": False,
        "mediation_cost": "medium",
        "document_class": "",
        "proof": {
            "supported_page_classes": ["public_document_like_html", "plain_text", "json"],
            "unsupported_page_classes": ["authenticated", "interactive", "js_heavy", "compatibility_required"],
            "browser_escalation_reasons": list(ESCALATION_REASONS),
        },
        "artifacts": {},
    }
    ok, reason = _validate_web_url(url)
    if not ok:
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"]["ok"] = False
        payload["proof"]["reason"] = reason
        if write_manifest:
            payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-web-access.json",
                payload,
            )
        return payload

    host = (urlparse(url).hostname or "").lower()
    if domain_allowlist:
        allowed = any(_host_matches_rule(host, rule) for rule in domain_allowlist)
        if not allowed:
            payload["unsupported_or_deferred"] = True
            payload["mediation_cost"] = "deferred"
            payload["proof"]["ok"] = False
            payload["proof"]["reason"] = "domain_not_allowed"
            if write_manifest:
                payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                    workspace,
                    "latest-web-access.json",
                    payload,
                )
            return payload

    escalation_reason = ""
    if requires_authentication:
        escalation_reason = "requires_authentication"
    elif interactive:
        escalation_reason = "interactive_or_js_heavy"
    elif compatibility_required:
        escalation_reason = "compatibility_required"
    if escalation_reason:
        payload["escalated_handled"] = True
        payload["escalation_reason"] = escalation_reason
        payload["proof"]["ok"] = True
        payload["proof"]["selected_path"] = "browser_escalated"
        if write_manifest:
            payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-web-access.json",
                payload,
            )
        return payload

    try:
        raw, content_type = _fetch_web_payload(url)
    except (TimeoutError, urllib_error.URLError):
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"]["ok"] = False
        payload["proof"]["reason"] = "request_timed_out"
        if write_manifest:
            payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-web-access.json",
                payload,
            )
        return payload
    except Exception as exc:
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"]["ok"] = False
        payload["proof"]["reason"] = f"fetch_failed:{exc}"
        if write_manifest:
            payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                workspace,
                "latest-web-access.json",
                payload,
            )
        return payload

    if "html" in content_type:
        document_class = "html"
        if _html_needs_browser(raw):
            payload["escalated_handled"] = True
            payload["escalation_reason"] = "interactive_or_js_heavy"
            payload["proof"]["ok"] = True
            payload["proof"]["selected_path"] = "browser_escalated"
            payload["proof"]["content_type"] = content_type
            if write_manifest:
                payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
                    workspace,
                    "latest-web-access.json",
                    payload,
                )
            return payload
        text = _extract_html_text(raw)
    elif "json" in content_type:
        document_class = "json"
        text = _decode_text(raw).strip()
    else:
        document_class = "text"
        text = _decode_text(raw).strip()

    payload.update(
        {
            "document_class": document_class,
            "native_handled": True,
            "mediation_cost": "low",
        }
    )
    payload["proof"].update(
        {
            "ok": True,
            "selected_path": "native_fetch_parse",
            "content_type": content_type,
            "text_preview": _trim_output(text),
        }
    )
    if write_manifest:
        payload["artifacts"]["latest_web_access_manifest_json"] = _write_manifest(
            workspace,
            "latest-web-access.json",
            payload,
        )
    return payload


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _intake_kind_for_event(event: dict) -> str:
    source = str(event.get("source", "")).strip().lower()
    kind = str(event.get("kind", "")).strip().lower()
    if source == "manual":
        return "manual_intake"
    if "approval" in kind or source == "broker":
        return "operator_intake"
    return "event_intake"


def _visibility_state(correlation: dict) -> str:
    if any(str(correlation.get(key, "")).strip() for key in ("session_id", "request_id", "approval_id", "trace_id")):
        return "session_correlated"
    return "visible_unlinked"


def _mediation_cost_for_intake(item: dict) -> str:
    kind = str(item.get("intake_kind", "")).strip()
    if kind == "feedback_intake":
        return "medium"
    if kind == "operator_intake":
        return "medium"
    return "low"


def _first_nonempty(values: list[str]) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def ensure_inbox_fixture(workspace_dir: str | Path, fixture_path: str = DEFAULT_INBOX_FIXTURE_PATH) -> str:
    workspace = Path(workspace_dir).resolve()
    target = workspace / fixture_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        payload = {
            "messages": [
                {
                    "message_id": "<agentos-fixture-root@example.local>",
                    "thread_id": "<agentos-fixture-root@example.local>",
                    "subject": "AgentOS inbox fixture root",
                    "from": "agentos@example.local",
                    "to": ["operator@example.local"],
                    "timestamp_utc": "2026-04-21T00:00:00Z",
                    "source_ref": "fixture:root",
                    "attachment_metadata": [],
                    "body_preview": "Fixture root message for the Window 9 inbox capability baseline.",
                },
                {
                    "message_id": "<agentos-fixture-reply@example.local>",
                    "thread_id": "<agentos-fixture-root@example.local>",
                    "subject": "Re: AgentOS inbox fixture root",
                    "from": "operator@example.local",
                    "to": ["agentos@example.local"],
                    "timestamp_utc": "2026-04-21T00:01:00Z",
                    "source_ref": "fixture:reply",
                    "attachment_metadata": [
                        {
                            "filename": "notes.txt",
                            "content_type": "text/plain",
                            "size_bytes": 18,
                        }
                    ],
                    "body_preview": "Reply fixture message with one attachment metadata record.",
                },
            ]
        }
        target.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(target.relative_to(workspace))


def _attachment_metadata_from_message(message) -> list[dict]:
    attachments: list[dict] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if not filename and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "filename": filename or "",
                "content_type": str(part.get_content_type() or ""),
                "size_bytes": len(payload),
            }
        )
    return attachments


def _body_preview_from_message(message) -> str:
    previews: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = str(part.get_content_type() or "")
        if content_type.startswith("text/"):
            try:
                text = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            normalized = str(text or "").strip()
            if normalized:
                previews.append(normalized)
    return _trim_output("\n".join(previews))


def _normalize_fixture_message(message: dict, index: int) -> dict:
    message_id = _first_nonempty([str(message.get("message_id", "")), f"fixture-message-{index}"])
    thread_id = _first_nonempty([str(message.get("thread_id", "")), message_id])
    attachments = list(message.get("attachment_metadata") or [])
    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "subject": str(message.get("subject", "")).strip(),
        "from": str(message.get("from", "")).strip(),
        "to": [str(item).strip() for item in (message.get("to") or []) if str(item).strip()],
        "timestamp_utc": str(message.get("timestamp_utc", "")).strip(),
        "source_ref": _first_nonempty([str(message.get("source_ref", "")), f"fixture:{index}"]),
        "attachment_metadata": attachments,
        "attachment_count": len(attachments),
        "body_preview": _trim_output(str(message.get("body_preview", "")).strip()),
    }


def _load_fixture_messages(target: Path) -> list[dict]:
    payload = _read_json(target)
    messages = []
    for index, item in enumerate(payload.get("messages") or [], start=1):
        if not isinstance(item, dict):
            continue
        messages.append(_normalize_fixture_message(item, index))
    return messages


def _normalize_maildir_message(key: str, maildir_message, source_ref: str) -> dict:
    message_id = _first_nonempty([maildir_message.get("Message-ID", ""), key])
    references = str(maildir_message.get("References", "")).split()
    thread_id = _first_nonempty(
        [
            maildir_message.get("In-Reply-To", ""),
            references[0] if references else "",
            message_id,
        ]
    )
    to_header = str(maildir_message.get("To", "")).strip()
    recipients = [item.strip() for item in to_header.split(",") if item.strip()]
    attachments = _attachment_metadata_from_message(maildir_message)
    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "subject": str(maildir_message.get("Subject", "")).strip(),
        "from": str(maildir_message.get("From", "")).strip(),
        "to": recipients,
        "timestamp_utc": "",
        "source_ref": source_ref,
        "attachment_metadata": attachments,
        "attachment_count": len(attachments),
        "body_preview": _body_preview_from_message(maildir_message),
    }


def _load_maildir_messages(target: Path) -> list[dict]:
    parser = BytesParser(policy=policy.default)
    box = mailbox.Maildir(str(target), factory=None, create=False)
    messages: list[dict] = []
    for key in box.iterkeys():
        raw = box.get_bytes(key)
        if raw is None:
            continue
        parsed = parser.parsebytes(raw)
        subpath = ""
        for folder in ("cur", "new"):
            candidate = target / folder
            for item in candidate.iterdir() if candidate.exists() else []:
                if item.name.startswith(str(key)):
                    subpath = str(item.relative_to(target.parent))
                    break
            if subpath:
                break
        messages.append(_normalize_maildir_message(str(key), parsed, subpath or f"{target.name}:{key}"))
    return messages


def _normalize_inbox_message_intake_item(message: dict, *, path_kind: str, source_kind: str, correlation: dict) -> dict:
    return {
        "intake_id": f"message:{str(message.get('message_id', '')).strip()}",
        "intake_kind": "message_intake",
        "path_kind": path_kind,
        "source_kind": source_kind,
        "message_id": str(message.get("message_id", "")).strip(),
        "thread_id": str(message.get("thread_id", "")).strip(),
        "source_ref": str(message.get("source_ref", "")).strip(),
        "subject": str(message.get("subject", "")).strip(),
        "from": str(message.get("from", "")).strip(),
        "to": list(message.get("to") or []),
        "timestamp_utc": str(message.get("timestamp_utc", "")).strip(),
        "body_preview": str(message.get("body_preview", "")).strip(),
        "attachment_metadata": list(message.get("attachment_metadata") or []),
        "attachment_count": int(message.get("attachment_count", 0) or 0),
        "correlation": dict(correlation),
    }


def _session_correlation_context(workspace: Path, session_id: str) -> tuple[dict, dict]:
    timeline = query_session_timeline(workspace, session_id=session_id, limit=50)
    evidence = dict(timeline.get("correlation_evidence") or {})
    request_ids = [str(item).strip() for item in evidence.get("request_ids") or [] if str(item).strip()]
    approval_ids = [str(item).strip() for item in evidence.get("approval_ids") or [] if str(item).strip()]
    boot_ids = [str(item).strip() for item in evidence.get("boot_ids") or [] if str(item).strip()]
    correlation = {
        "session_id": str(session_id or evidence.get("session_id", "")).strip(),
        "request_id": request_ids[-1] if request_ids else "",
        "approval_id": approval_ids[-1] if approval_ids else "",
        "trace_id": "",
        "run_id": "",
        "boot_id": boot_ids[-1] if boot_ids else "",
    }
    return correlation, {
        "correlation_evidence": evidence,
        "ownership_summary": dict(timeline.get("ownership_summary") or {}),
        "timeline_events": int(timeline.get("returned_events", 0) or 0),
    }


def build_inbox_capability_report(
    workspace_dir: str | Path,
    *,
    fixture_path: str = DEFAULT_INBOX_FIXTURE_PATH,
    maildir_path: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    correlation, session_context = _session_correlation_context(workspace, str(session_id).strip())
    payload = {
        "schema_version": INBOX_CAPABILITY_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "inbox",
        "capability": "inbox_capability",
        "message_capability": "message_capability",
        "thread_capability": "thread_capability",
        "attachment_capability": "attachment_capability",
        "native_inbox_path": "",
        "inbox_adapter_path": "",
        "native_inbox_handled": False,
        "inbox_adapter_required": False,
        "message_thread_correlated": False,
        "attachment_visibility_ok": False,
        "inbox_execution_ready": False,
        "unsupported_or_deferred": False,
        "mediation_cost": "low",
        "messages": [],
        "threads": [],
        "proof": {},
        "session_contract": session_correlation_contract(),
        "correlation": correlation,
        "session_correlation": session_context["correlation_evidence"],
        "ownership_summary": session_context["ownership_summary"],
        "artifacts": {},
    }
    try:
        if maildir_path:
            target = safe_path(workspace, maildir_path)
            payload["native_inbox_path"] = ""
            payload["inbox_adapter_path"] = "maildir"
            payload["inbox_adapter_required"] = True
            payload["mediation_cost"] = "medium"
            if not target.exists():
                raise FileNotFoundError("maildir_not_found")
            if not (target / "cur").is_dir() or not (target / "new").is_dir():
                raise FileNotFoundError("maildir_layout_invalid")
            messages = _load_maildir_messages(target)
            payload["resolved_path"] = str(target)
        else:
            fixture_relpath = ensure_inbox_fixture(workspace, fixture_path)
            target = safe_path(workspace, fixture_relpath)
            payload["native_inbox_path"] = fixture_relpath
            payload["inbox_adapter_path"] = ""
            payload["mediation_cost"] = "low"
            messages = _load_fixture_messages(target)
            payload["resolved_path"] = str(target)
    except (ValueError, FileNotFoundError) as exc:
        payload["unsupported_or_deferred"] = True
        payload["mediation_cost"] = "deferred"
        payload["proof"] = {"ok": False, "reason": str(exc)}
        if write_manifest:
            payload["artifacts"]["latest_inbox_capability_manifest_json"] = _write_manifest(
                workspace,
                "latest-inbox-capability.json",
                payload,
            )
        return payload

    threads: dict[str, dict] = {}
    for message in messages:
        thread_id = str(message.get("thread_id", "")).strip() or str(message.get("message_id", "")).strip()
        thread = threads.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "message_ids": [],
                "subjects": [],
            },
        )
        thread["message_ids"].append(str(message.get("message_id", "")).strip())
        subject = str(message.get("subject", "")).strip()
        if subject and subject not in thread["subjects"]:
            thread["subjects"].append(subject)

    attachment_visibility_ok = all("attachment_metadata" in message for message in messages)
    thread_correlated = bool(messages) and all(str(message.get("thread_id", "")).strip() for message in messages)
    payload.update(
        {
            "messages": messages,
            "threads": list(threads.values()),
            "native_inbox_handled": bool(messages) and not maildir_path,
            "message_thread_correlated": thread_correlated,
            "attachment_visibility_ok": attachment_visibility_ok,
            "inbox_execution_ready": bool(messages),
        }
    )
    message_intake_items = [
        _normalize_inbox_message_intake_item(
            message,
            path_kind="adapter" if maildir_path else "native",
            source_kind="maildir" if maildir_path else "fixture",
            correlation=correlation,
        )
        for message in messages
    ]
    payload["message_intake_items"] = message_intake_items
    payload["proof"] = {
        "ok": bool(messages),
        "message_count": len(messages),
        "thread_count": len(threads),
        "adapter_kind": payload["inbox_adapter_path"] or "native_fixture",
        "message_identity_fields": ["message_id", "thread_id", "subject", "from", "to", "source_ref"],
        "attachment_metadata_fields": ["filename", "content_type", "size_bytes"],
        "session_correlated": bool(correlation.get("session_id", "")),
        "request_correlated": bool(correlation.get("request_id", "")),
        "approval_correlated": bool(correlation.get("approval_id", "")),
    }
    payload["summary"] = {
        "message_count": len(messages),
        "thread_count": len(threads),
        "native_inbox_handled": payload["native_inbox_handled"],
        "inbox_adapter_required": payload["inbox_adapter_required"],
        "message_thread_correlated": payload["message_thread_correlated"],
        "attachment_visibility_ok": payload["attachment_visibility_ok"],
        "inbox_execution_ready": payload["inbox_execution_ready"],
        "message_intake_count": len(message_intake_items),
        "session_correlated": bool(correlation.get("session_id", "")),
        "request_correlated": bool(correlation.get("request_id", "")),
        "approval_correlated": bool(correlation.get("approval_id", "")),
    }
    if write_manifest:
        payload["artifacts"]["latest_inbox_capability_manifest_json"] = _write_manifest(
            workspace,
            "latest-inbox-capability.json",
            payload,
        )
    return payload


def build_inbox_routing_contract(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    native_fixture = ensure_inbox_fixture(workspace)
    payload = {
        "schema_version": INBOX_ROUTING_CONTRACT_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "inbox",
        "capability": "inbox_routing_contract",
        "default_selected_path": "native_inbox_path",
        "paths": [
            {
                "path_id": "native_inbox_path",
                "path_kind": "native",
                "source_kind": "fixture",
                "relative_path": native_fixture,
                "mediation_cost": "low",
                "native_inbox_handled": True,
                "inbox_adapter_required": False,
            },
            {
                "path_id": "inbox_adapter_path",
                "path_kind": "adapter",
                "source_kind": "maildir",
                "relative_path": "<workspace-relative Maildir path>",
                "mediation_cost": "medium",
                "native_inbox_handled": False,
                "inbox_adapter_required": True,
            },
        ],
        "selection_rules": [
            "prefer native_inbox_path when a kernel-owned or workspace-owned inbox fixture is sufficient",
            "select inbox_adapter_path when a real Maildir source is explicitly requested",
            "preserve message_id, thread_id, attachment_metadata, and source_ref on both paths",
        ],
        "proof_fields": [
            "native_inbox_handled",
            "inbox_adapter_required",
            "message_thread_correlated",
            "attachment_visibility_ok",
            "inbox_execution_ready",
        ],
        "session_contract": session_correlation_contract(),
        "correlation": {
            "session_id": str(session_id).strip(),
            "request_id": "",
            "approval_id": "",
            "trace_id": "",
            "run_id": "",
            "boot_id": "",
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_inbox_routing_contract_json"] = _write_manifest(
            workspace,
            "latest-inbox-routing-contract.json",
            payload,
        )
    return payload


def build_verified_boot_attestation_nonclaim(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    payload = {
        "schema_version": VERIFIED_BOOT_ATTESTATION_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "runtime_proof",
        "capability": "verified_boot_attestation_nonclaim",
        "boundary_doc": "docs/architecture/verified-boot-attestation-proof-boundary.md",
        "local_runtime_proof_scope": [
            "runtime_status",
            "intent_dispatch",
            "bounded_capability_execution",
            "activity_and_record_output",
            "cleanup_policy",
        ],
        "trust_surfaces": [
            {
                "id": "secure_boot",
                "status": "not_observed",
                "claim_allowed": False,
                "requires": [
                    "firmware_or_vm_secure_boot_state",
                    "bootloader_or_shim_signature_path",
                    "kernel_or_initramfs_signature_policy",
                ],
            },
            {
                "id": "tpm_measured_boot",
                "status": "not_observed",
                "claim_allowed": False,
                "requires": [
                    "tpm_or_vtpm_available",
                    "boot_event_log",
                    "pcr_values",
                    "event_log_replay_against_pcrs",
                ],
            },
            {
                "id": "linux_ima",
                "status": "not_observed",
                "claim_allowed": False,
                "requires": [
                    "kernel_support_and_boot_parameters",
                    "active_ima_policy",
                    "measurement_appraisal_or_audit_logs",
                    "measurement_vs_appraisal_mode_declared",
                ],
            },
        ],
        "non_claims": {
            "secure_boot_enforced": False,
            "tpm_attestation_completed": False,
            "pcr_event_log_verified": False,
            "ima_appraisal_enforced": False,
            "hardware_backed_attestation_completed": False,
            "docker_runtime_used_as_boot_chain_proof": False,
        },
        "blockers": [
            {
                "id": "secure-boot-observation-required",
                "reason": "Secure Boot status requires observed VM or hardware firmware state evidence.",
                "recovery_action": "Run a VM or hardware proof flow and attach firmware state plus signature-path evidence before claiming Secure Boot.",
            },
            {
                "id": "tpm-pcr-event-log-required",
                "reason": "TPM measured boot requires TPM or vTPM PCR values and a matching boot event log.",
                "recovery_action": "Capture TPM-backed PCR/event-log evidence and verify event-log replay before claiming attestation.",
            },
            {
                "id": "ima-policy-log-required",
                "reason": "Linux IMA proof requires kernel/config, active policy, and measurement/appraisal/audit logs.",
                "recovery_action": "Attach IMA policy and logs, and declare whether AgentOS is measuring only or enforcing appraisal.",
            },
        ],
        "correlation": {
            "session_id": str(session_id).strip(),
            "request_id": "",
            "approval_id": "",
            "trace_id": "",
            "run_id": "",
            "boot_id": "",
        },
        "proof": {
            "local_runtime_proof_separate_from_boot_chain": True,
            "secure_boot_observed": False,
            "tpm_measured_boot_observed": False,
            "pcr_event_log_verified": False,
            "ima_enforcement_observed": False,
            "hardware_attestation_observed": False,
            "docker_claims_boot_trust": False,
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_verified_boot_attestation_nonclaim_json"] = _write_manifest(
            workspace,
            "latest-verified-boot-attestation-nonclaim.json",
            payload,
        )
    return payload


def build_observed_proof_intake_status(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    proof_surfaces = [
        {
            "id": "gmail_readonly_live",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["explicit_tester_oauth", "read_only_query", "sanitized_summary_or_log"],
        },
        {
            "id": "calendar_readonly_live",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["explicit_tester_oauth", "read_only_query", "sanitized_summary_or_log"],
        },
        {
            "id": "vm_iso_runtime_rejoin",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["observed_vm_boot", "reboot_or_recovery_run", "managed_runtime_rejoin_log"],
        },
        {
            "id": "release_artifact_signing",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["published_artifact", "checksum", "signature_or_signing_nonclaim"],
        },
        {
            "id": "browser_fallback_live",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["user_approved_browser_acceptance", "target_url", "sanitized_result"],
        },
        {
            "id": "boot_chain_trust",
            "status": "blocked",
            "claim_allowed": False,
            "requires": ["secure_boot_or_tpm_or_ima_evidence", "sanitized_observed_record"],
        },
    ]
    payload = {
        "schema_version": OBSERVED_PROOF_INTAKE_STATUS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "runtime_proof",
        "capability": "observed_proof_intake_status",
        "boundary_doc": "docs/architecture/observed-proof-intake-boundary.md",
        "record_schema": "docs/architecture/observed-proof-intake-schema.json",
        "validator": "scripts/observed_proof_intake_validate.py",
        "status": "ready_for_sanitized_records",
        "proof_surfaces": proof_surfaces,
        "summary": {
            "observed_proof_intake_ready": True,
            "observed_records_attached": 0,
            "claim_promotion_allowed": False,
            "live_credential_proof_claimed": False,
            "vm_iso_proof_claimed": False,
            "release_proof_claimed": False,
            "browser_live_proof_claimed": False,
            "boot_chain_trust_claimed": False,
        },
        "blockers": [
            {
                "id": "observed-record-required",
                "reason": "No sanitized observed proof record has been attached for any live or hardware proof surface.",
                "recovery_action": "Run the relevant manual acceptance flow, redact secrets, then validate the record with scripts/observed_proof_intake_validate.py.",
            }
        ],
        "correlation": {
            "session_id": str(session_id).strip(),
            "request_id": "",
            "approval_id": "",
            "trace_id": "",
            "run_id": "",
            "boot_id": "",
        },
        "proof": {
            "observed_proof_intake_ready": True,
            "observed_records_attached": False,
            "claim_promotion_allowed": False,
            "secrets_required_in_records": False,
            "live_proof_claimed": False,
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_observed_proof_intake_status_json"] = _write_manifest(
            workspace,
            "latest-observed-proof-intake-status.json",
            payload,
        )
    return payload


def build_calendar_readonly_status(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    payload = {
        "schema_version": CALENDAR_READONLY_STATUS_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "calendar",
        "capability": "calendar_readonly_status",
        "boundary_doc": "docs/architecture/calendar-readonly-capability-contract.md",
        "current_route": "calendar_fixture",
        "permission_level": "external_read",
        "fixture_ready": True,
        "live_oauth_ready": False,
        "mutation_allowed": False,
        "supported_actions": ["read", "search", "summarize"],
        "blocked_actions": ["create", "update", "delete", "invite", "cancel"],
        "proof": {
            "read_only": True,
            "fixture_mode_available": True,
            "real_calendar_credentials_used": False,
            "live_calendar_oauth_completed": False,
            "mutation_executed": False,
            "observed_live_proof_attached": False,
            "claim_promotion_allowed": False,
        },
        "blockers": [
            {
                "id": "calendar-live-oauth",
                "reason": "Live Calendar read-only proof requires explicit tester OAuth credentials and a live adapter design.",
                "recovery_action": "Keep Calendar in fixture mode until a read-only live adapter task records sanitized observed proof.",
            },
            {
                "id": "calendar-mutation-confirmation-model",
                "reason": "Calendar create/update/delete/invite/cancel actions are not part of the Phase 2 read-only boundary.",
                "recovery_action": "Design a later explicit confirmation model before enabling Calendar mutations.",
            },
        ],
        "correlation": {
            "session_id": str(session_id).strip(),
            "request_id": "",
            "approval_id": "",
            "trace_id": "",
            "run_id": "",
            "boot_id": "",
        },
        "summary": {
            "calendar_fixture_ready": True,
            "calendar_readonly_ready": True,
            "live_calendar_oauth_completed": False,
            "calendar_mutation_executed": False,
            "observed_live_calendar_proof_claimed": False,
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_calendar_readonly_status_json"] = _write_manifest(
            workspace,
            "latest-calendar-readonly-status.json",
            payload,
        )
    return payload


def build_inbox_proof_baseline_report(
    workspace_dir: str | Path,
    *,
    maildir_path: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    native_report = build_inbox_capability_report(workspace, session_id=session_id, write_manifest=True)
    native_intake_report = build_inbox_normalized_intake_report(
        workspace,
        session_id=session_id,
        write_manifest=False,
    )
    adapter_report = (
        build_inbox_capability_report(workspace, maildir_path=maildir_path, session_id=session_id, write_manifest=False)
        if maildir_path
        else {}
    )
    adapter_intake_report = (
        build_inbox_normalized_intake_report(
            workspace,
            maildir_path=maildir_path,
            session_id=session_id,
            write_manifest=False,
        )
        if maildir_path
        else {}
    )
    payload = {
        "schema_version": INBOX_PROOF_BASELINE_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "inbox",
        "capability": "inbox_proof_baseline",
        "native_fixture": native_report,
        "native_intake": native_intake_report,
        "adapter_report": adapter_report,
        "adapter_intake": adapter_intake_report,
        "proof_fields": [
            "native_inbox_handled",
            "inbox_adapter_required",
            "message_thread_correlated",
            "attachment_visibility_ok",
            "inbox_execution_ready",
            "session_correlated",
            "request_correlated",
            "approval_correlated",
        ],
        "summary": {
            "native_inbox_handled": bool(native_report.get("native_inbox_handled", False)),
            "adapter_report_present": bool(adapter_report),
            "inbox_adapter_required": bool(adapter_report.get("inbox_adapter_required", False)),
            "message_thread_correlated": bool(
                native_report.get("message_thread_correlated", False)
                and (adapter_report.get("message_thread_correlated", True) if adapter_report else True)
            ),
            "attachment_visibility_ok": bool(
                native_report.get("attachment_visibility_ok", False)
                and (adapter_report.get("attachment_visibility_ok", True) if adapter_report else True)
            ),
            "inbox_execution_ready": bool(
                native_report.get("inbox_execution_ready", False)
                and (adapter_report.get("inbox_execution_ready", True) if adapter_report else True)
            ),
            "session_correlated": bool(
                (native_intake_report.get("summary") or {}).get("session_correlated", False)
                and ((adapter_intake_report.get("summary") or {}).get("session_correlated", True) if adapter_intake_report else True)
            ),
            "request_correlated": bool(
                (native_intake_report.get("summary") or {}).get("request_correlated", False)
                and ((adapter_intake_report.get("summary") or {}).get("request_correlated", True) if adapter_intake_report else True)
            ),
            "approval_correlated": bool(
                (native_intake_report.get("summary") or {}).get("approval_correlated", False)
                and ((adapter_intake_report.get("summary") or {}).get("approval_correlated", True) if adapter_intake_report else True)
            ),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_inbox_proof_baseline_json"] = _write_manifest(
            workspace,
            "latest-inbox-proof-baseline.json",
            payload,
        )
    return payload


def build_inbox_normalized_intake_report(
    workspace_dir: str | Path,
    *,
    fixture_path: str = DEFAULT_INBOX_FIXTURE_PATH,
    maildir_path: str = "",
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    capability = build_inbox_capability_report(
        workspace,
        fixture_path=fixture_path,
        maildir_path=maildir_path,
        session_id=session_id,
        write_manifest=False,
    )
    correlation = dict(capability.get("correlation") or {})
    session_correlation = dict(capability.get("session_correlation") or {})
    ownership_summary = dict(capability.get("ownership_summary") or {})
    selected_path = "inbox_adapter_path" if capability.get("inbox_adapter_required", False) else "native_inbox_path"
    source_kind = capability.get("inbox_adapter_path") or "fixture"
    path_kind = "adapter" if capability.get("inbox_adapter_required", False) else "native"
    normalized_messages = []
    for index, message in enumerate(capability.get("messages") or [], start=1):
        normalized_messages.append(
            {
                "intake_id": f"message:{message.get('message_id', '') or index}",
                "intake_kind": "message_intake",
                "path_kind": path_kind,
                "source_kind": source_kind,
                "message_id": str(message.get("message_id", "")).strip(),
                "thread_id": str(message.get("thread_id", "")).strip(),
                "source_ref": str(message.get("source_ref", "")).strip(),
                "subject": str(message.get("subject", "")).strip(),
                "from": str(message.get("from", "")).strip(),
                "to": list(message.get("to") or []),
                "timestamp_utc": str(message.get("timestamp_utc", "")).strip(),
                "body_preview": str(message.get("body_preview", "")).strip(),
                "attachment_metadata": list(message.get("attachment_metadata") or []),
                "attachment_count": int(message.get("attachment_count", 0) or 0),
                "native_inbox_handled": bool(capability.get("native_inbox_handled", False)),
                "inbox_adapter_required": bool(capability.get("inbox_adapter_required", False)),
                "correlation": dict(correlation),
            }
        )
    payload = {
        "schema_version": INBOX_NORMALIZED_INTAKE_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "inbox",
        "capability": "inbox_normalized_intake",
        "selected_path": selected_path,
        "path_kind": path_kind,
        "source_kind": source_kind,
        "native_inbox_path": capability.get("native_inbox_path", ""),
        "inbox_adapter_path": capability.get("inbox_adapter_path", ""),
        "native_inbox_handled": bool(capability.get("native_inbox_handled", False)),
        "inbox_adapter_required": bool(capability.get("inbox_adapter_required", False)),
        "message_thread_correlated": bool(capability.get("message_thread_correlated", False)),
        "attachment_visibility_ok": bool(capability.get("attachment_visibility_ok", False)),
        "inbox_execution_ready": bool(capability.get("inbox_execution_ready", False)),
        "unsupported_or_deferred": bool(capability.get("unsupported_or_deferred", False)),
        "message_capability": capability.get("message_capability", "message_capability"),
        "thread_capability": capability.get("thread_capability", "thread_capability"),
        "attachment_capability": capability.get("attachment_capability", "attachment_capability"),
        "normalized_messages": normalized_messages,
        "threads": list(capability.get("threads") or []),
        "session_contract": session_correlation_contract(),
        "correlation": correlation,
        "session_correlation": session_correlation,
        "ownership_summary": ownership_summary,
        "proof_fields": [
            "native_inbox_handled",
            "inbox_adapter_required",
            "message_thread_correlated",
            "attachment_visibility_ok",
            "inbox_execution_ready",
        ],
        "proof": {
            "ok": bool(capability.get("inbox_execution_ready", False)),
            "selected_path": selected_path,
            "path_kind": path_kind,
            "source_kind": source_kind,
            "message_count": len(normalized_messages),
            "thread_count": len(capability.get("threads") or []),
            "message_identity_fields": ["message_id", "thread_id", "source_ref"],
            "attachment_metadata_fields": ["filename", "content_type", "size_bytes"],
            "session_correlated": bool(correlation.get("session_id", "")),
            "request_correlated": bool(correlation.get("request_id", "")),
            "approval_correlated": bool(correlation.get("approval_id", "")),
        },
        "summary": {
            "message_count": len(normalized_messages),
            "message_intake_count": len(normalized_messages),
            "thread_count": len(capability.get("threads") or []),
            "attachment_count": sum(int(item.get("attachment_count", 0) or 0) for item in normalized_messages),
            "selected_path": selected_path,
            "path_kind": path_kind,
            "source_kind": source_kind,
            "native_inbox_handled": bool(capability.get("native_inbox_handled", False)),
            "inbox_adapter_required": bool(capability.get("inbox_adapter_required", False)),
            "message_thread_correlated": bool(capability.get("message_thread_correlated", False)),
            "attachment_visibility_ok": bool(capability.get("attachment_visibility_ok", False)),
            "inbox_execution_ready": bool(capability.get("inbox_execution_ready", False)),
            "session_correlated": bool(correlation.get("session_id", "")),
            "request_correlated": bool(correlation.get("request_id", "")),
            "approval_correlated": bool(correlation.get("approval_id", "")),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_inbox_normalized_intake_json"] = _write_manifest(
            workspace,
            "latest-inbox-normalized-intake.json",
            payload,
        )
    return payload


def build_intake_surface_report(
    workspace_dir: str | Path,
    *,
    report_dir: str = "",
    session_id: str = "",
    limit: int = 20,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    events = query_events(workspace, limit=max(1, int(limit)))
    sessions = query_session_timeline(workspace, session_id=session_id, limit=max(1, int(limit)))
    intake_items: list[dict] = []
    for event in events.get("events", []) or []:
        correlation = dict(event.get("correlation") or {})
        intake_items.append(
            {
                "intake_id": f"event:{event.get('timestamp_utc', '')}:{event.get('kind', '')}",
                "timestamp_utc": event.get("timestamp_utc", ""),
                "intake_kind": _intake_kind_for_event(event),
                "intake_source": str(event.get("source", "")).strip().lower(),
                "summary": f"{event.get('kind', '')} {event.get('action', '')}".strip(),
                "native_intake_handled": True,
                "escalated_intake_handled": False,
                "intake_escalation_reason": "",
                "intake_visibility_state": _visibility_state(correlation),
                "intake_mediation_cost": _mediation_cost_for_intake({"intake_kind": _intake_kind_for_event(event)}),
                "correlation": correlation,
                "raw_ref": {"event_kind": event.get("kind", ""), "event_source": event.get("source", "")},
            }
        )

    feedback_root = Path(report_dir).resolve() if report_dir else workspace / "artifacts"
    feedback_manifest = _read_json(feedback_root / "feedback-intake" / "latest-feedback-intake-manifest.json")
    if feedback_manifest:
        feedback_packet = feedback_manifest.get("feedback_packet") or {}
        intake_items.append(
            {
                "intake_id": f"feedback:{feedback_manifest.get('generated_at_utc', '')}",
                "timestamp_utc": feedback_manifest.get("generated_at_utc", ""),
                "intake_kind": "feedback_intake",
                "intake_source": str(feedback_packet.get("channel", "manual")).strip(),
                "summary": str(feedback_packet.get("summary", "")).strip(),
                "native_intake_handled": True,
                "escalated_intake_handled": False,
                "intake_escalation_reason": "",
                "intake_visibility_state": "visible_to_codex",
                "intake_mediation_cost": "medium",
                "correlation": {
                    "session_id": str(session_id or (sessions.get("correlation_evidence", {}) or {}).get("session_id", "")),
                    "request_id": "",
                    "approval_id": "",
                    "trace_id": "",
                    "run_id": "",
                    "boot_id": "",
                },
                "raw_ref": {
                    "feedback_manifest_json": str(feedback_root / "feedback-intake" / "latest-feedback-intake-manifest.json"),
                    "recommendation": feedback_packet.get("recommendation", ""),
                },
            }
        )

    intake_items.sort(key=lambda item: item.get("timestamp_utc", ""))
    intake_items = intake_items[-max(1, int(limit)) :]
    counts_by_kind: dict[str, int] = {}
    for item in intake_items:
        counts_by_kind[item["intake_kind"]] = counts_by_kind.get(item["intake_kind"], 0) + 1

    payload = {
        "schema_version": INTAKE_SURFACE_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "supported_intake_kinds": list(SUPPORTED_INTAKE_KINDS),
        "session_contract": session_correlation_contract(),
        "intake_items": intake_items,
        "summary": {
            "ok": True,
            "total_items": len(intake_items),
            "counts_by_kind": counts_by_kind,
            "native_intake_items": sum(1 for item in intake_items if item.get("native_intake_handled")),
            "escalated_intake_items": sum(1 for item in intake_items if item.get("escalated_intake_handled")),
            "visible_session_correlated_items": sum(
                1 for item in intake_items if item.get("intake_visibility_state") == "session_correlated"
            ),
        },
        "session_correlation": sessions.get("correlation_evidence", {}),
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_intake_surface_manifest_json"] = _write_manifest(
            workspace,
            "latest-intake-surface.json",
            payload,
        )
    return payload


def build_capability_proof_surface(workspace_dir: str | Path) -> dict:
    workspace = Path(workspace_dir).resolve()
    document_path = _workspace_document_probe_path(workspace)
    document_manifest = build_document_access_report(workspace, document_path, write_manifest=True)
    # Refresh a canonical web proof surface so the integrated manifest is never just a stale read.
    web_manifest = build_web_access_report(workspace, "https://example.com", write_manifest=True)
    intake_manifest = build_intake_surface_report(workspace, write_manifest=True)
    inbox_manifest = build_inbox_capability_report(workspace, write_manifest=True)
    inbox_intake_manifest = build_inbox_normalized_intake_report(workspace, write_manifest=True)
    from kernel.service_permission_capability import (
        build_permission_capability_report,
        build_service_capability_report,
    )
    from kernel.control_plane_capabilities import build_execution_ownership_report, load_latest_control_plane_manifests

    service_manifest = build_service_capability_report(workspace, write_manifest=True)
    permission_manifest = build_permission_capability_report(workspace, write_manifest=True)
    execution_ownership_manifest = build_execution_ownership_report(workspace, samples=[], write_manifest=True)
    control_plane_manifests = load_latest_control_plane_manifests(workspace)
    payload = {
        "schema_version": CAPABILITY_PROOF_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "proof_vocabulary": {
            "native_handled": "capability completed through the native path",
            "escalated_handled": "capability required an escalated adapter path",
            "escalation_reason": "why the native path was not selected",
            "unsupported_or_deferred": "capability not yet handled in the current window",
            "mediation_cost": "qualitative mediation overhead",
            "native_intake_handled": "intake item visible through the native intake substrate",
            "escalated_intake_handled": "intake item required escalated mediation",
            "intake_visibility_state": "how directly the intake item is visible to Codex",
            "intake_mediation_cost": "qualitative overhead for intake visibility",
            "inbox_message_intake_count": "number of message-intake items exposed on the normalized inbox intake surface",
            "inbox_session_correlated": "the inbox intake surface carries session correlation evidence",
            "inbox_request_correlated": "the inbox intake surface carries request correlation evidence",
            "inbox_approval_correlated": "the inbox intake surface carries approval correlation evidence",
            "native_control_available": "direct control is available without broker mediation",
            "broker_mediated_control": "control is mediated through broker governance",
            "escalated_control_required": "control requires an approval or override path",
            "control_handling": "machine-readable control mode for the capability or event",
        },
        "document_access": document_manifest,
        "web_access": web_manifest,
        "intake_surface": intake_manifest,
        "inbox_capability": inbox_manifest,
        "inbox_normalized_intake": inbox_intake_manifest,
        "service_capability": service_manifest,
        "permission_capability": permission_manifest,
        "execution_ownership": execution_ownership_manifest,
        "vm_e2e_proof": control_plane_manifests.get("vm_e2e_proof", {}),
        "summary": {
            "document_native_handled": bool(document_manifest.get("native_handled", False)),
            "web_native_handled": bool(web_manifest.get("native_handled", False)),
            "web_escalated_handled": bool(web_manifest.get("escalated_handled", False)),
            "intake_native_items": int((intake_manifest.get("summary") or {}).get("native_intake_items", 0)),
            "intake_escalated_items": int((intake_manifest.get("summary") or {}).get("escalated_intake_items", 0)),
            "native_inbox_handled": bool(inbox_manifest.get("native_inbox_handled", False)),
            "inbox_adapter_required": bool(inbox_manifest.get("inbox_adapter_required", False)),
            "message_thread_correlated": bool(inbox_manifest.get("message_thread_correlated", False)),
            "attachment_visibility_ok": bool(inbox_manifest.get("attachment_visibility_ok", False)),
            "inbox_execution_ready": bool(inbox_manifest.get("inbox_execution_ready", False)),
            "inbox_message_intake_count": int((inbox_intake_manifest.get("summary") or {}).get("message_intake_count", 0)),
            "inbox_session_correlated": bool((inbox_intake_manifest.get("summary") or {}).get("session_correlated", False)),
            "inbox_request_correlated": bool((inbox_intake_manifest.get("summary") or {}).get("request_correlated", False)),
            "inbox_approval_correlated": bool((inbox_intake_manifest.get("summary") or {}).get("approval_correlated", False)),
            "service_broker_mediated_units": int((service_manifest.get("summary") or {}).get("broker_mediated_control_units", 0)),
            "service_escalated_control_units": int((service_manifest.get("summary") or {}).get("escalated_control_units", 0)),
            "permission_approval_requested": int((permission_manifest.get("summary") or {}).get("approval_requested", 0)),
            "permission_escalated_events": int((permission_manifest.get("summary") or {}).get("escalated_permission_events", 0)),
            "execution_samples": len((execution_ownership_manifest.get("sampled_execution_paths") or [])),
        },
        "artifacts": {},
    }
    payload["artifacts"]["latest_capability_proof_surface_json"] = _write_manifest(
        workspace,
        "latest-capability-proof-surface.json",
        payload,
    )
    return payload


def capability_vocabulary_contract() -> dict:
    return {
        "capability_families": ["document", "web", "intake", "inbox", "service", "permission"],
        "native_first_rule": "native path first -> escalated adapter second",
        "document_defaults": {
            "native_document_classes": list(SUPPORTED_DOCUMENT_CLASSES),
            "compatibility_tooling": ["file_read"],
        },
        "web_defaults": {
            "native_path": "fetch_parse_document",
            "browser_path": "escalated_only",
            "browser_escalation_reasons": list(ESCALATION_REASONS),
        },
        "intake_defaults": {
            "supported_intake_kinds": list(SUPPORTED_INTAKE_KINDS),
            "default_visibility_goal": "visible_to_codex_without_app_specific_ui_mediation",
        },
        "inbox_defaults": {
            "message_capability": "message_capability",
            "inbox_capability": "inbox_capability",
            "thread_capability": "thread_capability",
            "attachment_capability": "attachment_capability",
            "native_inbox_path": "fixture_or_kernel_owned_inbox_surface",
            "inbox_adapter_path": "maildir_or_other_adapter_surface",
        },
        "service_defaults": {
            "native_visibility": "system_state_observation",
            "default_control_path": "broker_mediated",
            "escalated_control_path": "broker_approval_gate",
        },
        "permission_defaults": {
            "native_signal_path": "runtime_trace_visibility",
            "default_control_path": "broker_approval_gate",
            "override_path": "broker_override",
        },
        "proof_vocabulary": {
            "native_handled": "native path completed the capability",
            "escalated_handled": "escalated adapter path completed the capability",
            "escalation_reason": "why escalation was required",
            "unsupported_or_deferred": "capability is not handled in the active window",
            "mediation_cost": "qualitative mediation overhead",
            "native_intake_handled": "intake item remained on the normalized intake path",
            "escalated_intake_handled": "intake item required escalated mediation",
            "intake_visibility_state": "how directly the item is visible to Codex",
            "intake_mediation_cost": "qualitative overhead for intake handling",
            "native_inbox_handled": "inbox handling completed on the native inbox path",
            "inbox_adapter_required": "the selected inbox path required an adapter such as Maildir",
            "message_intake_count": "number of normalized inbox message-intake items on the selected path",
            "session_correlated": "the inbox surface preserves session correlation evidence",
            "request_correlated": "the inbox surface preserves request correlation evidence",
            "approval_correlated": "the inbox surface preserves approval correlation evidence",
            "message_thread_correlated": "messages preserve a stable thread identity",
            "attachment_visibility_ok": "attachment metadata stays visible on the selected inbox path",
            "inbox_execution_ready": "the inbox surface is ready for downstream execution and review",
            "native_control_available": "direct control can happen without broker mediation",
            "broker_mediated_control": "control requires broker governance",
            "escalated_control_required": "approval or override path is required",
            "control_handling": "machine-readable control mode for the surface",
            "capability_selected_path": "the selected execution path for a capability action",
            "permission_state": "the current readiness of a capability action",
            "broker_mediated": "the selected execution path uses broker mediation",
            "external_adapter_required": "the selected execution path leaves native or broker-owned execution",
            "capability_execution_ready": "the capability can execute immediately on the selected path",
        },
    }
