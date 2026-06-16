#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
for candidate in (SRC_DIR, SCRIPTS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from io_utils import scrub_payload
from kernel.capability_substrate import build_telegram_live_loop_report
from kernel.operator_activity import build_activity_feed_payload
from kernel_phase2_run import run_phase2
from kernel_phase2_setup_status import build_status


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(scrub_payload(payload), ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b""
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            value = json.loads(raw.decode("utf-8") or "{}")
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


class DockerPreviewApp:
    def __init__(self, *, workspace: Path, user_root: Path, telegram_polling: bool, telegram_interval: int) -> None:
        self.workspace = workspace
        self.user_root = user_root
        self.telegram_polling = telegram_polling
        self.telegram_interval = max(5, int(telegram_interval or 10))
        self._stop = threading.Event()
        self._telegram_thread: threading.Thread | None = None

    def start_background_workers(self) -> None:
        token = os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN", "").strip()
        chats = os.environ.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
        if not self.telegram_polling or not token or not chats:
            return
        self._telegram_thread = threading.Thread(target=self._telegram_loop, name="agentos-telegram-polling-preview", daemon=True)
        self._telegram_thread.start()

    def _telegram_loop(self) -> None:
        while not self._stop.is_set():
            try:
                build_telegram_live_loop_report(self.workspace, once=True, send_reply=True, write_manifest=True)
            except Exception:
                # Keep compose logs user-facing. Detailed state is visible via /activity and artifacts.
                pass
            self._stop.wait(self.telegram_interval)

    def status(self) -> dict:
        setup = build_status(str(self.workspace), str(self.user_root))
        activity = build_activity_feed_payload(self.workspace, limit=12)
        product_layer = self.product_layer(setup=setup, activity=activity)
        return {
            "schema_version": "agentos-docker-runtime-preview-status.v1",
            "docker_preview": True,
            "workspace": str(self.workspace),
            "user_data_root": str(self.user_root),
            "http_url": "http://localhost:8787",
            "runtime": setup,
            "telegram": {
                "transport": "polling_preview",
                "polling_worker_enabled": bool(self.telegram_polling),
                "token_configured": bool(os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN", "").strip()),
                "allowed_chat_configured": bool(os.environ.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip()),
                "webhook_configured": False,
            },
            "activity": activity,
            "product_layer": product_layer,
            "proof": {
                "ok": True,
                "docker_preview_surface_ready": True,
                "product_layer_runtime_home_ready": True,
                "boot_or_iso_proof": False,
                "secrets_redacted": True,
            },
        }

    def product_layer(self, *, setup: dict | None = None, activity: dict | None = None) -> dict:
        setup_payload = setup or build_status(str(self.workspace), str(self.user_root))
        activity_payload = activity or build_activity_feed_payload(self.workspace, limit=12)
        adapters = setup_payload.get("adapters", {}) if isinstance(setup_payload.get("adapters"), dict) else {}
        work_inbox = self.work_inbox(setup=setup_payload)
        recovery_center = self.recovery_center(setup=setup_payload)
        evidence_dashboard = self.evidence_dashboard(setup=setup_payload, activity=activity_payload)
        blockers = recovery_center.get("blockers", [])
        return {
            "schema_version": "agentos-product-layer-runtime-home.v1",
            "surface": "Docker Runtime Home",
            "customer_message": "AgentOS is ready for local-first runtime preview. Some live proofs still need user-provided evidence.",
            "features": [
                {
                    "id": "runtime_home",
                    "label": "Runtime Home",
                    "state": str(setup_payload.get("overall_state", "ready")),
                    "customer_value": "See whether the managed runtime is ready before asking AgentOS to work.",
                },
                {
                    "id": "work_inbox",
                    "label": "Work Inbox",
                    "state": work_inbox.get("state", _inbox_state(adapters)),
                    "customer_value": "Try read-first inbox workflows through fixtures, Maildir boundaries, and explicit live blockers.",
                },
                {
                    "id": "activity_timeline",
                    "label": "Activity Timeline",
                    "state": "ready" if activity_payload.get("activity_feed_ready") else "degraded",
                    "customer_value": "Understand what AgentOS did, which capability ran, and what happened next.",
                },
                {
                    "id": "recovery_center",
                    "label": "Recovery Center",
                    "state": "attention" if blockers else "ready",
                    "customer_value": "Turn missing credentials, Docker daemon gaps, and observed-proof blockers into clear next steps.",
                },
                {
                    "id": "evidence_dashboard",
                    "label": "Evidence Dashboard",
                    "state": "partial",
                    "customer_value": "Separate completed Docker/local proof from live OAuth, VM/ISO, browser, release, and attestation evidence.",
                },
            ],
            "blockers": blockers,
            "work_inbox": work_inbox,
            "recovery_center": recovery_center,
            "evidence_dashboard": evidence_dashboard,
            "proof": {
                "docker_main_try_path": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "customer_facing_summary_ready": True,
            },
        }

    def evidence_dashboard(self, *, setup: dict | None = None, activity: dict | None = None) -> dict:
        setup_payload = setup or build_status(str(self.workspace), str(self.user_root))
        activity_payload = activity or build_activity_feed_payload(self.workspace, limit=12)
        evidence = [
            {
                "id": "docker-runtime-preview",
                "label": "Docker runtime preview",
                "state": "observed_by_smoke",
                "customer_claim": "AgentOS can be tried through Docker with Runtime Home, Work Inbox, Recovery Center, and activity APIs.",
                "evidence_source": "scripts/smoke_docker_runtime_preview_python.sh and docker compose config",
            },
            {
                "id": "phase2-golden-runtime-loop",
                "label": "Phase 2 golden runtime loop",
                "state": "observed_by_smoke",
                "customer_claim": "Prompt intake, intent classification, bounded capability execution, records, activity narration, and recovery contracts are locally smoke-tested.",
                "evidence_source": "scripts/smoke_phase2_golden_demo.sh",
            },
            {
                "id": "work-inbox-read-first",
                "label": "Work Inbox read-first proof",
                "state": "docker_preview_contract",
                "customer_claim": "Fixture, Maildir boundary, Gmail, and Calendar appear as read-first inbox sources with mutation non-claims.",
                "evidence_source": "/api/work-inbox",
            },
            {
                "id": "activity-timeline",
                "label": "Activity Timeline",
                "state": "ready" if activity_payload.get("activity_feed_ready") else "degraded",
                "customer_claim": "AgentOS can show recent runtime activity and user-visible records.",
                "evidence_source": "/api/activity",
            },
        ]
        non_claims = [
            {
                "id": "vm-iso-boot-proof",
                "label": "VM/ISO boot proof",
                "state": "not_claimed",
                "required_evidence": "Observed VM/ISO boot, install, reboot, recovery, and managed runtime rejoin record.",
            },
            {
                "id": "live-oauth-proof",
                "label": "Live OAuth proof",
                "state": "not_claimed",
                "required_evidence": "Explicit tester credentials plus sanitized read-only Gmail/Calendar observed runs.",
            },
            {
                "id": "live-browser-proof",
                "label": "Live browser proof",
                "state": "not_claimed",
                "required_evidence": "User-approved browser run and sanitized observed artifacts.",
            },
            {
                "id": "release-trust-proof",
                "label": "Release trust proof",
                "state": "not_claimed",
                "required_evidence": "Published release artifacts, checksums, signatures, and signoff record.",
            },
            {
                "id": "hardware-attestation-proof",
                "label": "Hardware attestation proof",
                "state": "not_claimed",
                "required_evidence": "Secure Boot, TPM/PCR, event-log, IMA, or equivalent hardware-backed attestation evidence.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-evidence-dashboard.v1",
            "surface": "Evidence Dashboard",
            "state": "partial",
            "customer_message": "Evidence Dashboard separates Docker/local proof from proof that still requires observed external evidence.",
            "evidence": evidence,
            "non_claims": non_claims,
            "proof": {
                "docker_preview_ready": True,
                "phase2_golden_smoke_expected": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "hardware_attestation_claimed": False,
                "customer_facing_evidence_ready": True,
            },
        }

    def recovery_center(self, *, setup: dict | None = None) -> dict:
        setup_payload = setup or build_status(str(self.workspace), str(self.user_root))
        blockers = _product_blockers(setup_payload)
        recovery_items = [
            {
                "id": "vm-iso-observed-proof",
                "label": "Boot and rejoin proof",
                "state": "blocked_until_observed_proof",
                "customer_problem": "Docker preview can show AgentOS runtime behavior, but it cannot prove ISO boot, install, reboot, recovery, or managed runtime rejoin.",
                "recovery_action": "Attach sanitized VM/ISO evidence from an observed run before claiming OS boot proof.",
            },
            {
                "id": "live-oauth-proof",
                "label": "Live inbox proof",
                "state": "blocked_until_user_credentials",
                "customer_problem": "Gmail and Calendar live proof require explicit user OAuth credentials and read-only observed runs.",
                "recovery_action": "Keep fixture and local-path proof active until credentials and sanitized observed evidence are provided.",
            },
            {
                "id": "live-browser-proof",
                "label": "Browser proof",
                "state": "blocked_until_user_approved_run",
                "customer_problem": "Browser automation is not claimed as a default customer capability until an approved live run is observed.",
                "recovery_action": "Run a future live browser proof with user approval and attach sanitized artifacts before promoting the claim.",
            },
            {
                "id": "release-trust-proof",
                "label": "Release trust proof",
                "state": "blocked_until_release_evidence",
                "customer_problem": "Docker preview does not prove signed release media, checksums, or distribution integrity.",
                "recovery_action": "Attach release manifests, checksums, and signing evidence before presenting release trust as complete.",
            },
            {
                "id": "attestation-proof",
                "label": "Attestation proof",
                "state": "blocked_until_hardware_evidence",
                "customer_problem": "Secure Boot, TPM/PCR, and hardware attestation are outside Docker preview proof.",
                "recovery_action": "Attach hardware-backed attestation evidence before claiming device-level trust.",
            },
        ]
        blocker_ids = {str(blocker.get("id", "")) for blocker in blockers}
        if "llm-setup" in blocker_ids:
            recovery_items.append(
                {
                    "id": "llm-setup",
                    "label": "Local model setup",
                    "state": "needs_setup_attention",
                    "customer_problem": "The local model path is not fully ready in this preview state.",
                    "recovery_action": "Use deterministic fixture-backed capabilities or follow setup guidance before claiming local model readiness.",
                }
            )
        return {
            "schema_version": "agentos-product-layer-recovery-center.v1",
            "surface": "Recovery Center",
            "state": "attention" if blockers else "ready",
            "customer_message": "Recovery Center turns missing proof into clear next actions without overstating what Docker has proven.",
            "items": recovery_items,
            "blockers": blockers,
            "proof": {
                "docker_preview_ready": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "hardware_attestation_claimed": False,
                "customer_facing_recovery_ready": True,
            },
        }

    def work_inbox(self, *, setup: dict | None = None) -> dict:
        setup_payload = setup or build_status(str(self.workspace), str(self.user_root))
        adapters = setup_payload.get("adapters", {}) if isinstance(setup_payload.get("adapters"), dict) else {}
        sources = [
            {
                "id": "native_fixture",
                "label": "Fixture Inbox",
                "state": "ready",
                "permission": "local_read",
                "customer_value": "Try inbox summaries and draft preparation without external credentials.",
            },
            {
                "id": "maildir",
                "label": "Maildir",
                "state": "available_after_user_path",
                "permission": "local_read",
                "customer_value": "Use a user-owned local inbox path when explicit observed evidence is attached.",
            },
            {
                "id": "gmail",
                "label": "Gmail",
                "state": _adapter_state(adapters.get("gmail")),
                "permission": "external_read",
                "customer_value": "Read-only Gmail can be promoted after explicit OAuth and observed proof.",
            },
            {
                "id": "calendar",
                "label": "Calendar",
                "state": _adapter_state(adapters.get("calendar")),
                "permission": "external_read",
                "customer_value": "Read-only Calendar can be promoted after explicit OAuth and observed proof.",
            },
        ]
        blockers = [
            {
                "id": "live-gmail-oauth",
                "source": "gmail",
                "reason": "Live Gmail proof requires explicit user OAuth credentials and a sanitized observed read-only run.",
                "recovery_action": "Use fixture/local proof until credentials and observed evidence are provided.",
            },
            {
                "id": "live-calendar-oauth",
                "source": "calendar",
                "reason": "Live Calendar proof requires explicit user OAuth credentials and a sanitized observed read-only run.",
                "recovery_action": "Use fixture/local proof until credentials and observed evidence are provided.",
            },
            {
                "id": "observed-maildir-user-data-proof",
                "source": "maildir",
                "reason": "Real user Maildir proof requires an explicit user-owned path and sanitized observed evidence.",
                "recovery_action": "Run a future Maildir observed-proof task before claiming production user inbox proof.",
            },
        ]
        workflows = [
            {
                "id": "inbox_summary",
                "label": "Summarize inbox items",
                "state": "docker_preview_ready",
                "mutation_allowed": False,
            },
            {
                "id": "draft_preparation",
                "label": "Prepare reply drafts",
                "state": "docker_preview_ready",
                "mutation_allowed": False,
            },
            {
                "id": "search_and_triage",
                "label": "Search and triage work items",
                "state": "docker_preview_ready",
                "mutation_allowed": False,
            },
        ]
        return {
            "schema_version": "agentos-product-layer-work-inbox.v1",
            "surface": "Work Inbox",
            "state": "preview",
            "customer_message": "Work Inbox is available as a read-first Docker preview. Live providers remain blocked until observed proof is attached.",
            "sources": sources,
            "workflows": workflows,
            "blockers": blockers,
            "proof": {
                "docker_preview_ready": True,
                "read_first_only": True,
                "external_mutation_claimed": False,
                "live_oauth_claimed": False,
                "browser_default_claimed": False,
                "customer_facing_summary_ready": True,
            },
        }

    def run_prompt(self, message: str) -> dict:
        message = str(message or "").strip()
        if not message:
            return {
                "ok": False,
                "failure_class": "empty_prompt",
                "response": "Enter a prompt first.",
            }
        result = run_phase2(workspace=self.workspace, user_root=self.user_root, prompt=message)
        return {
            "ok": bool(result.get("proof", {}).get("ok", False)),
            "intent": result.get("intent", ""),
            "capability": result.get("capability", ""),
            "status": result.get("status", ""),
            "response": result.get("response", ""),
            "record": result.get("record", {}),
            "artifacts": result.get("artifacts", {}),
            "activity": result.get("activity_feed", {}),
            "proof": result.get("proof", {}),
        }

    def telegram_check(self) -> dict:
        try:
            payload = build_telegram_live_loop_report(self.workspace, once=True, send_reply=True, write_manifest=True)
            return payload
        except Exception as exc:
            return {
                "schema_version": "agentos-docker-telegram-preview-error.v1",
                "proof": {"ok": False, "reason": "telegram_preview_failed"},
                "friendly_error": str(exc),
            }

    def activity(self) -> dict:
        return build_activity_feed_payload(self.workspace, limit=40)


def _product_blockers(setup: dict) -> list[dict]:
    blockers = [
        {
            "id": "vm-iso-observed-proof",
            "label": "VM/ISO proof",
            "reason": "Docker preview does not prove boot, install, reboot, recovery, or managed runtime rejoin.",
            "recovery_action": "Run and attach a sanitized observed VM/ISO proof record before claiming OS boot proof.",
        },
        {
            "id": "live-oauth-proof",
            "label": "Live OAuth proof",
            "reason": "Gmail and Calendar live proof require explicit user credentials and observed read-only runs.",
            "recovery_action": "Use fixture/local proof until a tester provides credentials and sanitized observed evidence.",
        },
    ]
    adapters = setup.get("adapters", {}) if isinstance(setup.get("adapters"), dict) else {}
    llm = adapters.get("llm", {}) if isinstance(adapters.get("llm"), dict) else {}
    if str(llm.get("state", "")).lower() not in {"ready", "available", "ok"}:
        blockers.append(
            {
                "id": "llm-setup",
                "label": "LLM setup",
                "reason": "The local model path is not fully ready in this preview state.",
                "recovery_action": "Follow setup status guidance or use deterministic fixture-backed capabilities.",
            }
        )
    return blockers


def _inbox_state(adapters: dict) -> str:
    gmail = adapters.get("gmail", {}) if isinstance(adapters.get("gmail"), dict) else {}
    calendar = adapters.get("calendar", {}) if isinstance(adapters.get("calendar"), dict) else {}
    if gmail.get("state") == "ready" or calendar.get("state") == "ready":
        return "ready"
    return "preview"


def _adapter_state(value: object) -> str:
    adapter = value if isinstance(value, dict) else {}
    state = str(adapter.get("state", "")).lower()
    if state in {"ready", "available", "ok"}:
        return "ready"
    if state in {"blocked", "setup_needed", "missing_credentials"}:
        return "setup_needed"
    return "blocked_until_observed_proof"


def _render_page(app: DockerPreviewApp) -> str:
    status = scrub_payload(app.status())
    adapters = status.get("runtime", {}).get("adapters", {})
    activity = status.get("activity", {}).get("events", [])
    product_layer = status.get("product_layer", {})
    work_inbox = product_layer.get("work_inbox", {}) if isinstance(product_layer.get("work_inbox"), dict) else {}
    recovery_center = product_layer.get("recovery_center", {}) if isinstance(product_layer.get("recovery_center"), dict) else {}
    evidence_dashboard = product_layer.get("evidence_dashboard", {}) if isinstance(product_layer.get("evidence_dashboard"), dict) else {}
    features = product_layer.get("features", []) if isinstance(product_layer.get("features"), list) else []
    blockers = product_layer.get("blockers", []) if isinstance(product_layer.get("blockers"), list) else []
    llm_state = adapters.get("llm", {}).get("state", "unknown")
    telegram = status.get("telegram", {})
    telegram_state = "ready" if telegram.get("token_configured") and telegram.get("allowed_chat_configured") else "setup needed"
    cards = [
        ("Runtime", status.get("runtime", {}).get("overall_state", "unknown")),
        ("LLM", llm_state),
        ("Telegram", f"{telegram_state} · polling preview"),
        ("Workspace", status.get("workspace", "")),
    ]
    activity_html = "\n".join(
        f"<li><b>{html.escape(str(event.get('label', 'AgentOS')))}</b> "
        f"<span>{html.escape(str(event.get('time', '')))}</span> "
        f"{html.escape(str(event.get('human_message', '')))}</li>"
        for event in activity[-12:]
    ) or "<li>No activity yet. Run a prompt below.</li>"
    card_html = "\n".join(
        f"<section class='card'><h3>{html.escape(title)}</h3><p>{html.escape(str(value))}</p></section>"
        for title, value in cards
    )
    feature_html = "\n".join(
        "<section class='feature'>"
        f"<div><h3>{html.escape(str(feature.get('label', 'Feature')))}</h3>"
        f"<p>{html.escape(str(feature.get('customer_value', '')))}</p></div>"
        f"<span class='state'>{html.escape(str(feature.get('state', 'unknown')))}</span>"
        "</section>"
        for feature in features
    )
    blocker_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(blocker.get('label', blocker.get('id', 'Blocker'))))}</b> "
        f"{html.escape(str(blocker.get('reason', '')))} "
        f"<em>{html.escape(str(blocker.get('recovery_action', '')))}</em>"
        "</li>"
        for blocker in blockers
    ) or "<li>No product-layer blockers in this Docker preview.</li>"
    recovery_item_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Recovery item'))))}</b> "
        f"{html.escape(str(item.get('customer_problem', '')))} "
        f"<em>{html.escape(str(item.get('recovery_action', '')))}</em>"
        "</li>"
        for item in recovery_center.get("items", [])
        if isinstance(item, dict)
    ) or blocker_html
    inbox_source_html = "\n".join(
        "<section class='feature'>"
        f"<div><h3>{html.escape(str(source.get('label', 'Inbox source')))}</h3>"
        f"<p>{html.escape(str(source.get('customer_value', '')))}</p></div>"
        f"<span class='state'>{html.escape(str(source.get('state', 'unknown')))}</span>"
        "</section>"
        for source in work_inbox.get("sources", [])
        if isinstance(source, dict)
    )
    inbox_workflow_html = "\n".join(
        f"<li><b>{html.escape(str(workflow.get('label', 'Workflow')))}</b> "
        f"{html.escape(str(workflow.get('state', '')))} · mutation_allowed={html.escape(str(workflow.get('mutation_allowed', False)).lower())}</li>"
        for workflow in work_inbox.get("workflows", [])
        if isinstance(workflow, dict)
    ) or "<li>No Work Inbox workflows are available yet.</li>"
    evidence_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Evidence'))))}</b> "
        f"{html.escape(str(item.get('customer_claim', '')))} "
        f"<em>{html.escape(str(item.get('evidence_source', '')))}</em>"
        "</li>"
        for item in evidence_dashboard.get("evidence", [])
        if isinstance(item, dict)
    ) or "<li>No customer-facing evidence is available yet.</li>"
    non_claim_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Non-claim'))))}</b> "
        f"{html.escape(str(item.get('required_evidence', '')))}"
        "</li>"
        for item in evidence_dashboard.get("non_claims", [])
        if isinstance(item, dict)
    ) or "<li>No explicit non-claims are available yet.</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentOS Docker Preview</title>
  <style>
    :root {{ color-scheme: dark; --bg:#08110f; --panel:#101c18; --line:#29463b; --text:#effaf3; --muted:#a8b9ae; --accent:#79f29a; --warn:#f2d479; }}
    body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #173429, var(--bg)); color:var(--text); }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ font-size: clamp(2.2rem, 6vw, 5rem); line-height: .94; margin: 0 0 16px; letter-spacing: -0.06em; }}
    .tag {{ display:inline-block; color:#06200e; background:var(--accent); border-radius: 999px; padding: 8px 14px; font-weight: 800; margin-bottom: 18px; }}
    .lead {{ max-width: 780px; color: var(--muted); font-size: 1.15rem; line-height: 1.6; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 28px 0; }}
    .card, .panel {{ background: color-mix(in srgb, var(--panel) 88%, transparent); border: 1px solid var(--line); border-radius: 22px; padding: 20px; box-shadow: 0 20px 80px rgba(0,0,0,.25); }}
    .card h3 {{ margin:0 0 10px; color:var(--accent); }}
    .card p {{ margin:0; color:var(--muted); overflow-wrap:anywhere; }}
    .product {{ display:grid; grid-template-columns: minmax(0,1.35fr) minmax(280px,.65fr); gap:18px; margin: 28px 0; }}
    .feature {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; border-bottom:1px solid #1d332b; padding:14px 0; }}
    .feature h3 {{ margin:0 0 6px; color:var(--text); }}
    .feature p {{ margin:0; color:var(--muted); line-height:1.45; }}
    .state {{ flex:0 0 auto; color:#07130c; background:var(--accent); border-radius:999px; padding:6px 10px; font-weight:850; font-size:.82rem; }}
    .blockers li em {{ display:block; color:var(--warn); margin-top:4px; font-style:normal; }}
    textarea {{ width:100%; min-height: 92px; box-sizing:border-box; border-radius:18px; border:1px solid var(--line); background:#06100d; color:var(--text); padding:16px; font: inherit; }}
    button {{ border:0; border-radius: 999px; background:var(--accent); color:#041008; padding: 12px 18px; font-weight: 850; margin: 12px 8px 0 0; cursor:pointer; }}
    button.secondary {{ background:#20392f; color:var(--text); border: 1px solid var(--line); }}
    pre {{ white-space: pre-wrap; overflow-wrap:anywhere; background:#050b09; border:1px solid var(--line); border-radius:18px; padding:16px; color:#d8eadf; }}
    ul {{ list-style:none; padding:0; margin:0; }}
    li {{ border-bottom:1px solid #1d332b; padding:10px 0; color:#dce9e1; }}
    li span {{ color:var(--muted); margin: 0 8px; }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="tag">Docker runtime preview</div>
    <h1>AgentOS</h1>
    <p class="lead">Try the AgentOS runtime without booting an ISO. This preview routes prompts through the same local-first intent/capability path and writes proof logs under mounted user data.</p>
  </header>
  <div class="grid">{card_html}</div>
  <section class="product">
    <div class="panel">
      <h2>Runtime Home</h2>
      <p class="lead">{html.escape(str(product_layer.get('customer_message', 'AgentOS runtime preview is ready.')))}</p>
      {feature_html}
    </div>
    <div class="panel">
      <h2>Recovery Center</h2>
      <p class="lead">{html.escape(str(recovery_center.get('customer_message', 'Missing proof is listed below.')))}</p>
      <ul class="blockers">{recovery_item_html}</ul>
      <p><a href="/api/recovery">recovery JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Work Inbox</h2>
      <p class="lead">{html.escape(str(work_inbox.get('customer_message', 'Read-first inbox preview.')))}</p>
      {inbox_source_html}
    </div>
    <div class="panel">
      <h2>Inbox Workflows</h2>
      <ul>{inbox_workflow_html}</ul>
      <p><a href="/api/work-inbox">work inbox JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Evidence Dashboard</h2>
      <p class="lead">{html.escape(str(evidence_dashboard.get('customer_message', 'Evidence state is available below.')))}</p>
      <ul>{evidence_html}</ul>
    </div>
    <div class="panel">
      <h2>Not Yet Claimed</h2>
      <ul>{non_claim_html}</ul>
      <p><a href="/api/evidence">evidence JSON</a></p>
    </div>
  </section>
  <section class="panel">
    <h2>Run a prompt</h2>
    <textarea id="prompt">status</textarea>
    <br>
    <button onclick="runPrompt()">Run prompt</button>
    <button class="secondary" onclick="telegramCheck()">Manual Telegram check</button>
    <button class="secondary" onclick="refreshStatus()">Refresh</button>
    <pre id="result">Ready. Try: hi, status, workspace 파일 목록 보여줘, or search AgentOS roadmap and summarize it.</pre>
  </section>
  <section class="panel" style="margin-top:18px">
    <h2>Activity</h2>
    <ul id="activity">{activity_html}</ul>
    <p><a href="/api/status">status JSON</a> · <a href="/api/activity">activity JSON</a></p>
  </section>
</main>
<script>
async function postJSON(url, payload) {{
  const res = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload || {{}})}});
  return await res.json();
}}
function showResult(payload) {{
  const response = payload.response || payload.friendly_error || JSON.stringify(payload, null, 2);
  const meta = [payload.intent, payload.capability, payload.status].filter(Boolean).join(' · ');
  document.getElementById('result').textContent = (meta ? meta + '\\n\\n' : '') + response;
  refreshActivity();
}}
async function runPrompt() {{
  document.getElementById('result').textContent = 'Running prompt...';
  showResult(await postJSON('/api/prompt', {{message: document.getElementById('prompt').value}}));
}}
async function telegramCheck() {{
  document.getElementById('result').textContent = 'Running one Telegram polling preview check...';
  const payload = await postJSON('/api/telegram/check', {{}});
  showResult({{
    response: 'telegram_polling_attempted=' + payload.telegram_polling_attempted + '\\ntelegram_live_update_received=' + payload.telegram_live_update_received + '\\ntelegram_reply_sent=' + payload.telegram_reply_sent + '\\nreason=' + ((payload.proof || {{}}).reason || ''),
    intent: 'telegram_preview',
    capability: 'telegram_polling_check',
    status: (payload.proof || {{}}).ok ? 'completed' : 'degraded'
  }});
}}
async function refreshActivity() {{
  const payload = await (await fetch('/api/activity')).json();
  const rows = payload.events || [];
  document.getElementById('activity').innerHTML = rows.slice(-12).map(e => `<li><b>${{escapeHtml(e.label || 'AgentOS')}}</b> <span>${{escapeHtml(e.time || '')}}</span> ${{escapeHtml(e.human_message || '')}}</li>`).join('') || '<li>No activity yet.</li>';
}}
async function refreshStatus() {{
  const payload = await (await fetch('/api/status')).json();
  document.getElementById('result').textContent = JSON.stringify(payload.runtime?.adapters || payload, null, 2);
  refreshActivity();
}}
function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
setInterval(refreshActivity, 5000);
</script>
</body>
</html>"""


def make_handler(app: DockerPreviewApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentOSDockerPreview/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            if _env_bool("AGENTOS_DOCKER_ACCESS_LOG", False):
                super().log_message(fmt, *args)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/setup", "/activity"}:
                _html_response(self, _render_page(app))
            elif path == "/healthz":
                _json_response(self, {"ok": True, "service": "agentos-docker-preview"})
            elif path == "/api/status":
                _json_response(self, app.status())
            elif path == "/api/product":
                _json_response(self, app.product_layer())
            elif path == "/api/work-inbox":
                _json_response(self, app.work_inbox())
            elif path == "/api/recovery":
                _json_response(self, app.recovery_center())
            elif path == "/api/evidence":
                _json_response(self, app.evidence_dashboard())
            elif path == "/api/activity":
                _json_response(self, app.activity())
            else:
                _json_response(self, {"ok": False, "error": "not_found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = _read_body(self)
            if path == "/api/prompt":
                _json_response(self, app.run_prompt(str(body.get("message", ""))))
            elif path == "/api/telegram/check":
                _json_response(self, app.telegram_check())
            else:
                _json_response(self, {"ok": False, "error": "not_found"}, status=404)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the AgentOS Docker runtime preview")
    parser.add_argument("--host", default=os.environ.get("AGENTOS_DOCKER_PREVIEW_HOST", "0.0.0.0"))
    parser.add_argument("--port", default=os.environ.get("AGENTOS_DOCKER_PREVIEW_PORT", "8787"))
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--user-root", default=os.environ.get("AGENTOS_USER_DATA_ROOT", "./agentos-data/user"))
    parser.add_argument("--telegram-polling", action="store_true", default=_env_bool("AGENTOS_DOCKER_TELEGRAM_POLLING", True))
    parser.add_argument("--telegram-interval", default=os.environ.get("AGENTOS_DOCKER_TELEGRAM_INTERVAL", "10"))
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    user_root = Path(args.user_root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    user_root.mkdir(parents=True, exist_ok=True)

    app = DockerPreviewApp(
        workspace=workspace,
        user_root=user_root,
        telegram_polling=bool(args.telegram_polling),
        telegram_interval=int(args.telegram_interval),
    )
    app.start_background_workers()

    server = ThreadingHTTPServer((args.host, int(args.port)), make_handler(app))
    print(f"AgentOS Docker preview: http://localhost:{args.port}", flush=True)
    print("Docker preview only; this is not ISO/boot proof.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
