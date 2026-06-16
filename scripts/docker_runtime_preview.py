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

    def onboarding_status(self) -> dict:
        steps = [
            {
                "id": "clone_repository",
                "label": "Clone the repository",
                "state": "documented",
                "command": "git clone git@github.com:Jongtae/agentos.git",
            },
            {
                "id": "copy_env",
                "label": "Create local environment file",
                "state": "documented",
                "command": "cp .env.example .env",
            },
            {
                "id": "start_docker_preview",
                "label": "Start Docker runtime preview",
                "state": "ready",
                "command": "docker compose up",
            },
            {
                "id": "open_runtime_home",
                "label": "Open Runtime Home",
                "state": "ready",
                "url": "http://localhost:8787",
            },
            {
                "id": "try_prompt",
                "label": "Try a first prompt",
                "state": "ready",
                "suggested_prompt": "status",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-onboarding-status.v1",
            "surface": "Docker Onboarding Status",
            "state": "ready",
            "customer_message": "Docker onboarding is ready for the public preview path; stronger OS, live, release, and hardware proofs still require observed evidence.",
            "steps": steps,
            "readiness_checklist": [
                {
                    "id": "quickstart_documented",
                    "label": "Quickstart is documented",
                    "state": "ready",
                    "evidence": "README.md",
                    "customer_value": "A customer has the exact clone, env, compose, and browser steps before starting.",
                },
                {
                    "id": "preview_entrypoints_available",
                    "label": "Preview entrypoints are visible",
                    "state": "ready",
                    "evidence": "http://localhost:8787, /api/status, /api/product, /api/onboarding",
                    "customer_value": "A customer can inspect the runtime home and onboarding contract from the running preview.",
                },
                {
                    "id": "basic_preview_no_api_key",
                    "label": "Basic preview does not require an API key",
                    "state": "ready",
                    "evidence": "requires_api_key_for_basic_preview=false",
                    "customer_value": "A customer can open the Docker Product Layer without first configuring live providers.",
                },
                {
                    "id": "docker_validation_available",
                    "label": "Docker-safe validation is available",
                    "state": "ready",
                    "evidence": "scripts/smoke_docker_onboarding_status_contract.sh",
                    "customer_value": "The public try path has a focused smoke that catches onboarding contract drift.",
                },
                {
                    "id": "observed_proof_boundaries_visible",
                    "label": "Observed proof boundaries are visible",
                    "state": "blocked_on_external_evidence",
                    "evidence": "VM/ISO, live OAuth, live browser, release, mutation, and hardware proof are explicit non-claims.",
                    "customer_value": "A customer can tell which claims are proven locally and which require future observed evidence.",
                },
            ],
            "entrypoints": {
                "browser_url": "http://localhost:8787",
                "status_api": "/api/status",
                "product_api": "/api/product",
                "onboarding_api": "/api/onboarding",
                "quickstart_doc": "README.md",
                "acceptance_doc": "docs/acceptance/docker-runtime-preview.md",
            },
            "validation": {
                "quickstart_smoke": "scripts/smoke_docker_customer_onboarding_quickstart.sh",
                "onboarding_status_contract_smoke": "scripts/smoke_docker_onboarding_status_contract.sh",
                "product_layer_completion_smoke": "scripts/smoke_docker_product_layer_completion.sh",
                "docker_runtime_preview_python_smoke": "scripts/smoke_docker_runtime_preview_python.sh",
            },
            "proof": {
                "docker_preview_ready": True,
                "customer_onboarding_ready": True,
                "requires_api_key_for_basic_preview": False,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_proof_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
            },
        }

    def guided_demo_journey(self) -> dict:
        stages = [
            {
                "id": "start_at_runtime_home",
                "label": "Start at Runtime Home",
                "surface": "Runtime Home",
                "state": "ready",
                "entrypoint": "http://localhost:8787",
                "customer_goal": "Confirm the managed runtime is reachable before asking AgentOS to work.",
                "proof_boundary": "Docker proves local preview reachability, not VM/ISO boot ownership.",
            },
            {
                "id": "inspect_work_inbox",
                "label": "Inspect Work Inbox",
                "surface": "Work Inbox",
                "state": "ready",
                "entrypoint": "/api/work-inbox",
                "customer_goal": "See fixture, Maildir, Gmail, and Calendar as read-first sources with live-proof blockers.",
                "proof_boundary": "Live OAuth and external mutations remain unclaimed.",
            },
            {
                "id": "run_first_prompt",
                "label": "Run a first prompt",
                "surface": "Prompt Runner",
                "state": "ready",
                "entrypoint": "/api/prompt",
                "suggested_prompt": "status",
                "customer_goal": "Watch a bounded request flow through intent dispatch and runtime narration.",
                "proof_boundary": "Docker-safe local execution is observed; external provider proof is not claimed.",
            },
            {
                "id": "review_activity_timeline",
                "label": "Review Activity Timeline",
                "surface": "Activity Timeline",
                "state": "ready",
                "entrypoint": "/api/timeline",
                "customer_goal": "Understand what AgentOS received, classified, ran, recorded, and returned.",
                "proof_boundary": "External app execution and live-provider proof remain unclaimed.",
            },
            {
                "id": "check_evidence_and_recovery",
                "label": "Check Evidence and Recovery",
                "surface": "Evidence Dashboard and Recovery Center",
                "state": "ready",
                "entrypoint": "/api/evidence",
                "secondary_entrypoint": "/api/recovery",
                "customer_goal": "Separate observed Docker/local proof from blockers that need credentials, VM/ISO runs, release artifacts, browser evidence, or attestation evidence.",
                "proof_boundary": "Unobserved VM/ISO, live OAuth, browser, release, mutation, and hardware attestation claims stay blocked.",
            },
        ]
        expected_outcomes = [
            {
                "id": "runtime_reachable",
                "label": "Runtime is reachable",
                "kind": "success",
                "surface": "Runtime Home",
                "expected_result": "The preview opens and reports Docker/local runtime readiness.",
                "customer_interpretation": "AgentOS can be tried through the local Product Layer preview.",
            },
            {
                "id": "read_first_work_visible",
                "label": "Read-first work is visible",
                "kind": "success",
                "surface": "Work Inbox",
                "expected_result": "Fixture, Maildir, Gmail, and Calendar sources are listed with safe read-first boundaries.",
                "customer_interpretation": "AgentOS shows how work intake will be owned before live credentials are connected.",
            },
            {
                "id": "activity_and_records_visible",
                "label": "Activity and records are visible",
                "kind": "success",
                "surface": "Activity Timeline",
                "expected_result": "Prompt handling produces customer-readable activity and user-owned record paths.",
                "customer_interpretation": "AgentOS narrates execution instead of hiding work behind raw logs.",
            },
            {
                "id": "proof_boundaries_visible",
                "label": "Proof boundaries are visible",
                "kind": "blocked_until_observed",
                "surface": "Evidence Dashboard",
                "expected_result": "VM/ISO, live OAuth, browser, release, mutation, and hardware attestation claims remain explicit non-claims.",
                "customer_interpretation": "Docker proof is useful but is not being oversold as OS, live-provider, release, or device trust proof.",
            },
            {
                "id": "recovery_next_steps_visible",
                "label": "Recovery next steps are visible",
                "kind": "blocked_until_observed",
                "surface": "Recovery Center",
                "expected_result": "Missing credentials, VM/ISO evidence, release evidence, browser evidence, and attestation evidence are translated into next actions.",
                "customer_interpretation": "AgentOS tells the customer what evidence is still needed before stronger claims can be made.",
            },
        ]
        completion_summary = {
            "id": "docker_guided_demo_complete",
            "label": "Docker guided demo is complete",
            "state": "ready",
            "customer_result": "A customer can complete the Docker Product Layer journey through runtime readiness, read-first work, prompt execution, activity narration, evidence, and recovery.",
            "completed_claims": [
                "Docker/local runtime preview is reachable.",
                "Product Layer surfaces are visible from the running preview.",
                "Prompt handling can be demonstrated through a Docker-safe local path.",
                "Evidence and recovery surfaces explain observed proof and blockers.",
            ],
            "next_blockers": [
                "VM/ISO boot, reboot, recovery, and managed runtime rejoin require observed VM evidence.",
                "Live Gmail or Calendar proof requires explicit tester OAuth credentials and sanitized observed records.",
                "Live browser, release signing/publication, external mutation, and hardware attestation claims require separate observed proof.",
            ],
        }
        return {
            "schema_version": "agentos-product-layer-guided-demo-journey.v1",
            "surface": "Guided Demo Journey",
            "state": "ready",
            "customer_message": "Follow this Docker-safe journey to understand AgentOS Product Layer readiness without confusing local preview proof for OS, live-provider, release, or hardware proof.",
            "stages": stages,
            "expected_outcomes": expected_outcomes,
            "completion_summary": completion_summary,
            "validation": {
                "guided_demo_journey_smoke": "scripts/smoke_docker_guided_demo_journey.sh",
                "product_layer_completion_smoke": "scripts/smoke_docker_product_layer_completion.sh",
                "docker_runtime_preview_python_smoke": "scripts/smoke_docker_runtime_preview_python.sh",
            },
            "proof": {
                "docker_preview_ready": True,
                "customer_guided_journey_ready": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_proof_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
            },
        }

    def product_layer(self, *, setup: dict | None = None, activity: dict | None = None) -> dict:
        setup_payload = setup or build_status(str(self.workspace), str(self.user_root))
        activity_payload = activity or build_activity_feed_payload(self.workspace, limit=12)
        adapters = setup_payload.get("adapters", {}) if isinstance(setup_payload.get("adapters"), dict) else {}
        onboarding_status = self.onboarding_status()
        guided_demo_journey = self.guided_demo_journey()
        work_inbox = self.work_inbox(setup=setup_payload)
        activity_timeline = self.activity_timeline(activity=activity_payload)
        capability_store = self.capability_store()
        approval_center = self.approval_center(capability_store=capability_store)
        proof_uploader = self.observed_proof_uploader()
        release_trust = self.release_trust_panel()
        attestation_status = self.attestation_status()
        recovery_center = self.recovery_center(setup=setup_payload)
        evidence_dashboard = self.evidence_dashboard(setup=setup_payload, activity=activity_payload)
        proof_packet = self.customer_proof_packet(
            onboarding_status=onboarding_status,
            guided_demo_journey=guided_demo_journey,
            evidence_dashboard=evidence_dashboard,
            recovery_center=recovery_center,
        )
        customer_handoff = self.customer_handoff_bundle(
            onboarding_status=onboarding_status,
            guided_demo_journey=guided_demo_journey,
            proof_packet=proof_packet,
            recovery_center=recovery_center,
        )
        proof_promotion = self.proof_promotion_center(
            evidence_dashboard=evidence_dashboard,
            recovery_center=recovery_center,
            proof_packet=proof_packet,
            customer_handoff=customer_handoff,
        )
        product_map = self.product_map()
        blockers = recovery_center.get("blockers", [])
        return {
            "schema_version": "agentos-product-layer-runtime-home.v1",
            "surface": "Docker Runtime Home",
            "customer_message": "AgentOS is ready for local-first runtime preview. Some live proofs still need user-provided evidence.",
            "features": [
                {
                    "id": "onboarding_status",
                    "label": "Docker Onboarding Status",
                    "state": onboarding_status.get("state", "ready"),
                    "customer_value": "Confirm the public quickstart, preview URL, first prompt, and proof boundaries before trying AgentOS.",
                },
                {
                    "id": "guided_demo_journey",
                    "label": "Guided Demo Journey",
                    "state": guided_demo_journey.get("state", "ready"),
                    "customer_value": "Follow the recommended customer path across Runtime Home, Work Inbox, prompt execution, Activity Timeline, Evidence Dashboard, and Recovery Center.",
                },
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
                    "id": "capability_store",
                    "label": "Capability Store",
                    "state": capability_store.get("state", "ready"),
                    "customer_value": "See which capabilities are safe local actions, user-owned writes, external reads, confirmed lifecycle actions, or blocked destructive requests.",
                },
                {
                    "id": "approval_center",
                    "label": "Approval Center",
                    "state": approval_center.get("state", "ready"),
                    "customer_value": "See which actions need user approval, observed proof, or are blocked before AgentOS may perform them.",
                },
                {
                    "id": "observed_proof_uploader",
                    "label": "Observed Proof Uploader",
                    "state": proof_uploader.get("state", "ready"),
                    "customer_value": "See which evidence types can be attached later before live, VM, release, browser, or attestation claims are promoted.",
                },
                {
                    "id": "release_trust_panel",
                    "label": "Release Trust Panel",
                    "state": release_trust.get("state", "blocked"),
                    "customer_value": "See which release artifact, manifest, checksum, signing, publication, and VM proof evidence is still required.",
                },
                {
                    "id": "attestation_status",
                    "label": "Attestation Status",
                    "state": attestation_status.get("state", "blocked"),
                    "customer_value": "See which Secure Boot, TPM/PCR, event-log, IMA, and hardware-backed evidence is still required.",
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
                {
                    "id": "customer_proof_packet",
                    "label": "Customer Proof Packet",
                    "state": proof_packet.get("state", "ready"),
                    "customer_value": "Export the Docker-local proof summary, validation commands, and explicit non-claims in one customer-readable packet.",
                },
                {
                    "id": "customer_handoff_bundle",
                    "label": "Customer Handoff Bundle",
                    "state": customer_handoff.get("state", "ready"),
                    "customer_value": "Share one Docker-safe bundle with the run command, first screens, validation commands, proof packet, and next observed-proof blockers.",
                },
                {
                    "id": "proof_promotion_center",
                    "label": "Proof Promotion Center",
                    "state": proof_promotion.get("state", "ready"),
                    "customer_value": "Decide which Docker-local claims are ready and which stronger claims require sanitized observed evidence before promotion.",
                },
                {
                    "id": "product_map",
                    "label": "Product Layer Map",
                    "state": product_map.get("state", "ready"),
                    "customer_value": "See the recommended customer path across Product Layer surfaces, proof packets, blockers, and trust panels.",
                },
            ],
            "blockers": blockers,
            "onboarding_status": onboarding_status,
            "guided_demo_journey": guided_demo_journey,
            "work_inbox": work_inbox,
            "activity_timeline": activity_timeline,
            "capability_store": capability_store,
            "approval_center": approval_center,
            "observed_proof_uploader": proof_uploader,
            "release_trust_panel": release_trust,
            "attestation_status": attestation_status,
            "recovery_center": recovery_center,
            "evidence_dashboard": evidence_dashboard,
            "customer_proof_packet": proof_packet,
            "customer_handoff_bundle": customer_handoff,
            "proof_promotion_center": proof_promotion,
            "product_map": product_map,
            "proof": {
                "docker_main_try_path": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "customer_facing_summary_ready": True,
            },
        }

    def product_map(self) -> dict:
        surface_groups = [
            {
                "id": "start_here",
                "label": "Start here",
                "customer_goal": "Open the preview, understand readiness, and follow the first guided demo path.",
                "surfaces": [
                    {"id": "runtime_home", "label": "Runtime Home", "endpoint": "/api/product", "state": "ready"},
                    {"id": "onboarding_status", "label": "Docker Onboarding Status", "endpoint": "/api/onboarding", "state": "ready"},
                    {"id": "guided_demo_journey", "label": "Guided Demo Journey", "endpoint": "/api/demo-journey", "state": "ready"},
                ],
            },
            {
                "id": "do_work",
                "label": "Do safe work",
                "customer_goal": "Inspect read-first work, runtime events, capability boundaries, and approval needs.",
                "surfaces": [
                    {"id": "work_inbox", "label": "Work Inbox", "endpoint": "/api/work-inbox", "state": "ready"},
                    {"id": "activity_timeline", "label": "Activity Timeline", "endpoint": "/api/timeline", "state": "ready"},
                    {"id": "capability_store", "label": "Capability Store", "endpoint": "/api/capabilities", "state": "ready"},
                    {"id": "approval_center", "label": "Approval Center", "endpoint": "/api/approvals", "state": "ready"},
                ],
            },
            {
                "id": "prove_and_handoff",
                "label": "Prove and hand off",
                "customer_goal": "Collect Docker-local evidence, share safe proof, and keep stronger claims blocked.",
                "surfaces": [
                    {"id": "evidence_dashboard", "label": "Evidence Dashboard", "endpoint": "/api/evidence", "state": "ready"},
                    {"id": "customer_proof_packet", "label": "Customer Proof Packet", "endpoint": "/api/proof-packet", "state": "ready"},
                    {"id": "customer_handoff_bundle", "label": "Customer Handoff Bundle", "endpoint": "/api/customer-handoff", "state": "ready"},
                    {"id": "proof_promotion_center", "label": "Proof Promotion Center", "endpoint": "/api/proof-promotion", "state": "ready"},
                ],
            },
            {
                "id": "blocked_until_observed",
                "label": "Blocked until observed",
                "customer_goal": "Understand recovery, release, and device-trust claims that require external observed evidence.",
                "surfaces": [
                    {"id": "recovery_center", "label": "Recovery Center", "endpoint": "/api/recovery", "state": "attention"},
                    {"id": "observed_proof_uploader", "label": "Observed Proof Uploader", "endpoint": "/api/proofs", "state": "ready"},
                    {"id": "release_trust_panel", "label": "Release Trust Panel", "endpoint": "/api/release-trust", "state": "blocked"},
                    {"id": "attestation_status", "label": "Attestation Status", "endpoint": "/api/attestation", "state": "blocked"},
                ],
            },
        ]
        reviewer_routes = [
            {
                "id": "runtime_evaluator",
                "label": "Runtime evaluator",
                "customer_goal": "Confirm the Docker runtime is reachable and the guided path is visible.",
                "route": [
                    "runtime_home",
                    "onboarding_status",
                    "guided_demo_journey",
                    "activity_timeline",
                    "recovery_center",
                ],
                "claim_boundary": "Docker preview only; not VM/ISO boot or install proof.",
            },
            {
                "id": "proof_reviewer",
                "label": "Proof reviewer",
                "customer_goal": "Check local proof sources, handoff material, and claim promotion boundaries.",
                "route": [
                    "evidence_dashboard",
                    "customer_proof_packet",
                    "customer_handoff_bundle",
                    "proof_promotion_center",
                ],
                "claim_boundary": "Share Docker-local claims only; stronger claims require sanitized observed evidence.",
            },
            {
                "id": "capability_reviewer",
                "label": "Capability reviewer",
                "customer_goal": "Inspect read-first work, permission boundaries, and approval requirements.",
                "route": [
                    "work_inbox",
                    "capability_store",
                    "approval_center",
                    "activity_timeline",
                ],
                "claim_boundary": "Does not claim external writes, live provider execution, or destructive actions.",
            },
            {
                "id": "trust_reviewer",
                "label": "Trust reviewer",
                "customer_goal": "Review blocked release, VM/ISO, browser, and attestation evidence requirements.",
                "route": [
                    "observed_proof_uploader",
                    "release_trust_panel",
                    "attestation_status",
                    "recovery_center",
                ],
                "claim_boundary": "No release, browser, VM/ISO, or hardware trust proof is claimed.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-map.v1",
            "surface": "Product Layer Map",
            "state": "ready",
            "customer_message": "Product Layer Map gives customers one ordered path and reviewer-specific routes through AgentOS Docker preview surfaces without turning Docker proof into VM/ISO, live provider, release, mutation, or attestation proof.",
            "surface_groups": surface_groups,
            "reviewer_routes": reviewer_routes,
            "recommended_path": [
                "runtime_home",
                "onboarding_status",
                "guided_demo_journey",
                "work_inbox",
                "activity_timeline",
                "evidence_dashboard",
                "customer_proof_packet",
                "customer_handoff_bundle",
                "proof_promotion_center",
                "recovery_center",
            ],
            "proof": {
                "customer_facing_product_map_ready": True,
                "docker_main_try_path": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
            },
        }

    def customer_handoff_bundle(
        self,
        *,
        onboarding_status: dict | None = None,
        guided_demo_journey: dict | None = None,
        proof_packet: dict | None = None,
        recovery_center: dict | None = None,
    ) -> dict:
        onboarding = onboarding_status or self.onboarding_status()
        journey = guided_demo_journey or self.guided_demo_journey()
        packet = proof_packet or self.customer_proof_packet()
        recovery = recovery_center or self.recovery_center()
        next_blockers = recovery.get("items", []) if isinstance(recovery.get("items"), list) else []
        handoff_checklist = [
            {
                "id": "run_preview",
                "label": "Run the Docker preview",
                "state": "ready",
                "customer_action": "Start the public try path with docker compose up --build.",
                "proof_boundary": "Proves only that the Docker-local preview can be started when Docker is available.",
            },
            {
                "id": "open_runtime_home",
                "label": "Open Runtime Home",
                "state": "ready",
                "customer_action": "Open http://localhost:8787 and confirm Runtime Home loads before trying a prompt.",
                "proof_boundary": "Does not prove ISO boot, install, reboot, recovery, or managed runtime rejoin.",
            },
            {
                "id": "inspect_guided_path",
                "label": "Inspect the guided path",
                "state": "ready",
                "customer_action": "Review onboarding, Guided Demo Journey, Evidence Dashboard, Recovery Center, and Customer Proof Packet.",
                "proof_boundary": "Keeps live OAuth, browser, release, mutation, and attestation proof unclaimed.",
            },
            {
                "id": "run_validation_commands",
                "label": "Run validation commands",
                "state": "ready",
                "customer_action": "Run the listed smoke commands to reproduce Docker-safe proof locally.",
                "proof_boundary": "Full Docker smoke requires an available Docker daemon; VM/ISO proof still requires observed VM evidence.",
            },
            {
                "id": "record_remaining_blockers",
                "label": "Record remaining proof blockers",
                "state": "blocked_until_observed_evidence",
                "customer_action": "Attach sanitized observed evidence before promoting VM/ISO, live OAuth, browser, release, mutation, or attestation claims.",
                "proof_boundary": "The handoff bundle never auto-promotes stronger claims.",
            },
        ]
        handoff_report = {
            "schema_version": "agentos-product-layer-customer-handoff-report.v1",
            "title": "Docker customer handoff report",
            "audience": "customer evaluator or internal product reviewer",
            "summary": "A shareable Docker-local report that explains what was run, what can be inspected, which local proof was reproduced, and which stronger claims remain blocked until observed evidence exists.",
            "sections": [
                {
                    "id": "reproduced_try_path",
                    "label": "Reproduced try path",
                    "state": "ready",
                    "customer_value": "Records the Docker command, browser URL, and first prompt a reviewer used.",
                    "source": "try_path",
                },
                {
                    "id": "inspected_product_surfaces",
                    "label": "Inspected Product Layer surfaces",
                    "state": "ready",
                    "customer_value": "Lists Runtime Home, onboarding, guided demo, proof packet, recovery, and evidence surfaces.",
                    "source": "inspect_surfaces",
                },
                {
                    "id": "local_validation_evidence",
                    "label": "Local validation evidence",
                    "state": "ready",
                    "customer_value": "Names Docker-safe validation commands a reviewer can rerun before trusting the handoff.",
                    "source": "validation_commands",
                },
                {
                    "id": "remaining_observed_proof_blockers",
                    "label": "Remaining observed-proof blockers",
                    "state": "blocked_until_observed_evidence",
                    "customer_value": "Keeps VM/ISO, live OAuth, browser, release, mutation, Docker daemon observed proof, and attestation out of completed claims.",
                    "source": "next_blockers",
                },
                {
                    "id": "share_safe_non_claims",
                    "label": "Share-safe non-claims",
                    "state": "ready",
                    "customer_value": "States that secrets are forbidden and stronger claims require sanitized observed evidence.",
                    "source": "proof",
                },
            ],
            "share_policy": {
                "safe_to_share_without_secrets": True,
                "secret_material_allowed": False,
                "automatic_claim_promotion": False,
                "requires_sanitized_observed_evidence_for_stronger_claims": True,
            },
        }
        return {
            "schema_version": "agentos-product-layer-customer-handoff-bundle.v1",
            "surface": "Customer Handoff Bundle",
            "state": "ready",
            "customer_message": "Customer Handoff Bundle gives a Docker-safe path to run, inspect, validate, and explain AgentOS without claiming stronger observed proof.",
            "try_path": {
                "command": "docker compose up --build",
                "url": "http://localhost:8787",
                "first_prompt": "status",
                "docker_is_default_public_try_path": True,
            },
            "handoff_checklist": handoff_checklist,
            "handoff_report": handoff_report,
            "inspect_surfaces": [
                {"id": "runtime_home", "label": "Runtime Home", "url": "/api/product"},
                {"id": "onboarding_status", "label": "Docker Onboarding Status", "url": "/api/onboarding"},
                {"id": "guided_demo_journey", "label": "Guided Demo Journey", "url": "/api/demo-journey"},
                {"id": "customer_proof_packet", "label": "Customer Proof Packet", "url": "/api/proof-packet"},
                {"id": "recovery_center", "label": "Recovery Center", "url": "/api/recovery"},
                {"id": "evidence_dashboard", "label": "Evidence Dashboard", "url": "/api/evidence"},
            ],
            "validation_commands": [
                "docker compose config",
                "scripts/smoke_docker_customer_handoff_bundle.sh",
                "scripts/smoke_docker_runtime_preview_python.sh",
                "scripts/smoke_docker_product_layer_completion.sh",
                "scripts/smoke_phase2_golden_demo.sh",
            ],
            "handoff_sources": {
                "onboarding_status": onboarding.get("schema_version"),
                "guided_demo_journey": journey.get("schema_version"),
                "customer_proof_packet": packet.get("schema_version"),
                "recovery_center": recovery.get("schema_version"),
            },
            "next_blockers": next_blockers,
            "proof": {
                "docker_main_try_path": True,
                "customer_handoff_ready": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
            },
        }

    def proof_promotion_center(
        self,
        *,
        evidence_dashboard: dict | None = None,
        recovery_center: dict | None = None,
        proof_packet: dict | None = None,
        customer_handoff: dict | None = None,
    ) -> dict:
        evidence = evidence_dashboard or self.evidence_dashboard()
        recovery = recovery_center or self.recovery_center()
        packet = proof_packet or self.customer_proof_packet()
        handoff = customer_handoff or self.customer_handoff_bundle()
        promotion_decisions = [
            {
                "id": "docker-local-product-layer",
                "label": "Docker-local Product Layer",
                "state": "ready_to_describe",
                "customer_decision": "Use Docker preview proof to evaluate Runtime Home, Work Inbox, Activity Timeline, Recovery Center, Evidence Dashboard, proof packet, and handoff bundle.",
                "required_evidence": [
                    "scripts/smoke_docker_runtime_preview_python.sh",
                    "scripts/smoke_docker_product_layer_completion.sh",
                    "scripts/smoke_docker_customer_handoff_bundle.sh",
                ],
                "promotion_boundary": "May be described as Docker-local Product Layer proof only.",
            },
            {
                "id": "docker-daemon-observed-run",
                "label": "Docker daemon observed run",
                "state": "blocked_until_observed_docker_daemon",
                "customer_decision": "Promote Docker preview from Python-local smoke to observed Docker daemon run only after a real daemon-backed smoke is captured.",
                "required_evidence": ["scripts/smoke_docker_runtime_preview.sh"],
                "promotion_boundary": "Still does not prove VM/ISO boot, live providers, release signing, mutation, or attestation.",
            },
            {
                "id": "vm-iso-runtime-ownership",
                "label": "VM/ISO runtime ownership",
                "state": "blocked_until_observed_vm_iso",
                "customer_decision": "Promote OS boot/rejoin claims only after observed VM/ISO boot, recovery, and managed runtime rejoin evidence exists.",
                "required_evidence": ["docs/acceptance/vm-iso-proof-preflight.md", "sanitized observed VM run record"],
                "promotion_boundary": "Docker proof must not be reused as boot ownership proof.",
            },
            {
                "id": "live-provider-readonly",
                "label": "Live provider read-only proof",
                "state": "blocked_until_live_credentials",
                "customer_decision": "Promote Gmail or Calendar live proof only after explicit tester OAuth credentials and sanitized read-only observed records exist.",
                "required_evidence": [
                    "docs/acceptance/gmail-live-readonly-acceptance.md",
                    "docs/acceptance/calendar-live-readonly-acceptance.md",
                ],
                "promotion_boundary": "Does not permit send/delete/archive/calendar mutations.",
            },
            {
                "id": "live-browser-release-attestation",
                "label": "Browser, release, and attestation proof",
                "state": "blocked_until_specialized_observed_evidence",
                "customer_decision": "Promote live browser, release trust, or hardware trust claims only with their own sanitized observed evidence.",
                "required_evidence": [
                    "browser observed acceptance record",
                    "release artifact, checksum, signing, and publication record",
                    "Secure Boot, TPM/PCR, event-log, IMA, or hardware attestation record",
                ],
                "promotion_boundary": "No automatic promotion from Docker-local proof.",
            },
        ]
        sharing_checklist = [
            {
                "id": "describe_docker_local_product_layer",
                "label": "Describe Docker-local Product Layer",
                "state": "share_ready",
                "customer_guidance": "Safe to say the Docker preview exposes the customer Product Layer surfaces and local smoke-verified proof boundaries.",
                "allowed_claim": "Docker-local Product Layer preview is ready for customer inspection.",
                "blocked_claim": "Do not describe this as VM/ISO boot ownership, installer proof, or production release proof.",
            },
            {
                "id": "include_validation_commands",
                "label": "Include validation commands",
                "state": "share_ready",
                "customer_guidance": "Share the Docker-safe validation commands that reproduced the local preview proof.",
                "allowed_claim": "Local proof is backed by the listed Docker-safe smokes and compose config.",
                "blocked_claim": "Do not imply full Docker daemon proof if the daemon smoke was skipped or unavailable.",
            },
            {
                "id": "attach_source_surfaces",
                "label": "Attach source surfaces",
                "state": "share_ready",
                "customer_guidance": "Point reviewers to Evidence Dashboard, Recovery Center, Customer Proof Packet, Customer Handoff Bundle, and this Promotion Center.",
                "allowed_claim": "The claim is traceable to customer-visible Product Layer surfaces.",
                "blocked_claim": "Do not rely on hidden logs or private credentials as customer-facing proof.",
            },
            {
                "id": "withhold_stronger_claims",
                "label": "Withhold stronger claims",
                "state": "blocked_until_observed_evidence",
                "customer_guidance": "Hold Docker daemon, VM/ISO, live OAuth, browser, release, mutation, and attestation claims until sanitized observed evidence exists.",
                "allowed_claim": "Stronger claims are explicitly blocked pending observed evidence.",
                "blocked_claim": "Do not auto-promote Docker-local proof into stronger runtime, release, or hardware trust claims.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-proof-promotion-center.v1",
            "surface": "Proof Promotion Center",
            "state": "ready",
            "customer_message": "Proof Promotion Center turns Docker-local proof into clear customer decisions about what can be described now and what still needs observed evidence.",
            "promotion_decisions": promotion_decisions,
            "sharing_checklist": sharing_checklist,
            "source_surfaces": {
                "evidence_dashboard": evidence.get("schema_version"),
                "recovery_center": recovery.get("schema_version"),
                "customer_proof_packet": packet.get("schema_version"),
                "customer_handoff_bundle": handoff.get("schema_version"),
            },
            "share_policy": {
                "secret_material_allowed": False,
                "automatic_claim_promotion": False,
                "requires_sanitized_observed_evidence_for_stronger_claims": True,
            },
            "proof": {
                "docker_local_claims_ready": True,
                "docker_daemon_observed_claimed": False,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
                "customer_facing_proof_promotion_ready": True,
            },
        }

    def attestation_status(self) -> dict:
        checks = [
            {
                "id": "secure-boot-state",
                "label": "Secure Boot state",
                "state": "blocked_until_observed_boot_chain",
                "customer_value": "Requires observed firmware or bootloader evidence before Secure Boot trust is claimed.",
            },
            {
                "id": "tpm-pcr-evidence",
                "label": "TPM/PCR evidence",
                "state": "blocked_until_tpm_measurements",
                "customer_value": "Requires TPM-backed measurements or equivalent attestation evidence before measured boot is claimed.",
            },
            {
                "id": "event-log-review",
                "label": "Event-log review",
                "state": "blocked_until_event_log",
                "customer_value": "Requires sanitized boot event logs before boot-chain integrity is promoted.",
            },
            {
                "id": "ima-runtime-integrity",
                "label": "IMA/runtime integrity",
                "state": "blocked_until_runtime_integrity_evidence",
                "customer_value": "Requires Linux IMA or equivalent runtime integrity evidence before runtime attestation is claimed.",
            },
            {
                "id": "hardware-backed-attestation",
                "label": "Hardware-backed attestation",
                "state": "blocked_until_device_evidence",
                "customer_value": "Requires real VM or hardware evidence before device-level trust is promoted.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-attestation-status.v1",
            "surface": "Attestation Status",
            "state": "blocked",
            "customer_message": "Attestation Status shows boot-chain and hardware trust evidence that Docker cannot prove.",
            "checks": checks,
            "boundary": {
                "boundary_doc": "docs/architecture/verified-boot-attestation-proof-boundary.md",
                "status_artifact": "agentos-verified-boot-attestation-nonclaim.v1",
                "docker_is_attestation_proof": False,
            },
            "proof": {
                "docker_preview_ready": True,
                "secure_boot_observed": False,
                "tpm_pcr_observed": False,
                "event_log_observed": False,
                "ima_runtime_integrity_observed": False,
                "hardware_attestation_observed": False,
                "customer_facing_attestation_status_ready": True,
            },
        }

    def release_trust_panel(self) -> dict:
        checks = [
            {
                "id": "artifact-manifest",
                "label": "Release artifact manifest",
                "state": "blocked_until_release_artifact",
                "customer_value": "Requires an actual release artifact and identity manifest before release freshness is claimed.",
            },
            {
                "id": "checksum-publication",
                "label": "Checksum publication",
                "state": "blocked_until_checksum",
                "customer_value": "Requires published checksums that match each release artifact.",
            },
            {
                "id": "signing-evidence",
                "label": "Signing evidence",
                "state": "blocked_until_signature_or_unsigned_statement",
                "customer_value": "Requires signing proof or an explicit unsigned-preview statement before trust is promoted.",
            },
            {
                "id": "secret-free-review",
                "label": "Secret-free artifact review",
                "state": "blocked_until_artifact_review",
                "customer_value": "Requires artifact review that confirms no secrets or local-only proof are bundled.",
            },
            {
                "id": "vm-iso-release-proof",
                "label": "VM/ISO release proof",
                "state": "blocked_until_observed_vm_run",
                "customer_value": "Requires an observed VM/ISO run before boot, installer, recovery, or rejoin claims are promoted.",
            },
        ]
        readiness_checklist = [
            {
                "id": "local_preflight_available",
                "label": "Local preflight is available",
                "state": "ready",
                "customer_value": "Customers can run local manifest/checksum preflight before discussing any release package.",
                "validation": "scripts/release_manifest_checksum_preflight.py",
            },
            {
                "id": "artifact_manifest_required",
                "label": "Artifact manifest required",
                "state": "blocked_until_release_artifact",
                "customer_value": "Release freshness remains blocked until a real artifact manifest exists.",
                "validation": "Attach the release artifact manifest before promoting release freshness.",
            },
            {
                "id": "checksum_publication_required",
                "label": "Checksum publication required",
                "state": "blocked_until_checksum",
                "customer_value": "Release integrity remains blocked until published checksums match real artifacts.",
                "validation": "Publish and verify checksums for each release artifact.",
            },
            {
                "id": "signing_or_unsigned_statement_required",
                "label": "Signing or unsigned-preview statement required",
                "state": "blocked_until_signature_or_unsigned_statement",
                "customer_value": "Trust language must say whether the preview is signed or explicitly unsigned.",
                "validation": "Attach signing evidence or a clear unsigned-preview statement.",
            },
            {
                "id": "vm_iso_release_proof_required",
                "label": "VM/ISO release proof required",
                "state": "blocked_until_observed_vm_run",
                "customer_value": "Boot, installer, recovery, and rejoin claims require observed VM/ISO evidence.",
                "validation": "Attach sanitized VM/ISO boot, recovery, and managed runtime rejoin evidence.",
            },
        ]
        customer_decisions = [
            {
                "id": "describe_local_preflight_only",
                "label": "Describe local preflight only",
                "state": "share_ready",
                "customer_guidance": "Safe to say Docker preview exposes release trust requirements and local preflight hooks.",
                "allowed_claim": "Release trust requirements are customer-visible in the Docker preview.",
                "blocked_claim": "Do not claim release artifacts, signing, publication, or VM/ISO release proof.",
            },
            {
                "id": "withhold_release_readiness",
                "label": "Withhold release readiness",
                "state": "blocked_until_release_evidence",
                "customer_guidance": "Hold release-ready language until artifact, checksum, signing or unsigned-preview, secret review, and VM/ISO evidence exist.",
                "allowed_claim": "Release readiness is blocked on observed release evidence.",
                "blocked_claim": "Do not present Docker preview proof as release readiness.",
            },
            {
                "id": "route_to_observed_proof",
                "label": "Route stronger claims to observed proof",
                "state": "blocked_until_observed_evidence",
                "customer_guidance": "Use Observed Proof Uploader and Proof Promotion Center before stronger release, browser, VM/ISO, or attestation claims are shared.",
                "allowed_claim": "Stronger claims have named evidence routes.",
                "blocked_claim": "Do not auto-promote local preflight into stronger proof.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-release-trust-panel.v1",
            "surface": "Release Trust Panel",
            "state": "blocked",
            "customer_message": "Release Trust Panel separates local packaging preflight from real release, signing, checksum, and VM/ISO proof.",
            "checks": checks,
            "readiness_checklist": readiness_checklist,
            "customer_decisions": customer_decisions,
            "preflight": {
                "local_manifest_checksum_preflight_available": True,
                "preflight_script": "scripts/release_manifest_checksum_preflight.py",
                "boundary_doc": "docs/operations/distribution-packaging-proof-boundary.md",
            },
            "proof": {
                "docker_preview_ready": True,
                "release_artifact_observed": False,
                "manifest_validated": False,
                "checksum_published": False,
                "signing_observed": False,
                "release_uploaded": False,
                "vm_iso_release_proof_completed": False,
                "customer_facing_release_trust_ready": True,
            },
        }

    def observed_proof_uploader(self) -> dict:
        proof_types = [
            {
                "id": "live-oauth-readonly",
                "label": "Live OAuth read-only proof",
                "state": "awaiting_external_evidence",
                "accepted_evidence": ["provider", "scope", "sanitized transcript", "redacted artifact path", "reviewer note"],
                "customer_value": "Promotes Gmail or Calendar read-only claims only after explicit credentials and sanitized observed evidence exist.",
            },
            {
                "id": "vm-iso-boot-rejoin",
                "label": "VM/ISO boot and rejoin proof",
                "state": "awaiting_external_evidence",
                "accepted_evidence": ["vm runner", "boot log", "reboot/recovery observation", "managed runtime rejoin observation"],
                "customer_value": "Promotes OS boot, recovery, and managed runtime rejoin claims only after a real VM run is observed.",
            },
            {
                "id": "live-browser-observed",
                "label": "Live browser observed proof",
                "state": "awaiting_user_approved_run",
                "accepted_evidence": ["target", "approval note", "sanitized screenshots or transcript", "fallback contract result"],
                "customer_value": "Promotes browser fallback claims only after a user-approved live browser run is observed.",
            },
            {
                "id": "release-trust",
                "label": "Release trust proof",
                "state": "awaiting_release_evidence",
                "accepted_evidence": ["artifact manifest", "checksum", "signature", "release signoff"],
                "customer_value": "Promotes release trust claims only after real release artifacts and signing/checksum evidence exist.",
            },
            {
                "id": "hardware-attestation",
                "label": "Hardware attestation proof",
                "state": "awaiting_hardware_evidence",
                "accepted_evidence": ["Secure Boot state", "TPM/PCR evidence", "event log", "IMA or equivalent attestation"],
                "customer_value": "Promotes hardware trust claims only after device-backed attestation evidence exists.",
            },
        ]
        return {
            "schema_version": "agentos-product-layer-observed-proof-uploader.v1",
            "surface": "Observed Proof Uploader",
            "state": "ready",
            "customer_message": "Observed Proof Uploader defines the evidence AgentOS needs before stronger live, VM, browser, release, or attestation claims can be promoted.",
            "proof_types": proof_types,
            "mock_submission_contract": {
                "required_fields": ["proof_type", "observed_at", "sanitized_artifact_ref", "reviewer_note"],
                "secret_material_allowed": False,
                "claim_promotion_automatic": False,
            },
            "proof": {
                "docker_preview_ready": True,
                "mock_contract_ready": True,
                "file_upload_execution_claimed": False,
                "claim_promotion_claimed": False,
                "secret_material_allowed": False,
                "customer_facing_proof_uploader_ready": True,
            },
        }

    def approval_center(self, *, capability_store: dict | None = None) -> dict:
        store = capability_store or self.capability_store()
        capabilities = store.get("capabilities", []) if isinstance(store.get("capabilities"), list) else []
        approval_items = []
        for item in capabilities:
            if not isinstance(item, dict):
                continue
            permission = str(item.get("permission_level", "unsupported"))
            if permission not in {"external_read", "external_write_confirmed", "lifecycle_confirmed", "destructive_blocked"}:
                continue
            approval_items.append(
                {
                    "id": str(item.get("id", "capability")),
                    "label": str(item.get("label", item.get("id", "Capability"))),
                    "permission_level": permission,
                    "state": _approval_state(permission),
                    "approval_requirement": _approval_requirement(permission),
                    "customer_value": str(item.get("customer_value", "")),
                }
            )
        return {
            "schema_version": "agentos-product-layer-approval-center.v1",
            "surface": "Approval Center",
            "state": "attention" if approval_items else "ready",
            "customer_message": "Approval Center shows actions that need user confirmation, observed proof, or must remain blocked before AgentOS may perform them.",
            "items": approval_items,
            "proof": {
                "docker_preview_ready": True,
                "approval_records_ready": True,
                "approval_execution_claimed": False,
                "destructive_action_executed_by_default": False,
                "external_write_claimed": False,
                "live_provider_proof_claimed": False,
                "customer_facing_approval_center_ready": True,
            },
        }

    def capability_store(self) -> dict:
        registry = _read_capability_registry()
        raw_capabilities = registry.get("capabilities", {}) if isinstance(registry.get("capabilities"), dict) else {}
        capabilities = []
        for capability_id, entry in sorted(raw_capabilities.items()):
            details = entry if isinstance(entry, dict) else {}
            permission = str(details.get("permission_level", "unsupported"))
            capabilities.append(
                {
                    "id": str(capability_id),
                    "label": str(capability_id).replace("_", " ").title(),
                    "permission_level": permission,
                    "state": _capability_store_state(permission),
                    "customer_value": _capability_customer_value(str(capability_id), permission),
                }
            )
        permission_levels = registry.get("permission_levels", []) if isinstance(registry.get("permission_levels"), list) else []
        return {
            "schema_version": "agentos-product-layer-capability-store.v1",
            "surface": "Capability Store",
            "state": "ready" if capabilities else "degraded",
            "customer_message": "Capability Store shows what AgentOS can do locally, what needs confirmation, and what remains blocked.",
            "permission_levels": permission_levels,
            "capabilities": capabilities,
            "defaults": registry.get("defaults", {}) if isinstance(registry.get("defaults"), dict) else {},
            "proof": {
                "docker_preview_ready": True,
                "registry_loaded": bool(capabilities),
                "destructive_action_executed_by_default": False,
                "external_write_claimed": False,
                "live_provider_proof_claimed": False,
                "customer_facing_capability_store_ready": bool(capabilities),
            },
        }

    def activity_timeline(self, *, activity: dict | None = None) -> dict:
        activity_payload = activity or build_activity_feed_payload(self.workspace, limit=40)
        raw_events = activity_payload.get("events", []) if isinstance(activity_payload.get("events"), list) else []
        timeline_events = []
        for event in raw_events[-12:]:
            if not isinstance(event, dict):
                continue
            timeline_events.append(
                {
                    "id": str(event.get("request_id") or event.get("timestamp_utc") or event.get("kind") or "event"),
                    "time": str(event.get("time", "")),
                    "kind": str(event.get("kind", "")),
                    "label": str(event.get("label", "AgentOS")),
                    "message": str(event.get("human_message", "")),
                    "intent": str(event.get("intent", "")),
                    "capability": str(event.get("capability", "")),
                    "request_id": str(event.get("request_id", "")),
                }
            )
        return {
            "schema_version": "agentos-product-layer-activity-timeline.v1",
            "surface": "Activity Timeline",
            "state": "ready" if activity_payload.get("activity_feed_ready") else "degraded",
            "customer_message": "Activity Timeline shows what AgentOS received, classified, ran, completed, blocked, or recovered in this runtime.",
            "events": timeline_events,
            "summary": {
                "activity_feed_ready": bool(activity_payload.get("activity_feed_ready")),
                "event_count": int(activity_payload.get("event_count", len(raw_events)) or 0),
                "latest_human_message": str(
                    activity_payload.get("summary", {}).get("latest_human_message", "")
                    if isinstance(activity_payload.get("summary"), dict)
                    else ""
                ),
            },
            "records": activity_payload.get("artifacts", {}) if isinstance(activity_payload.get("artifacts"), dict) else {},
            "proof": {
                "docker_preview_ready": True,
                "user_visible_records_ready": True,
                "external_app_execution_claimed": False,
                "live_provider_proof_claimed": False,
                "customer_facing_timeline_ready": True,
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

    def customer_proof_packet(
        self,
        *,
        onboarding_status: dict | None = None,
        guided_demo_journey: dict | None = None,
        evidence_dashboard: dict | None = None,
        recovery_center: dict | None = None,
    ) -> dict:
        onboarding = onboarding_status or self.onboarding_status()
        journey = guided_demo_journey or self.guided_demo_journey()
        evidence = evidence_dashboard or self.evidence_dashboard()
        recovery = recovery_center or self.recovery_center()
        completed_claims = [
            {
                "id": "docker-runtime-preview-ready",
                "label": "Docker runtime preview is ready",
                "evidence_source": "docker compose config and scripts/smoke_docker_runtime_preview_python.sh",
            },
            {
                "id": "product-layer-surfaces-ready",
                "label": "Product Layer surfaces are customer-visible",
                "evidence_source": "scripts/smoke_docker_product_layer_completion.sh",
            },
            {
                "id": "guided-demo-path-ready",
                "label": "Guided demo path, outcomes, and completion summary are available",
                "evidence_source": "scripts/smoke_docker_guided_demo_journey.sh",
            },
            {
                "id": "golden-runtime-loop-ready",
                "label": "Golden runtime loop remains Docker/local smoke-verifiable",
                "evidence_source": "scripts/smoke_phase2_golden_demo.sh",
            },
        ]
        validation_commands = [
            "docker compose config",
            "scripts/smoke_docker_runtime_preview_python.sh",
            "scripts/smoke_docker_product_layer_completion.sh",
            "scripts/smoke_docker_guided_demo_journey.sh",
            "scripts/smoke_phase2_golden_demo.sh",
        ]
        readiness_checklist = [
            {
                "id": "completed_claims_present",
                "label": "Completed Docker-local claims are present",
                "state": "ready",
                "customer_value": "The packet lists Docker-local claims backed by smoke-verifiable evidence.",
            },
            {
                "id": "validation_commands_present",
                "label": "Validation commands are present",
                "state": "ready",
                "customer_value": "The packet lists commands a customer or maintainer can run to reproduce local proof.",
            },
            {
                "id": "proof_sources_linked",
                "label": "Proof sources are linked",
                "state": "ready",
                "customer_value": "The packet links onboarding, guided demo, Evidence Dashboard, and Recovery Center contracts.",
            },
            {
                "id": "non_claims_explicit",
                "label": "Non-claims are explicit",
                "state": "blocked_until_observed_evidence",
                "customer_value": "VM/ISO, live OAuth, browser, release, mutation, and attestation proof stay blocked until observed evidence exists.",
            },
            {
                "id": "automatic_claim_promotion_disabled",
                "label": "Automatic claim promotion is disabled",
                "state": "ready_protected",
                "customer_value": "Observed evidence can inform future proof promotion, but this packet does not auto-promote stronger claims.",
            },
        ]
        non_claims = evidence.get("non_claims", []) if isinstance(evidence.get("non_claims"), list) else []
        blockers = recovery.get("items", []) if isinstance(recovery.get("items"), list) else []
        return {
            "schema_version": "agentos-product-layer-customer-proof-packet.v1",
            "surface": "Customer Proof Packet",
            "state": "ready",
            "customer_message": "Customer Proof Packet summarizes what Docker/local proof supports today and which stronger claims still require observed evidence.",
            "completed_claims": completed_claims,
            "validation_commands": validation_commands,
            "readiness_checklist": readiness_checklist,
            "proof_sources": {
                "onboarding_status": onboarding.get("schema_version"),
                "guided_demo_journey": journey.get("schema_version"),
                "evidence_dashboard": evidence.get("schema_version"),
                "recovery_center": recovery.get("schema_version"),
            },
            "non_claims": non_claims,
            "next_blockers": blockers,
            "proof": {
                "docker_preview_ready": True,
                "customer_packet_ready": True,
                "shareable_summary_ready": True,
                "boot_or_iso_proof_claimed": False,
                "live_oauth_claimed": False,
                "live_browser_proof_claimed": False,
                "release_trust_claimed": False,
                "external_mutation_claimed": False,
                "hardware_attestation_claimed": False,
                "claim_promotion_automatic": False,
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


def _read_capability_registry() -> dict:
    path = ROOT_DIR / "docs" / "architecture" / "capability-permission-registry.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _capability_store_state(permission: str) -> str:
    if permission in {"safe_read", "safe_write_user_owned"}:
        return "docker_preview_ready"
    if permission in {"external_read", "external_write_confirmed", "lifecycle_confirmed"}:
        return "requires_setup_or_confirmation"
    if permission in {"destructive_blocked", "unsupported"}:
        return "blocked"
    return "unknown"


def _capability_customer_value(capability_id: str, permission: str) -> str:
    if permission == "safe_read":
        return "Available as a local read-only runtime capability."
    if permission == "safe_write_user_owned":
        return "Can write only to user-owned AgentOS records or workspace paths."
    if permission == "external_read":
        return "Requires setup or observed provider proof before claiming live external access."
    if permission == "external_write_confirmed":
        return "Requires explicit confirmation and future observed proof before external writes are claimed."
    if permission == "lifecycle_confirmed":
        return "Requires confirmation and observed runtime/OS proof before lifecycle behavior is claimed."
    if permission == "destructive_blocked":
        return "Blocked by default; Docker preview must not execute this destructive action."
    return f"{capability_id} is not supported by default in this preview."


def _approval_state(permission: str) -> str:
    if permission == "external_read":
        return "needs_setup_or_observed_proof"
    if permission == "external_write_confirmed":
        return "needs_explicit_confirmation"
    if permission == "lifecycle_confirmed":
        return "needs_lifecycle_confirmation"
    if permission == "destructive_blocked":
        return "blocked"
    return "not_required"


def _approval_requirement(permission: str) -> str:
    if permission == "external_read":
        return "Requires provider setup, explicit user credentials, and observed read-only proof before live access is claimed."
    if permission == "external_write_confirmed":
        return "Requires explicit user confirmation and future observed proof before any external write is claimed."
    if permission == "lifecycle_confirmed":
        return "Requires explicit confirmation and observed runtime or OS proof before lifecycle behavior is claimed."
    if permission == "destructive_blocked":
        return "Blocked by default; this preview must not execute the destructive action."
    return "No approval required in this preview."


def _render_page(app: DockerPreviewApp) -> str:
    status = scrub_payload(app.status())
    adapters = status.get("runtime", {}).get("adapters", {})
    activity = status.get("activity", {}).get("events", [])
    product_layer = status.get("product_layer", {})
    onboarding_status = product_layer.get("onboarding_status", {}) if isinstance(product_layer.get("onboarding_status"), dict) else {}
    guided_demo_journey = product_layer.get("guided_demo_journey", {}) if isinstance(product_layer.get("guided_demo_journey"), dict) else {}
    work_inbox = product_layer.get("work_inbox", {}) if isinstance(product_layer.get("work_inbox"), dict) else {}
    activity_timeline = product_layer.get("activity_timeline", {}) if isinstance(product_layer.get("activity_timeline"), dict) else {}
    capability_store = product_layer.get("capability_store", {}) if isinstance(product_layer.get("capability_store"), dict) else {}
    approval_center = product_layer.get("approval_center", {}) if isinstance(product_layer.get("approval_center"), dict) else {}
    proof_uploader = product_layer.get("observed_proof_uploader", {}) if isinstance(product_layer.get("observed_proof_uploader"), dict) else {}
    release_trust = product_layer.get("release_trust_panel", {}) if isinstance(product_layer.get("release_trust_panel"), dict) else {}
    attestation_status = product_layer.get("attestation_status", {}) if isinstance(product_layer.get("attestation_status"), dict) else {}
    recovery_center = product_layer.get("recovery_center", {}) if isinstance(product_layer.get("recovery_center"), dict) else {}
    evidence_dashboard = product_layer.get("evidence_dashboard", {}) if isinstance(product_layer.get("evidence_dashboard"), dict) else {}
    customer_proof_packet = product_layer.get("customer_proof_packet", {}) if isinstance(product_layer.get("customer_proof_packet"), dict) else {}
    customer_handoff = product_layer.get("customer_handoff_bundle", {}) if isinstance(product_layer.get("customer_handoff_bundle"), dict) else {}
    proof_promotion = product_layer.get("proof_promotion_center", {}) if isinstance(product_layer.get("proof_promotion_center"), dict) else {}
    product_map = product_layer.get("product_map", {}) if isinstance(product_layer.get("product_map"), dict) else {}
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
    product_map_group_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(group.get('label', group.get('id', 'Map group'))))}</b> "
        f"{html.escape(str(group.get('customer_goal', '')))} "
        f"<em>{html.escape(', '.join(str(surface.get('label', surface.get('id', 'surface'))) for surface in group.get('surfaces', []) if isinstance(surface, dict)))}</em>"
        "</li>"
        for group in product_map.get("surface_groups", [])
        if isinstance(group, dict)
    ) or "<li>No product map groups are configured.</li>"
    product_map_path_html = "\n".join(
        f"<li><code>{html.escape(str(surface_id))}</code></li>"
        for surface_id in product_map.get("recommended_path", [])
    ) or "<li>No recommended product path is configured.</li>"
    product_map_reviewer_route_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(route.get('label', route.get('id', 'Reviewer route'))))}</b> "
        f"{html.escape(str(route.get('customer_goal', '')))} "
        f"<em>{html.escape(str(route.get('claim_boundary', '')))}</em>"
        "</li>"
        for route in product_map.get("reviewer_routes", [])
        if isinstance(route, dict)
    ) or "<li>No reviewer routes are configured.</li>"
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
    onboarding_step_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Onboarding step'))))}</b> "
        f"{html.escape(str(item.get('command', item.get('url', item.get('suggested_prompt', '')))))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in onboarding_status.get("steps", [])
        if isinstance(item, dict)
    ) or "<li>No onboarding steps are configured.</li>"
    onboarding_checklist_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Readiness check'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in onboarding_status.get("readiness_checklist", [])
        if isinstance(item, dict)
    ) or "<li>No onboarding readiness checks are configured.</li>"
    guided_demo_stage_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Demo stage'))))}</b> "
        f"{html.escape(str(item.get('customer_goal', '')))} "
        f"<em>{html.escape(str(item.get('proof_boundary', '')))}</em>"
        "</li>"
        for item in guided_demo_journey.get("stages", [])
        if isinstance(item, dict)
    ) or "<li>No guided demo journey is configured.</li>"
    guided_demo_outcome_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Expected outcome'))))}</b> "
        f"{html.escape(str(item.get('expected_result', '')))} "
        f"<em>{html.escape(str(item.get('kind', 'unknown')))}</em>"
        "</li>"
        for item in guided_demo_journey.get("expected_outcomes", [])
        if isinstance(item, dict)
    ) or "<li>No guided demo expected outcomes are configured.</li>"
    guided_demo_completion = guided_demo_journey.get("completion_summary", {})
    if not isinstance(guided_demo_completion, dict):
        guided_demo_completion = {}
    guided_demo_completed_claim_html = "\n".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in guided_demo_completion.get("completed_claims", [])
    ) or "<li>No completed Docker demo claims are configured.</li>"
    guided_demo_next_blocker_html = "\n".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in guided_demo_completion.get("next_blockers", [])
    ) or "<li>No guided demo next blockers are configured.</li>"
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
    timeline_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(event.get('label', 'AgentOS')))}</b> "
        f"<span>{html.escape(str(event.get('time', '')))}</span> "
        f"{html.escape(str(event.get('message', '')))} "
        f"<em>{html.escape(str(event.get('intent', '') or event.get('capability', '')))}</em>"
        "</li>"
        for event in activity_timeline.get("events", [])
        if isinstance(event, dict)
    ) or "<li>No activity yet. Run a prompt below.</li>"
    capability_html = "\n".join(
        "<section class='feature'>"
        f"<div><h3>{html.escape(str(item.get('label', item.get('id', 'Capability'))))}</h3>"
        f"<p>{html.escape(str(item.get('customer_value', '')))}</p></div>"
        f"<span class='state'>{html.escape(str(item.get('state', 'unknown')))}</span>"
        "</section>"
        for item in capability_store.get("capabilities", [])[:10]
        if isinstance(item, dict)
    ) or "<p class='lead'>Capability registry is unavailable.</p>"
    approval_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Approval'))))}</b> "
        f"{html.escape(str(item.get('approval_requirement', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in approval_center.get("items", [])[:10]
        if isinstance(item, dict)
    ) or "<li>No approval-gated actions are available.</li>"
    proof_type_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Proof type'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in proof_uploader.get("proof_types", [])
        if isinstance(item, dict)
    ) or "<li>No observed proof types are configured.</li>"
    release_trust_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Release check'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in release_trust.get("checks", [])
        if isinstance(item, dict)
    ) or "<li>No release trust checks are configured.</li>"
    release_readiness_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Readiness item'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · {html.escape(str(item.get('validation', '')))}</em>"
        "</li>"
        for item in release_trust.get("readiness_checklist", [])
        if isinstance(item, dict)
    ) or "<li>No release readiness checklist is configured.</li>"
    release_decision_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Release decision'))))}</b> "
        f"{html.escape(str(item.get('customer_guidance', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · allowed: {html.escape(str(item.get('allowed_claim', '')))} · blocked: {html.escape(str(item.get('blocked_claim', '')))}</em>"
        "</li>"
        for item in release_trust.get("customer_decisions", [])
        if isinstance(item, dict)
    ) or "<li>No release customer decisions are configured.</li>"
    attestation_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Attestation check'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in attestation_status.get("checks", [])
        if isinstance(item, dict)
    ) or "<li>No attestation checks are configured.</li>"
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
    proof_packet_claim_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Completed claim'))))}</b> "
        f"<em>{html.escape(str(item.get('evidence_source', '')))}</em>"
        "</li>"
        for item in customer_proof_packet.get("completed_claims", [])
        if isinstance(item, dict)
    ) or "<li>No completed proof packet claims are configured.</li>"
    proof_packet_command_html = "\n".join(
        f"<li><code>{html.escape(str(command))}</code></li>"
        for command in customer_proof_packet.get("validation_commands", [])
    ) or "<li>No proof packet validation commands are configured.</li>"
    proof_packet_readiness_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Readiness check'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))}</em>"
        "</li>"
        for item in customer_proof_packet.get("readiness_checklist", [])
        if isinstance(item, dict)
    ) or "<li>No proof packet readiness checks are configured.</li>"
    handoff_try_path = customer_handoff.get("try_path", {})
    if not isinstance(handoff_try_path, dict):
        handoff_try_path = {}
    handoff_surface_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Surface'))))}</b> "
        f"<code>{html.escape(str(item.get('url', '')))}</code>"
        "</li>"
        for item in customer_handoff.get("inspect_surfaces", [])
        if isinstance(item, dict)
    ) or "<li>No handoff surfaces are configured.</li>"
    handoff_validation_html = "\n".join(
        f"<li><code>{html.escape(str(command))}</code></li>"
        for command in customer_handoff.get("validation_commands", [])
    ) or "<li>No handoff validation commands are configured.</li>"
    handoff_checklist_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Handoff step'))))}</b> "
        f"{html.escape(str(item.get('customer_action', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · {html.escape(str(item.get('proof_boundary', '')))}</em>"
        "</li>"
        for item in customer_handoff.get("handoff_checklist", [])
        if isinstance(item, dict)
    ) or "<li>No handoff checklist steps are configured.</li>"
    handoff_report = customer_handoff.get("handoff_report", {})
    if not isinstance(handoff_report, dict):
        handoff_report = {}
    handoff_report_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Report section'))))}</b> "
        f"{html.escape(str(item.get('customer_value', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · source: {html.escape(str(item.get('source', 'unknown')))}</em>"
        "</li>"
        for item in handoff_report.get("sections", [])
        if isinstance(item, dict)
    ) or "<li>No handoff report sections are configured.</li>"
    handoff_share_policy = handoff_report.get("share_policy", {})
    if not isinstance(handoff_share_policy, dict):
        handoff_share_policy = {}
    proof_promotion_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Promotion decision'))))}</b> "
        f"{html.escape(str(item.get('customer_decision', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · {html.escape(str(item.get('promotion_boundary', '')))}</em>"
        "</li>"
        for item in proof_promotion.get("promotion_decisions", [])
        if isinstance(item, dict)
    ) or "<li>No proof promotion decisions are configured.</li>"
    proof_promotion_share_policy = proof_promotion.get("share_policy", {})
    if not isinstance(proof_promotion_share_policy, dict):
        proof_promotion_share_policy = {}
    proof_promotion_checklist_html = "\n".join(
        "<li>"
        f"<b>{html.escape(str(item.get('label', item.get('id', 'Sharing checklist item'))))}</b> "
        f"{html.escape(str(item.get('customer_guidance', '')))} "
        f"<em>{html.escape(str(item.get('state', 'unknown')))} · allowed: {html.escape(str(item.get('allowed_claim', '')))} · blocked: {html.escape(str(item.get('blocked_claim', '')))}</em>"
        "</li>"
        for item in proof_promotion.get("sharing_checklist", [])
        if isinstance(item, dict)
    ) or "<li>No proof sharing checklist is configured.</li>"
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
      <h2>Product Layer Map</h2>
      <p class="lead">{html.escape(str(product_map.get('customer_message', 'A product layer map is available below.')))}</p>
      <ul>{product_map_group_html}</ul>
    </div>
    <div class="panel">
      <h2>Recommended Path</h2>
      <ul>{product_map_path_html}</ul>
      <h2>Reviewer Routes</h2>
      <ul>{product_map_reviewer_route_html}</ul>
      <p><a href="/api/product-map">product map JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Guided Demo Journey</h2>
      <p class="lead">{html.escape(str(guided_demo_journey.get('customer_message', 'A guided demo journey is available below.')))}</p>
      <ul>{guided_demo_stage_html}</ul>
      <h3>Expected Outcomes</h3>
      <ul>{guided_demo_outcome_html}</ul>
      <h3>Demo Completion Summary</h3>
      <p class="lead">{html.escape(str(guided_demo_completion.get('customer_result', 'The Docker guided demo can be completed through the local Product Layer preview.')))}</p>
      <h3>Completed Claims</h3>
      <ul>{guided_demo_completed_claim_html}</ul>
      <h3>Next Proof Blockers</h3>
      <ul>{guided_demo_next_blocker_html}</ul>
    </div>
    <div class="panel">
      <h2>Journey Proof</h2>
      <ul>
        <li><b>Docker preview</b> ready</li>
        <li><b>VM/ISO boot proof</b> not claimed</li>
        <li><b>Live provider proof</b> not claimed</li>
      </ul>
      <p><a href="/api/demo-journey">demo journey JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Docker Onboarding Status</h2>
      <p class="lead">{html.escape(str(onboarding_status.get('customer_message', 'Docker onboarding status is available below.')))}</p>
      <ul>{onboarding_step_html}</ul>
      <h3>Readiness Checklist</h3>
      <ul>{onboarding_checklist_html}</ul>
    </div>
    <div class="panel">
      <h2>Onboarding Proof</h2>
      <ul>
        <li><b>Basic preview API key</b> not required</li>
        <li><b>VM/ISO boot proof</b> not claimed</li>
        <li><b>Live OAuth proof</b> not claimed</li>
      </ul>
      <p><a href="/api/onboarding">onboarding JSON</a></p>
    </div>
  </section>
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
      <h2>Activity Timeline</h2>
      <p class="lead">{html.escape(str(activity_timeline.get('customer_message', 'Recent runtime activity is available below.')))}</p>
      <ul>{timeline_html}</ul>
    </div>
    <div class="panel">
      <h2>Timeline Proof</h2>
      <ul>
        <li><b>Records</b> {html.escape(str(activity_timeline.get('records', {}).get('os_events_jsonl', '') if isinstance(activity_timeline.get('records'), dict) else ''))}</li>
        <li><b>External app execution</b> not claimed</li>
        <li><b>Live provider proof</b> not claimed</li>
      </ul>
      <p><a href="/api/timeline">timeline JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Capability Store</h2>
      <p class="lead">{html.escape(str(capability_store.get('customer_message', 'Capability registry is available below.')))}</p>
      {capability_html}
    </div>
    <div class="panel">
      <h2>Capability Proof</h2>
      <ul>
        <li><b>Destructive actions</b> blocked by default</li>
        <li><b>External writes</b> not claimed</li>
        <li><b>Live provider proof</b> not claimed</li>
      </ul>
      <p><a href="/api/capabilities">capabilities JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Approval Center</h2>
      <p class="lead">{html.escape(str(approval_center.get('customer_message', 'Approval requirements are available below.')))}</p>
      <ul>{approval_html}</ul>
    </div>
    <div class="panel">
      <h2>Approval Proof</h2>
      <ul>
        <li><b>Approval execution</b> not claimed</li>
        <li><b>External writes</b> not claimed</li>
        <li><b>Destructive actions</b> blocked by default</li>
      </ul>
      <p><a href="/api/approvals">approvals JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Observed Proof Uploader</h2>
      <p class="lead">{html.escape(str(proof_uploader.get('customer_message', 'Observed proof requirements are available below.')))}</p>
      <ul>{proof_type_html}</ul>
    </div>
    <div class="panel">
      <h2>Upload Boundary</h2>
      <ul>
        <li><b>Secret material</b> not allowed</li>
        <li><b>Claim promotion</b> not automatic</li>
        <li><b>File upload execution</b> not claimed</li>
      </ul>
      <p><a href="/api/proofs">proofs JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Release Trust Panel</h2>
      <p class="lead">{html.escape(str(release_trust.get('customer_message', 'Release trust requirements are available below.')))}</p>
      <ul>{release_trust_html}</ul>
      <h3>Release Readiness Checklist</h3>
      <ul>{release_readiness_html}</ul>
    </div>
    <div class="panel">
      <h2>Release Customer Decisions</h2>
      <ul>{release_decision_html}</ul>
      <h2>Release Non-Claims</h2>
      <ul>
        <li><b>Release uploaded</b> not claimed</li>
        <li><b>Signing observed</b> not claimed</li>
        <li><b>VM/ISO release proof</b> not claimed</li>
      </ul>
      <p><a href="/api/release-trust">release trust JSON</a></p>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Attestation Status</h2>
      <p class="lead">{html.escape(str(attestation_status.get('customer_message', 'Attestation requirements are available below.')))}</p>
      <ul>{attestation_html}</ul>
    </div>
    <div class="panel">
      <h2>Attestation Non-Claims</h2>
      <ul>
        <li><b>Secure Boot</b> not claimed</li>
        <li><b>TPM/PCR evidence</b> not claimed</li>
        <li><b>Hardware attestation</b> not claimed</li>
      </ul>
      <p><a href="/api/attestation">attestation JSON</a></p>
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
  <section class="product">
    <div class="panel">
      <h2>Customer Handoff Bundle</h2>
      <p class="lead">{html.escape(str(customer_handoff.get('customer_message', 'Customer handoff bundle is available below.')))}</p>
      <ul>
        <li><b>Run</b> <code>{html.escape(str(handoff_try_path.get('command', 'docker compose up --build')))}</code></li>
        <li><b>Open</b> <code>{html.escape(str(handoff_try_path.get('url', 'http://localhost:8787')))}</code></li>
        <li><b>First prompt</b> <code>{html.escape(str(handoff_try_path.get('first_prompt', 'status')))}</code></li>
      </ul>
      <p><a href="/api/customer-handoff">customer handoff JSON</a></p>
    </div>
    <div class="panel">
      <h2>Handoff Surfaces</h2>
      <ul>{handoff_surface_html}</ul>
    </div>
    <div class="panel">
      <h2>Handoff Checklist</h2>
      <ul>{handoff_checklist_html}</ul>
    </div>
    <div class="panel">
      <h2>Handoff Validation</h2>
      <ul>{handoff_validation_html}</ul>
    </div>
    <div class="panel">
      <h2>Handoff Report</h2>
      <p class="lead">{html.escape(str(handoff_report.get('summary', 'A shareable Docker-local handoff report is available below.')))}</p>
      <ul>{handoff_report_html}</ul>
      <ul>
        <li><b>Secrets allowed</b> {html.escape(str(handoff_share_policy.get('secret_material_allowed', False)))}</li>
        <li><b>Automatic claim promotion</b> {html.escape(str(handoff_share_policy.get('automatic_claim_promotion', False)))}</li>
        <li><b>Stronger claims require observed evidence</b> {html.escape(str(handoff_share_policy.get('requires_sanitized_observed_evidence_for_stronger_claims', True)))}</li>
      </ul>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Customer Proof Packet</h2>
      <p class="lead">{html.escape(str(customer_proof_packet.get('customer_message', 'Customer proof packet is available below.')))}</p>
      <ul>{proof_packet_claim_html}</ul>
    </div>
    <div class="panel">
      <h2>Packet Validation</h2>
      <ul>{proof_packet_command_html}</ul>
      <p><a href="/api/proof-packet">proof packet JSON</a></p>
    </div>
    <div class="panel">
      <h2>Packet Readiness</h2>
      <ul>{proof_packet_readiness_html}</ul>
    </div>
  </section>
  <section class="product">
    <div class="panel">
      <h2>Proof Promotion Center</h2>
      <p class="lead">{html.escape(str(proof_promotion.get('customer_message', 'Proof promotion decisions are available below.')))}</p>
      <ul>{proof_promotion_html}</ul>
    </div>
    <div class="panel">
      <h2>Promotion Policy</h2>
      <ul>
        <li><b>Secrets allowed</b> {html.escape(str(proof_promotion_share_policy.get('secret_material_allowed', False)))}</li>
        <li><b>Automatic claim promotion</b> {html.escape(str(proof_promotion_share_policy.get('automatic_claim_promotion', False)))}</li>
        <li><b>Stronger claims require observed evidence</b> {html.escape(str(proof_promotion_share_policy.get('requires_sanitized_observed_evidence_for_stronger_claims', True)))}</li>
      </ul>
      <p><a href="/api/proof-promotion">proof promotion JSON</a></p>
    </div>
    <div class="panel">
      <h2>Proof Sharing Checklist</h2>
      <ul>{proof_promotion_checklist_html}</ul>
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
            elif path == "/api/onboarding":
                _json_response(self, app.onboarding_status())
            elif path == "/api/demo-journey":
                _json_response(self, app.guided_demo_journey())
            elif path == "/api/work-inbox":
                _json_response(self, app.work_inbox())
            elif path == "/api/timeline":
                _json_response(self, app.activity_timeline())
            elif path == "/api/capabilities":
                _json_response(self, app.capability_store())
            elif path == "/api/approvals":
                _json_response(self, app.approval_center())
            elif path == "/api/proofs":
                _json_response(self, app.observed_proof_uploader())
            elif path == "/api/release-trust":
                _json_response(self, app.release_trust_panel())
            elif path == "/api/attestation":
                _json_response(self, app.attestation_status())
            elif path == "/api/recovery":
                _json_response(self, app.recovery_center())
            elif path == "/api/evidence":
                _json_response(self, app.evidence_dashboard())
            elif path == "/api/proof-packet":
                _json_response(self, app.customer_proof_packet())
            elif path == "/api/customer-handoff":
                _json_response(self, app.customer_handoff_bundle())
            elif path == "/api/proof-promotion":
                _json_response(self, app.proof_promotion_center())
            elif path == "/api/product-map":
                _json_response(self, app.product_map())
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
