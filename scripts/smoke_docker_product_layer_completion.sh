#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PRODUCT_LAYER_SMOKE_PORT:-18788}"
PID=""
cleanup() {
  if [ -n "$PID" ]; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

AGENTOS_DOCKER_TELEGRAM_POLLING=false \
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts:$ROOT_DIR" \
python3 scripts/docker_runtime_preview.py \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workspace "$TMP_DIR/workspace" \
  --user-root "$TMP_DIR/user" \
  > "$TMP_DIR/server.log" 2>&1 &
PID="$!"

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null
curl -fsS "http://127.0.0.1:$PORT/" > "$TMP_DIR/home.html"
curl -fsS "http://127.0.0.1:$PORT/api/product" > "$TMP_DIR/product.json"
curl -fsS "http://127.0.0.1:$PORT/api/onboarding" > "$TMP_DIR/onboarding.json"
curl -fsS "http://127.0.0.1:$PORT/api/demo-journey" > "$TMP_DIR/demo-journey.json"
curl -fsS "http://127.0.0.1:$PORT/api/preview-readiness" > "$TMP_DIR/preview-readiness.json"
curl -fsS "http://127.0.0.1:$PORT/api/work-inbox" > "$TMP_DIR/work-inbox.json"
curl -fsS "http://127.0.0.1:$PORT/api/timeline" > "$TMP_DIR/timeline.json"
curl -fsS "http://127.0.0.1:$PORT/api/capabilities" > "$TMP_DIR/capabilities.json"
curl -fsS "http://127.0.0.1:$PORT/api/approvals" > "$TMP_DIR/approvals.json"
curl -fsS "http://127.0.0.1:$PORT/api/proofs" > "$TMP_DIR/proofs.json"
curl -fsS "http://127.0.0.1:$PORT/api/release-trust" > "$TMP_DIR/release-trust.json"
curl -fsS "http://127.0.0.1:$PORT/api/attestation" > "$TMP_DIR/attestation.json"
curl -fsS "http://127.0.0.1:$PORT/api/recovery" > "$TMP_DIR/recovery.json"
curl -fsS "http://127.0.0.1:$PORT/api/recovery-drills" > "$TMP_DIR/recovery-drills.json"
curl -fsS "http://127.0.0.1:$PORT/api/session-report" > "$TMP_DIR/session-report.json"
curl -fsS "http://127.0.0.1:$PORT/api/evidence" > "$TMP_DIR/evidence.json"
curl -fsS "http://127.0.0.1:$PORT/api/proof-packet" > "$TMP_DIR/proof-packet.json"
curl -fsS "http://127.0.0.1:$PORT/api/customer-handoff" > "$TMP_DIR/customer-handoff.json"
curl -fsS "http://127.0.0.1:$PORT/api/proof-promotion" > "$TMP_DIR/proof-promotion.json"
curl -fsS "http://127.0.0.1:$PORT/api/proof-requests" > "$TMP_DIR/proof-requests.json"
curl -fsS "http://127.0.0.1:$PORT/api/product-map" > "$TMP_DIR/product-map.json"
curl -fsS "http://127.0.0.1:$PORT/api/next-work" > "$TMP_DIR/next-work.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text()
product = json.loads((root / "product.json").read_text())
onboarding = json.loads((root / "onboarding.json").read_text())

surfaces = {
    "onboarding_status": ("onboarding.json", "agentos-product-layer-onboarding-status.v1", "Docker Onboarding Status"),
    "guided_demo_journey": ("demo-journey.json", "agentos-product-layer-guided-demo-journey.v1", "Guided Demo Journey"),
    "preview_readiness_board": ("preview-readiness.json", "agentos-product-layer-preview-readiness-board.v1", "Preview Readiness Board"),
    "work_inbox": ("work-inbox.json", "agentos-product-layer-work-inbox.v1", "Work Inbox"),
    "activity_timeline": ("timeline.json", "agentos-product-layer-activity-timeline.v1", "Activity Timeline"),
    "capability_store": ("capabilities.json", "agentos-product-layer-capability-store.v1", "Capability Store"),
    "approval_center": ("approvals.json", "agentos-product-layer-approval-center.v1", "Approval Center"),
    "observed_proof_uploader": ("proofs.json", "agentos-product-layer-observed-proof-uploader.v1", "Observed Proof Uploader"),
    "release_trust_panel": ("release-trust.json", "agentos-product-layer-release-trust-panel.v1", "Release Trust Panel"),
    "attestation_status": ("attestation.json", "agentos-product-layer-attestation-status.v1", "Attestation Status"),
    "recovery_center": ("recovery.json", "agentos-product-layer-recovery-center.v1", "Recovery Center"),
    "recovery_drill_board": ("recovery-drills.json", "agentos-product-layer-recovery-drill-board.v1", "Recovery Drill Board"),
    "session_report": ("session-report.json", "agentos-product-layer-session-report.v1", "Session Report"),
    "evidence_dashboard": ("evidence.json", "agentos-product-layer-evidence-dashboard.v1", "Evidence Dashboard"),
    "customer_proof_packet": ("proof-packet.json", "agentos-product-layer-customer-proof-packet.v1", "Customer Proof Packet"),
    "customer_handoff_bundle": ("customer-handoff.json", "agentos-product-layer-customer-handoff-bundle.v1", "Customer Handoff Bundle"),
    "proof_promotion_center": ("proof-promotion.json", "agentos-product-layer-proof-promotion-center.v1", "Proof Promotion Center"),
    "observed_proof_request_board": ("proof-requests.json", "agentos-product-layer-observed-proof-request-board.v1", "Observed Proof Request Board"),
    "product_map": ("product-map.json", "agentos-product-layer-map.v1", "Product Layer Map"),
    "next_work_board": ("next-work.json", "agentos-product-layer-next-work-board.v1", "Next Work Board"),
}

assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["docker_main_try_path"] is True
assert product["proof"]["boot_or_iso_proof_claimed"] is False
assert product["proof"]["live_oauth_claimed"] is False
assert product["proof"]["live_browser_proof_claimed"] is False
assert product["proof"]["runtime_home_completion_snapshot_ready"] is True

snapshot = product["completion_snapshot"]
assert snapshot["schema_version"] == "agentos-product-layer-runtime-home-completion-snapshot.v1"
assert snapshot["state"] == "ready"
assert {item["id"] for item in snapshot["completed_local_proof"]} == {
    "docker_runtime_home_visible",
    "customer_path_available",
    "proof_boundaries_visible",
}
assert {item["id"] for item in snapshot["validation_gates"]} >= {
    "runtime_home_snapshot_gate",
    "product_layer_completion_gate",
    "runtime_preview_python_gate",
    "compose_config_gate",
}
assert any(item["command"] == "scripts/smoke_docker_runtime_home_snapshot.sh" for item in snapshot["validation_gates"])
assert {item["id"] for item in snapshot["review_surfaces"]} >= {
    "start_here",
    "guided_path",
    "preview_readiness",
    "product_map",
    "next_work",
    "recovery_drills",
    "session_report",
}
assert {item["id"] for item in snapshot["blocked_stronger_proof"]} == {
    "docker_daemon_observed",
    "vm_iso_runtime_rejoin",
    "live_readonly_oauth",
    "release_browser_attestation",
}
assert snapshot["proof"]["customer_facing_runtime_home_snapshot_ready"] is True
assert snapshot["proof"]["automatic_claim_promotion"] is False

feature_ids = {feature["id"] for feature in product["features"]}
expected_feature_ids = {"runtime_home", *surfaces.keys()}
assert expected_feature_ids <= feature_ids, sorted(expected_feature_ids - feature_ids)
assert "Runtime Home" in home
assert "Runtime Home Completion Snapshot" in home
assert "scripts/smoke_docker_runtime_home_snapshot.sh" in home

for key, (filename, schema, label) in surfaces.items():
    embedded = product[key]
    endpoint = json.loads((root / filename).read_text())
    assert embedded["schema_version"] == schema, key
    assert endpoint["schema_version"] == schema, key
    assert label in home, label

assert product["onboarding_status"]["validation"]["onboarding_status_contract_smoke"] == "scripts/smoke_docker_onboarding_status_contract.sh"
assert product["work_inbox"]["proof"]["work_inbox_completion_snapshot_ready"] is True
work_inbox_snapshot = product["work_inbox"]["completion_snapshot"]
assert work_inbox_snapshot["schema_version"] == "agentos-product-layer-work-inbox-completion-snapshot.v1"
assert work_inbox_snapshot["state"] == "ready"
assert {item["id"] for item in work_inbox_snapshot["completed_local_proof"]} == {
    "fixture_inbox_ready",
    "read_first_workflows_ready",
    "live_boundaries_visible",
}
assert {item["id"] for item in work_inbox_snapshot["mutation_boundaries"]} == {
    "external_send_blocked",
    "production_sync_blocked",
}
assert any(item["command"] == "scripts/smoke_docker_work_inbox_snapshot.sh" for item in work_inbox_snapshot["validation_gates"])
assert work_inbox_snapshot["proof"]["customer_facing_work_inbox_snapshot_ready"] is True
assert work_inbox_snapshot["proof"]["external_mutation_claimed"] is False
assert work_inbox_snapshot["proof"]["automatic_claim_promotion"] is False
assert "Work Inbox Completion Snapshot" in home
assert "scripts/smoke_docker_work_inbox_snapshot.sh" in home
assert {item["id"] for item in product["guided_demo_journey"]["expected_outcomes"]} >= {
    "runtime_reachable",
    "read_first_work_visible",
    "activity_and_records_visible",
    "proof_boundaries_visible",
    "recovery_next_steps_visible",
}
assert product["guided_demo_journey"]["completion_summary"]["id"] == "docker_guided_demo_complete"
assert len(product["guided_demo_journey"]["completion_summary"]["completed_claims"]) >= 4
assert len(product["guided_demo_journey"]["completion_summary"]["next_blockers"]) >= 3
assert {item["id"] for item in product["preview_readiness_board"]["readiness_checks"]} >= {
    "docker_try_path_documented",
    "product_layer_surfaces_visible",
    "docker_safe_validation_available",
    "public_preview_operations_contract_linked",
    "observed_proof_blockers_visible",
}
assert {item["id"] for item in product["preview_readiness_board"]["promotion_decisions"]} >= {
    "share_docker_local_preview",
    "rerun_local_gates_before_demo",
    "withhold_stronger_preview_claims",
}
assert product["preview_readiness_board"]["operations_contract"]["doc"] == "docs/operations/public-preview-operations.md"
assert "scripts/smoke_docker_preview_readiness_board.sh" in product["preview_readiness_board"]["validation_commands"]
assert "Preview Readiness Board" in home
assert "Preview Promotion Decisions" in home
assert "preview readiness JSON" in home
assert product["customer_proof_packet"]["proof"]["customer_packet_ready"] is True
assert product["customer_proof_packet"]["proof"]["claim_promotion_automatic"] is False
assert product["customer_handoff_bundle"]["proof"]["customer_handoff_ready"] is True
assert product["customer_handoff_bundle"]["proof"]["boot_or_iso_proof_claimed"] is False
assert product["customer_handoff_bundle"]["try_path"]["command"] == "docker compose up --build"
assert {item["id"] for item in product["customer_handoff_bundle"]["handoff_checklist"]} >= {
    "run_preview",
    "open_runtime_home",
    "inspect_guided_path",
    "run_validation_commands",
    "record_remaining_blockers",
}
assert product["customer_handoff_bundle"]["handoff_report"]["schema_version"] == "agentos-product-layer-customer-handoff-report.v1"
assert {item["id"] for item in product["customer_handoff_bundle"]["handoff_report"]["sections"]} >= {
    "reproduced_try_path",
    "inspected_product_surfaces",
    "local_validation_evidence",
    "remaining_observed_proof_blockers",
    "share_safe_non_claims",
}
assert product["customer_handoff_bundle"]["handoff_report"]["share_policy"]["secret_material_allowed"] is False
assert product["customer_handoff_bundle"]["handoff_report"]["share_policy"]["automatic_claim_promotion"] is False
release_readiness = {
    item["id"]: item["state"]
    for item in product["release_trust_panel"]["readiness_checklist"]
}
assert release_readiness == {
    "local_preflight_available": "ready",
    "artifact_manifest_required": "blocked_until_release_artifact",
    "checksum_publication_required": "blocked_until_checksum",
    "signing_or_unsigned_statement_required": "blocked_until_signature_or_unsigned_statement",
    "vm_iso_release_proof_required": "blocked_until_observed_vm_run",
}
release_decisions = {
    item["id"]: item["state"]
    for item in product["release_trust_panel"]["customer_decisions"]
}
assert release_decisions == {
    "describe_local_preflight_only": "share_ready",
    "withhold_release_readiness": "blocked_until_release_evidence",
    "route_to_observed_proof": "blocked_until_observed_evidence",
}
assert "Release Readiness Checklist" in home
assert "Release Customer Decisions" in home
assert product["proof_promotion_center"]["proof"]["customer_facing_proof_promotion_ready"] is True
assert product["proof_promotion_center"]["proof"]["docker_local_claims_ready"] is True
assert product["proof_promotion_center"]["proof"]["docker_daemon_observed_claimed"] is False
assert product["proof_promotion_center"]["share_policy"]["secret_material_allowed"] is False
assert product["proof_promotion_center"]["share_policy"]["automatic_claim_promotion"] is False
assert {item["id"] for item in product["proof_promotion_center"]["promotion_decisions"]} >= {
    "docker-local-product-layer",
    "docker-daemon-observed-run",
    "vm-iso-runtime-ownership",
    "live-provider-readonly",
    "live-browser-release-attestation",
}
proof_sharing_states = {
    item["id"]: item["state"]
    for item in product["proof_promotion_center"]["sharing_checklist"]
}
assert proof_sharing_states == {
    "describe_docker_local_product_layer": "share_ready",
    "include_validation_commands": "share_ready",
    "attach_source_surfaces": "share_ready",
    "withhold_stronger_claims": "blocked_until_observed_evidence",
}
assert "Proof Sharing Checklist" in home
assert "Withhold stronger claims" in home
assert product["observed_proof_request_board"]["proof"]["customer_facing_observed_proof_requests_ready"] is True
assert product["observed_proof_request_board"]["proof"]["secret_material_allowed"] is False
assert product["observed_proof_request_board"]["proof"]["automatic_claim_promotion"] is False
assert {item["id"] for item in product["observed_proof_request_board"]["requests"]} == {
    "docker_daemon_observed",
    "vm_iso_runtime_rejoin",
    "live_readonly_oauth",
    "live_browser_fallback",
    "release_trust",
    "hardware_attestation",
}
assert "scripts/smoke_docker_observed_proof_request_board.sh" in product["observed_proof_request_board"]["validation_commands"]
assert product["product_map"]["proof"]["customer_facing_product_map_ready"] is True
assert product["product_map"]["proof"]["boot_or_iso_proof_claimed"] is False
assert product["next_work_board"]["proof"]["customer_facing_next_work_ready"] is True
assert product["next_work_board"]["proof"]["boot_or_iso_proof_claimed"] is False
assert product["next_work_board"]["proof"]["automatic_claim_promotion"] is False
assert {item["id"] for item in product["next_work_board"]["completed_product_proof"]} >= {
    "docker_product_layer_surfaces",
    "docker_customer_handoff",
    "runtime_truthfulness_gates",
}
assert {item["id"] for item in product["next_work_board"]["safe_next_candidates"]} == {
    "docker_daemon_observed_run",
    "live_readonly_provider_proof",
    "vm_iso_runtime_rejoin_proof",
    "release_and_attestation_evidence",
}
assert {item["id"] for item in product["next_work_board"]["blocked_tracks"]} == {
    "vm_iso",
    "live_oauth",
    "live_browser",
    "release",
    "hardware_attestation",
}
assert "scripts/smoke_docker_next_work_board.sh" in product["next_work_board"]["validation_commands"]
assert {group["id"] for group in product["product_map"]["surface_groups"]} >= {
    "start_here",
    "do_work",
    "prove_and_handoff",
    "blocked_until_observed",
}
assert "proof_promotion_center" in product["product_map"]["recommended_path"]
assert "observed_proof_request_board" in product["product_map"]["recommended_path"]
assert "next_work_board" in product["product_map"]["recommended_path"]
assert "recovery_drill_board" in product["product_map"]["recommended_path"]
assert "session_report" in product["product_map"]["recommended_path"]
assert product["session_report"]["proof"]["customer_facing_session_report_ready"] is True
assert product["session_report"]["proof"]["evidence_dashboard_linked"] is True
assert product["session_report"]["proof"]["recovery_drills_linked"] is True
assert {item["id"] for item in product["session_report"]["report_sections"]} == {
    "runtime_state",
    "recent_activity",
    "proof_sources",
    "recovery_drills",
    "stronger_proof_blockers",
}
assert "scripts/smoke_docker_session_report.sh" in product["session_report"]["validation_commands"]
assert product["recovery_drill_board"]["proof"]["customer_facing_recovery_drills_ready"] is True
assert product["recovery_drill_board"]["proof"]["boot_or_iso_proof_claimed"] is False
assert product["recovery_drill_board"]["proof"]["live_oauth_claimed"] is False
assert {item["id"] for item in product["recovery_drill_board"]["drills"]} == {
    "preview_health_check",
    "runtime_preview_python_smoke",
    "product_layer_completion_recheck",
    "cleanup_policy_recheck",
    "vm_iso_rejoin_blocker_review",
    "live_adapter_recovery_review",
}
assert "scripts/smoke_docker_recovery_drill_board.sh" in product["recovery_drill_board"]["validation_commands"]
reviewer_routes = {item["id"]: item for item in product["product_map"]["reviewer_routes"]}
assert set(reviewer_routes) == {
    "runtime_evaluator",
    "proof_reviewer",
    "capability_reviewer",
    "trust_reviewer",
}
assert reviewer_routes["runtime_evaluator"]["route"] == [
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
    "preview_readiness_board",
    "next_work_board",
    "activity_timeline",
    "recovery_drill_board",
    "recovery_center",
]
assert "VM/ISO" in reviewer_routes["runtime_evaluator"]["claim_boundary"]
assert reviewer_routes["proof_reviewer"]["route"] == [
    "evidence_dashboard",
    "customer_proof_packet",
    "customer_handoff_bundle",
    "session_report",
    "proof_promotion_center",
    "observed_proof_request_board",
    "next_work_board",
]
assert "sanitized observed evidence" in reviewer_routes["proof_reviewer"]["claim_boundary"]
assert reviewer_routes["capability_reviewer"]["route"] == [
    "work_inbox",
    "capability_store",
    "approval_center",
    "activity_timeline",
]
assert "external writes" in reviewer_routes["capability_reviewer"]["claim_boundary"]
assert reviewer_routes["trust_reviewer"]["route"] == [
    "observed_proof_uploader",
    "observed_proof_request_board",
    "recovery_drill_board",
    "release_trust_panel",
    "attestation_status",
    "recovery_center",
]
assert "hardware trust proof" in reviewer_routes["trust_reviewer"]["claim_boundary"]
assert "Product Layer Map" in home
assert "Reviewer Routes" in home
assert "product map JSON" in home
assert "Observed Proof Request Board" in home
assert "proof requests JSON" in home
assert "Recovery Drill Board" in home
assert "recovery drills JSON" in home
assert "Session Report" in home
assert "session report JSON" in home
assert "Next Work Board" in home
assert "next work JSON" in home
assert {item["id"] for item in product["customer_handoff_bundle"]["inspect_surfaces"]} >= {
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
    "customer_proof_packet",
    "recovery_center",
    "evidence_dashboard",
}
assert {item["id"] for item in product["customer_proof_packet"]["readiness_checklist"]} >= {
    "completed_claims_present",
    "validation_commands_present",
    "proof_sources_linked",
    "non_claims_explicit",
    "automatic_claim_promotion_disabled",
}
assert {item["id"] for item in product["customer_proof_packet"]["completed_claims"]} >= {
    "docker-runtime-preview-ready",
    "product-layer-surfaces-ready",
    "guided-demo-path-ready",
    "golden-runtime-loop-ready",
}
assert {item["id"] for item in product["onboarding_status"]["readiness_checklist"]} >= {
    "quickstart_documented",
    "preview_entrypoints_available",
    "basic_preview_no_api_key",
    "docker_validation_available",
    "observed_proof_boundaries_visible",
}

non_claims = {
    "boot_or_iso_proof_claimed": product["proof"]["boot_or_iso_proof_claimed"],
    "guided_demo_boot_or_iso": product["guided_demo_journey"]["proof"]["boot_or_iso_proof_claimed"],
    "guided_demo_live_oauth": product["guided_demo_journey"]["proof"]["live_oauth_claimed"],
    "guided_demo_external_mutation": product["guided_demo_journey"]["proof"]["external_mutation_claimed"],
    "preview_readiness_docker_daemon": product["preview_readiness_board"]["proof"]["docker_daemon_observed_claimed"],
    "preview_readiness_vm_iso": product["preview_readiness_board"]["proof"]["boot_or_iso_proof_claimed"],
    "preview_readiness_live_oauth": product["preview_readiness_board"]["proof"]["live_oauth_claimed"],
    "preview_readiness_live_browser": product["preview_readiness_board"]["proof"]["live_browser_proof_claimed"],
    "preview_readiness_release": product["preview_readiness_board"]["proof"]["release_trust_claimed"],
    "preview_readiness_external_mutation": product["preview_readiness_board"]["proof"]["external_mutation_claimed"],
    "preview_readiness_attestation": product["preview_readiness_board"]["proof"]["hardware_attestation_claimed"],
    "preview_readiness_automatic_promotion": product["preview_readiness_board"]["proof"]["automatic_claim_promotion"],
    "onboarding_boot_or_iso": product["onboarding_status"]["proof"]["boot_or_iso_proof_claimed"],
    "onboarding_live_oauth": product["onboarding_status"]["proof"]["live_oauth_claimed"],
    "work_inbox_live_oauth": product["work_inbox"]["proof"]["live_oauth_claimed"],
    "work_inbox_external_mutation": product["work_inbox"]["proof"]["external_mutation_claimed"],
    "work_inbox_snapshot_live_oauth": product["work_inbox"]["completion_snapshot"]["proof"]["live_oauth_claimed"],
    "work_inbox_snapshot_browser_default": product["work_inbox"]["completion_snapshot"]["proof"]["browser_default_claimed"],
    "work_inbox_snapshot_external_mutation": product["work_inbox"]["completion_snapshot"]["proof"]["external_mutation_claimed"],
    "work_inbox_snapshot_production_sync": product["work_inbox"]["completion_snapshot"]["proof"]["production_sync_claimed"],
    "work_inbox_snapshot_maildir_observed": product["work_inbox"]["completion_snapshot"]["proof"]["user_maildir_observed_claimed"],
    "work_inbox_snapshot_auto_promotion": product["work_inbox"]["completion_snapshot"]["proof"]["automatic_claim_promotion"],
    "timeline_external_app": product["activity_timeline"]["proof"]["external_app_execution_claimed"],
    "capability_external_write": product["capability_store"]["proof"]["external_write_claimed"],
    "approval_execution": product["approval_center"]["proof"]["approval_execution_claimed"],
    "proof_upload_execution": product["observed_proof_uploader"]["proof"]["file_upload_execution_claimed"],
    "release_uploaded": product["release_trust_panel"]["proof"]["release_uploaded"],
    "release_vm_iso": product["release_trust_panel"]["proof"]["vm_iso_release_proof_completed"],
    "secure_boot": product["attestation_status"]["proof"]["secure_boot_observed"],
    "hardware_attestation": product["attestation_status"]["proof"]["hardware_attestation_observed"],
    "recovery_vm_iso": product["recovery_center"]["proof"]["boot_or_iso_proof_claimed"],
    "recovery_drill_docker_daemon": product["recovery_drill_board"]["proof"]["docker_daemon_observed_claimed"],
    "recovery_drill_vm_iso": product["recovery_drill_board"]["proof"]["boot_or_iso_proof_claimed"],
    "recovery_drill_live_oauth": product["recovery_drill_board"]["proof"]["live_oauth_claimed"],
    "recovery_drill_live_browser": product["recovery_drill_board"]["proof"]["live_browser_proof_claimed"],
    "recovery_drill_release": product["recovery_drill_board"]["proof"]["release_trust_claimed"],
    "recovery_drill_external_mutation": product["recovery_drill_board"]["proof"]["external_mutation_claimed"],
    "recovery_drill_attestation": product["recovery_drill_board"]["proof"]["hardware_attestation_claimed"],
    "session_report_docker_daemon": product["session_report"]["proof"]["docker_daemon_observed_claimed"],
    "session_report_vm_iso": product["session_report"]["proof"]["boot_or_iso_proof_claimed"],
    "session_report_live_oauth": product["session_report"]["proof"]["live_oauth_claimed"],
    "session_report_live_browser": product["session_report"]["proof"]["live_browser_proof_claimed"],
    "session_report_release": product["session_report"]["proof"]["release_trust_claimed"],
    "session_report_external_mutation": product["session_report"]["proof"]["external_mutation_claimed"],
    "session_report_attestation": product["session_report"]["proof"]["hardware_attestation_claimed"],
    "evidence_hardware": product["evidence_dashboard"]["proof"]["hardware_attestation_claimed"],
    "proof_packet_vm_iso": product["customer_proof_packet"]["proof"]["boot_or_iso_proof_claimed"],
    "proof_packet_live_oauth": product["customer_proof_packet"]["proof"]["live_oauth_claimed"],
    "proof_packet_external_mutation": product["customer_proof_packet"]["proof"]["external_mutation_claimed"],
    "handoff_vm_iso": product["customer_handoff_bundle"]["proof"]["boot_or_iso_proof_claimed"],
    "handoff_live_oauth": product["customer_handoff_bundle"]["proof"]["live_oauth_claimed"],
    "handoff_external_mutation": product["customer_handoff_bundle"]["proof"]["external_mutation_claimed"],
    "promotion_docker_daemon_observed": product["proof_promotion_center"]["proof"]["docker_daemon_observed_claimed"],
    "promotion_vm_iso": product["proof_promotion_center"]["proof"]["boot_or_iso_proof_claimed"],
    "promotion_live_oauth": product["proof_promotion_center"]["proof"]["live_oauth_claimed"],
    "promotion_live_browser": product["proof_promotion_center"]["proof"]["live_browser_proof_claimed"],
    "promotion_release": product["proof_promotion_center"]["proof"]["release_trust_claimed"],
    "promotion_external_mutation": product["proof_promotion_center"]["proof"]["external_mutation_claimed"],
    "promotion_attestation": product["proof_promotion_center"]["proof"]["hardware_attestation_claimed"],
    "product_map_vm_iso": product["product_map"]["proof"]["boot_or_iso_proof_claimed"],
    "product_map_live_oauth": product["product_map"]["proof"]["live_oauth_claimed"],
    "product_map_browser": product["product_map"]["proof"]["live_browser_proof_claimed"],
    "product_map_release": product["product_map"]["proof"]["release_trust_claimed"],
    "product_map_mutation": product["product_map"]["proof"]["external_mutation_claimed"],
    "product_map_attestation": product["product_map"]["proof"]["hardware_attestation_claimed"],
    "runtime_home_snapshot_docker_daemon": product["completion_snapshot"]["proof"]["docker_daemon_observed_claimed"],
    "runtime_home_snapshot_boot": product["completion_snapshot"]["proof"]["boot_or_iso_proof_claimed"],
    "runtime_home_snapshot_live_oauth": product["completion_snapshot"]["proof"]["live_oauth_claimed"],
    "runtime_home_snapshot_live_browser": product["completion_snapshot"]["proof"]["live_browser_proof_claimed"],
    "runtime_home_snapshot_release": product["completion_snapshot"]["proof"]["release_trust_claimed"],
    "runtime_home_snapshot_mutation": product["completion_snapshot"]["proof"]["external_mutation_claimed"],
    "runtime_home_snapshot_attestation": product["completion_snapshot"]["proof"]["hardware_attestation_claimed"],
    "runtime_home_snapshot_auto_promotion": product["completion_snapshot"]["proof"]["automatic_claim_promotion"],
}
assert all(value is False for value in non_claims.values()), non_claims

ready_claims = {
    "runtime_home": product["proof"]["customer_facing_summary_ready"],
    "runtime_home_completion_snapshot": product["completion_snapshot"]["proof"]["customer_facing_runtime_home_snapshot_ready"],
    "guided_demo_journey": product["guided_demo_journey"]["proof"]["customer_guided_journey_ready"],
    "preview_readiness_board": product["preview_readiness_board"]["proof"]["customer_facing_preview_readiness_ready"],
    "onboarding_status": product["onboarding_status"]["proof"]["customer_onboarding_ready"],
    "work_inbox": product["work_inbox"]["proof"]["customer_facing_summary_ready"],
    "work_inbox_completion_snapshot": product["work_inbox"]["completion_snapshot"]["proof"]["customer_facing_work_inbox_snapshot_ready"],
    "activity_timeline": product["activity_timeline"]["proof"]["customer_facing_timeline_ready"],
    "capability_store": product["capability_store"]["proof"]["customer_facing_capability_store_ready"],
    "approval_center": product["approval_center"]["proof"]["customer_facing_approval_center_ready"],
    "proof_uploader": product["observed_proof_uploader"]["proof"]["customer_facing_proof_uploader_ready"],
    "release_trust": product["release_trust_panel"]["proof"]["customer_facing_release_trust_ready"],
    "attestation_status": product["attestation_status"]["proof"]["customer_facing_attestation_status_ready"],
    "recovery_center": product["recovery_center"]["proof"]["customer_facing_recovery_ready"],
    "recovery_drill_board": product["recovery_drill_board"]["proof"]["customer_facing_recovery_drills_ready"],
    "session_report": product["session_report"]["proof"]["customer_facing_session_report_ready"],
    "evidence_dashboard": product["evidence_dashboard"]["proof"]["customer_facing_evidence_ready"],
    "customer_proof_packet": product["customer_proof_packet"]["proof"]["customer_packet_ready"],
    "customer_handoff_bundle": product["customer_handoff_bundle"]["proof"]["customer_handoff_ready"],
    "proof_promotion_center": product["proof_promotion_center"]["proof"]["customer_facing_proof_promotion_ready"],
    "product_map": product["product_map"]["proof"]["customer_facing_product_map_ready"],
}
assert all(value is True for value in ready_claims.values()), ready_claims
PY

echo "docker product layer completion smoke: PASS"
