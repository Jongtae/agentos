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
curl -fsS "http://127.0.0.1:$PORT/api/work-inbox" > "$TMP_DIR/work-inbox.json"
curl -fsS "http://127.0.0.1:$PORT/api/timeline" > "$TMP_DIR/timeline.json"
curl -fsS "http://127.0.0.1:$PORT/api/capabilities" > "$TMP_DIR/capabilities.json"
curl -fsS "http://127.0.0.1:$PORT/api/approvals" > "$TMP_DIR/approvals.json"
curl -fsS "http://127.0.0.1:$PORT/api/proofs" > "$TMP_DIR/proofs.json"
curl -fsS "http://127.0.0.1:$PORT/api/release-trust" > "$TMP_DIR/release-trust.json"
curl -fsS "http://127.0.0.1:$PORT/api/attestation" > "$TMP_DIR/attestation.json"
curl -fsS "http://127.0.0.1:$PORT/api/recovery" > "$TMP_DIR/recovery.json"
curl -fsS "http://127.0.0.1:$PORT/api/evidence" > "$TMP_DIR/evidence.json"
curl -fsS "http://127.0.0.1:$PORT/api/proof-packet" > "$TMP_DIR/proof-packet.json"
curl -fsS "http://127.0.0.1:$PORT/api/customer-handoff" > "$TMP_DIR/customer-handoff.json"
curl -fsS "http://127.0.0.1:$PORT/api/proof-promotion" > "$TMP_DIR/proof-promotion.json"
curl -fsS "http://127.0.0.1:$PORT/api/product-map" > "$TMP_DIR/product-map.json"

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
    "work_inbox": ("work-inbox.json", "agentos-product-layer-work-inbox.v1", "Work Inbox"),
    "activity_timeline": ("timeline.json", "agentos-product-layer-activity-timeline.v1", "Activity Timeline"),
    "capability_store": ("capabilities.json", "agentos-product-layer-capability-store.v1", "Capability Store"),
    "approval_center": ("approvals.json", "agentos-product-layer-approval-center.v1", "Approval Center"),
    "observed_proof_uploader": ("proofs.json", "agentos-product-layer-observed-proof-uploader.v1", "Observed Proof Uploader"),
    "release_trust_panel": ("release-trust.json", "agentos-product-layer-release-trust-panel.v1", "Release Trust Panel"),
    "attestation_status": ("attestation.json", "agentos-product-layer-attestation-status.v1", "Attestation Status"),
    "recovery_center": ("recovery.json", "agentos-product-layer-recovery-center.v1", "Recovery Center"),
    "evidence_dashboard": ("evidence.json", "agentos-product-layer-evidence-dashboard.v1", "Evidence Dashboard"),
    "customer_proof_packet": ("proof-packet.json", "agentos-product-layer-customer-proof-packet.v1", "Customer Proof Packet"),
    "customer_handoff_bundle": ("customer-handoff.json", "agentos-product-layer-customer-handoff-bundle.v1", "Customer Handoff Bundle"),
    "proof_promotion_center": ("proof-promotion.json", "agentos-product-layer-proof-promotion-center.v1", "Proof Promotion Center"),
    "product_map": ("product-map.json", "agentos-product-layer-map.v1", "Product Layer Map"),
}

assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["docker_main_try_path"] is True
assert product["proof"]["boot_or_iso_proof_claimed"] is False
assert product["proof"]["live_oauth_claimed"] is False
assert product["proof"]["live_browser_proof_claimed"] is False

feature_ids = {feature["id"] for feature in product["features"]}
expected_feature_ids = {"runtime_home", *surfaces.keys()}
assert expected_feature_ids <= feature_ids, sorted(expected_feature_ids - feature_ids)
assert "Runtime Home" in home

for key, (filename, schema, label) in surfaces.items():
    embedded = product[key]
    endpoint = json.loads((root / filename).read_text())
    assert embedded["schema_version"] == schema, key
    assert endpoint["schema_version"] == schema, key
    assert label in home, label

assert product["onboarding_status"]["validation"]["onboarding_status_contract_smoke"] == "scripts/smoke_docker_onboarding_status_contract.sh"
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
assert product["product_map"]["proof"]["customer_facing_product_map_ready"] is True
assert product["product_map"]["proof"]["boot_or_iso_proof_claimed"] is False
assert {group["id"] for group in product["product_map"]["surface_groups"]} >= {
    "start_here",
    "do_work",
    "prove_and_handoff",
    "blocked_until_observed",
}
assert "proof_promotion_center" in product["product_map"]["recommended_path"]
assert "Product Layer Map" in home
assert "product map JSON" in home
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
    "onboarding_boot_or_iso": product["onboarding_status"]["proof"]["boot_or_iso_proof_claimed"],
    "onboarding_live_oauth": product["onboarding_status"]["proof"]["live_oauth_claimed"],
    "work_inbox_live_oauth": product["work_inbox"]["proof"]["live_oauth_claimed"],
    "work_inbox_external_mutation": product["work_inbox"]["proof"]["external_mutation_claimed"],
    "timeline_external_app": product["activity_timeline"]["proof"]["external_app_execution_claimed"],
    "capability_external_write": product["capability_store"]["proof"]["external_write_claimed"],
    "approval_execution": product["approval_center"]["proof"]["approval_execution_claimed"],
    "proof_upload_execution": product["observed_proof_uploader"]["proof"]["file_upload_execution_claimed"],
    "release_uploaded": product["release_trust_panel"]["proof"]["release_uploaded"],
    "release_vm_iso": product["release_trust_panel"]["proof"]["vm_iso_release_proof_completed"],
    "secure_boot": product["attestation_status"]["proof"]["secure_boot_observed"],
    "hardware_attestation": product["attestation_status"]["proof"]["hardware_attestation_observed"],
    "recovery_vm_iso": product["recovery_center"]["proof"]["boot_or_iso_proof_claimed"],
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
}
assert all(value is False for value in non_claims.values()), non_claims

ready_claims = {
    "runtime_home": product["proof"]["customer_facing_summary_ready"],
    "guided_demo_journey": product["guided_demo_journey"]["proof"]["customer_guided_journey_ready"],
    "onboarding_status": product["onboarding_status"]["proof"]["customer_onboarding_ready"],
    "work_inbox": product["work_inbox"]["proof"]["customer_facing_summary_ready"],
    "activity_timeline": product["activity_timeline"]["proof"]["customer_facing_timeline_ready"],
    "capability_store": product["capability_store"]["proof"]["customer_facing_capability_store_ready"],
    "approval_center": product["approval_center"]["proof"]["customer_facing_approval_center_ready"],
    "proof_uploader": product["observed_proof_uploader"]["proof"]["customer_facing_proof_uploader_ready"],
    "release_trust": product["release_trust_panel"]["proof"]["customer_facing_release_trust_ready"],
    "attestation_status": product["attestation_status"]["proof"]["customer_facing_attestation_status_ready"],
    "recovery_center": product["recovery_center"]["proof"]["customer_facing_recovery_ready"],
    "evidence_dashboard": product["evidence_dashboard"]["proof"]["customer_facing_evidence_ready"],
    "customer_proof_packet": product["customer_proof_packet"]["proof"]["customer_packet_ready"],
    "customer_handoff_bundle": product["customer_handoff_bundle"]["proof"]["customer_handoff_ready"],
    "proof_promotion_center": product["proof_promotion_center"]["proof"]["customer_facing_proof_promotion_ready"],
    "product_map": product["product_map"]["proof"]["customer_facing_product_map_ready"],
}
assert all(value is True for value in ready_claims.values()), ready_claims
PY

echo "docker product layer completion smoke: PASS"
