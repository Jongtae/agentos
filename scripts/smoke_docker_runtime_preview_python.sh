#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PREVIEW_SMOKE_PORT:-18787}"
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
curl -fsS "http://127.0.0.1:$PORT/api/status" > "$TMP_DIR/status.json"
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
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"message":"hi"}' \
  "http://127.0.0.1:$PORT/api/prompt" > "$TMP_DIR/prompt.json"
curl -fsS "http://127.0.0.1:$PORT/api/activity" > "$TMP_DIR/activity.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
status = json.loads((root / "status.json").read_text())
product = json.loads((root / "product.json").read_text())
onboarding = json.loads((root / "onboarding.json").read_text())
demo_journey = json.loads((root / "demo-journey.json").read_text())
work_inbox = json.loads((root / "work-inbox.json").read_text())
timeline = json.loads((root / "timeline.json").read_text())
capabilities = json.loads((root / "capabilities.json").read_text())
approvals = json.loads((root / "approvals.json").read_text())
proofs = json.loads((root / "proofs.json").read_text())
release_trust = json.loads((root / "release-trust.json").read_text())
attestation = json.loads((root / "attestation.json").read_text())
recovery = json.loads((root / "recovery.json").read_text())
evidence = json.loads((root / "evidence.json").read_text())
prompt = json.loads((root / "prompt.json").read_text())
activity = json.loads((root / "activity.json").read_text())
home = (root / "home.html").read_text()

assert status["proof"]["docker_preview_surface_ready"] is True
assert status["proof"]["product_layer_runtime_home_ready"] is True
assert status["proof"]["boot_or_iso_proof"] is False
assert status["telegram"]["transport"] == "polling_preview"
assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["docker_main_try_path"] is True
assert product["proof"]["boot_or_iso_proof_claimed"] is False
assert product["proof"]["customer_facing_summary_ready"] is True
assert product["onboarding_status"]["schema_version"] == "agentos-product-layer-onboarding-status.v1"
assert product["guided_demo_journey"]["schema_version"] == "agentos-product-layer-guided-demo-journey.v1"
assert product["work_inbox"]["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert product["activity_timeline"]["schema_version"] == "agentos-product-layer-activity-timeline.v1"
assert product["capability_store"]["schema_version"] == "agentos-product-layer-capability-store.v1"
assert product["approval_center"]["schema_version"] == "agentos-product-layer-approval-center.v1"
assert product["observed_proof_uploader"]["schema_version"] == "agentos-product-layer-observed-proof-uploader.v1"
assert product["release_trust_panel"]["schema_version"] == "agentos-product-layer-release-trust-panel.v1"
assert product["attestation_status"]["schema_version"] == "agentos-product-layer-attestation-status.v1"
assert product["recovery_center"]["schema_version"] == "agentos-product-layer-recovery-center.v1"
assert product["evidence_dashboard"]["schema_version"] == "agentos-product-layer-evidence-dashboard.v1"
assert {feature["id"] for feature in product["features"]} >= {
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
    "work_inbox",
    "activity_timeline",
    "attestation_status",
    "recovery_center",
    "evidence_dashboard",
}
assert demo_journey["schema_version"] == "agentos-product-layer-guided-demo-journey.v1"
assert demo_journey["proof"]["docker_preview_ready"] is True
assert demo_journey["proof"]["customer_guided_journey_ready"] is True
assert demo_journey["proof"]["boot_or_iso_proof_claimed"] is False
assert demo_journey["proof"]["live_oauth_claimed"] is False
assert demo_journey["proof"]["live_browser_proof_claimed"] is False
assert demo_journey["proof"]["release_proof_claimed"] is False
assert demo_journey["proof"]["external_mutation_claimed"] is False
assert demo_journey["proof"]["hardware_attestation_claimed"] is False
assert {stage["id"] for stage in demo_journey["stages"]} == {
    "start_at_runtime_home",
    "inspect_work_inbox",
    "run_first_prompt",
    "review_activity_timeline",
    "check_evidence_and_recovery",
}
assert {item["id"] for item in demo_journey["expected_outcomes"]} == {
    "runtime_reachable",
    "read_first_work_visible",
    "activity_and_records_visible",
    "proof_boundaries_visible",
    "recovery_next_steps_visible",
}
assert {item["kind"] for item in demo_journey["expected_outcomes"]} >= {"success", "blocked_until_observed"}
assert onboarding["schema_version"] == "agentos-product-layer-onboarding-status.v1"
assert onboarding["proof"]["docker_preview_ready"] is True
assert onboarding["proof"]["customer_onboarding_ready"] is True
assert onboarding["proof"]["requires_api_key_for_basic_preview"] is False
assert onboarding["proof"]["boot_or_iso_proof_claimed"] is False
assert onboarding["proof"]["live_oauth_claimed"] is False
assert onboarding["proof"]["live_browser_proof_claimed"] is False
assert onboarding["proof"]["release_proof_claimed"] is False
assert onboarding["proof"]["external_mutation_claimed"] is False
assert onboarding["proof"]["hardware_attestation_claimed"] is False
assert onboarding["entrypoints"]["browser_url"] == "http://localhost:8787"
assert onboarding["entrypoints"]["onboarding_api"] == "/api/onboarding"
assert onboarding["validation"]["onboarding_status_contract_smoke"] == "scripts/smoke_docker_onboarding_status_contract.sh"
assert {step["id"] for step in onboarding["steps"]} >= {
    "clone_repository",
    "copy_env",
    "start_docker_preview",
    "open_runtime_home",
    "try_prompt",
}
assert {item["id"] for item in onboarding["readiness_checklist"]} >= {
    "quickstart_documented",
    "preview_entrypoints_available",
    "basic_preview_no_api_key",
    "docker_validation_available",
    "observed_proof_boundaries_visible",
}
assert {item["id"]: item["state"] for item in onboarding["readiness_checklist"]}["observed_proof_boundaries_visible"] == "blocked_on_external_evidence"
assert work_inbox["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert work_inbox["proof"]["docker_preview_ready"] is True
assert work_inbox["proof"]["read_first_only"] is True
assert work_inbox["proof"]["external_mutation_claimed"] is False
assert work_inbox["proof"]["live_oauth_claimed"] is False
assert {source["id"] for source in work_inbox["sources"]} >= {"native_fixture", "maildir", "gmail", "calendar"}
assert {workflow["id"] for workflow in work_inbox["workflows"]} >= {"inbox_summary", "draft_preparation", "search_and_triage"}
assert timeline["schema_version"] == "agentos-product-layer-activity-timeline.v1"
assert timeline["proof"]["docker_preview_ready"] is True
assert timeline["proof"]["user_visible_records_ready"] is True
assert timeline["proof"]["external_app_execution_claimed"] is False
assert timeline["proof"]["live_provider_proof_claimed"] is False
assert timeline["proof"]["customer_facing_timeline_ready"] is True
assert "os_events_jsonl" in timeline["records"]
assert capabilities["schema_version"] == "agentos-product-layer-capability-store.v1"
assert capabilities["proof"]["docker_preview_ready"] is True
assert capabilities["proof"]["registry_loaded"] is True
assert capabilities["proof"]["destructive_action_executed_by_default"] is False
assert capabilities["proof"]["external_write_claimed"] is False
assert capabilities["proof"]["live_provider_proof_claimed"] is False
assert capabilities["proof"]["customer_facing_capability_store_ready"] is True
assert {"safe_read", "external_read", "destructive_blocked"} <= set(capabilities["permission_levels"])
capability_ids = {item["id"] for item in capabilities["capabilities"]}
assert {"runtime_status", "gmail_read", "gmail_send"} <= capability_ids
states_by_id = {item["id"]: item["state"] for item in capabilities["capabilities"]}
assert states_by_id["runtime_status"] == "docker_preview_ready"
assert states_by_id["gmail_read"] == "requires_setup_or_confirmation"
assert states_by_id["gmail_send"] == "blocked"
assert approvals["schema_version"] == "agentos-product-layer-approval-center.v1"
assert approvals["proof"]["docker_preview_ready"] is True
assert approvals["proof"]["approval_records_ready"] is True
assert approvals["proof"]["approval_execution_claimed"] is False
assert approvals["proof"]["destructive_action_executed_by_default"] is False
assert approvals["proof"]["external_write_claimed"] is False
assert approvals["proof"]["live_provider_proof_claimed"] is False
assert approvals["proof"]["customer_facing_approval_center_ready"] is True
approval_states = {item["id"]: item["state"] for item in approvals["items"]}
assert approval_states["gmail_read"] == "needs_setup_or_observed_proof"
assert approval_states["restart_runtime"] == "needs_lifecycle_confirmation"
assert approval_states["gmail_send"] == "blocked"
assert proofs["schema_version"] == "agentos-product-layer-observed-proof-uploader.v1"
assert proofs["proof"]["docker_preview_ready"] is True
assert proofs["proof"]["mock_contract_ready"] is True
assert proofs["proof"]["file_upload_execution_claimed"] is False
assert proofs["proof"]["claim_promotion_claimed"] is False
assert proofs["proof"]["secret_material_allowed"] is False
assert proofs["proof"]["customer_facing_proof_uploader_ready"] is True
assert proofs["mock_submission_contract"]["secret_material_allowed"] is False
assert proofs["mock_submission_contract"]["claim_promotion_automatic"] is False
assert {"proof_type", "observed_at", "sanitized_artifact_ref", "reviewer_note"} <= set(proofs["mock_submission_contract"]["required_fields"])
assert {item["id"] for item in proofs["proof_types"]} >= {
    "live-oauth-readonly",
    "vm-iso-boot-rejoin",
    "live-browser-observed",
    "release-trust",
    "hardware-attestation",
}
assert release_trust["schema_version"] == "agentos-product-layer-release-trust-panel.v1"
assert release_trust["proof"]["docker_preview_ready"] is True
assert release_trust["proof"]["release_artifact_observed"] is False
assert release_trust["proof"]["manifest_validated"] is False
assert release_trust["proof"]["checksum_published"] is False
assert release_trust["proof"]["signing_observed"] is False
assert release_trust["proof"]["release_uploaded"] is False
assert release_trust["proof"]["vm_iso_release_proof_completed"] is False
assert release_trust["proof"]["customer_facing_release_trust_ready"] is True
assert release_trust["preflight"]["local_manifest_checksum_preflight_available"] is True
assert {item["id"] for item in release_trust["checks"]} >= {
    "artifact-manifest",
    "checksum-publication",
    "signing-evidence",
    "secret-free-review",
    "vm-iso-release-proof",
}
assert attestation["schema_version"] == "agentos-product-layer-attestation-status.v1"
assert attestation["proof"]["docker_preview_ready"] is True
assert attestation["proof"]["secure_boot_observed"] is False
assert attestation["proof"]["tpm_pcr_observed"] is False
assert attestation["proof"]["event_log_observed"] is False
assert attestation["proof"]["ima_runtime_integrity_observed"] is False
assert attestation["proof"]["hardware_attestation_observed"] is False
assert attestation["proof"]["customer_facing_attestation_status_ready"] is True
assert attestation["boundary"]["docker_is_attestation_proof"] is False
assert {item["id"] for item in attestation["checks"]} >= {
    "secure-boot-state",
    "tpm-pcr-evidence",
    "event-log-review",
    "ima-runtime-integrity",
    "hardware-backed-attestation",
}
assert recovery["schema_version"] == "agentos-product-layer-recovery-center.v1"
assert recovery["proof"]["docker_preview_ready"] is True
assert recovery["proof"]["customer_facing_recovery_ready"] is True
assert recovery["proof"]["boot_or_iso_proof_claimed"] is False
assert recovery["proof"]["live_oauth_claimed"] is False
assert recovery["proof"]["live_browser_proof_claimed"] is False
assert recovery["proof"]["release_trust_claimed"] is False
assert recovery["proof"]["hardware_attestation_claimed"] is False
assert {item["id"] for item in recovery["items"]} >= {
    "vm-iso-observed-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "attestation-proof",
}
assert evidence["schema_version"] == "agentos-product-layer-evidence-dashboard.v1"
assert evidence["proof"]["docker_preview_ready"] is True
assert evidence["proof"]["customer_facing_evidence_ready"] is True
assert evidence["proof"]["boot_or_iso_proof_claimed"] is False
assert evidence["proof"]["live_oauth_claimed"] is False
assert evidence["proof"]["live_browser_proof_claimed"] is False
assert evidence["proof"]["release_trust_claimed"] is False
assert evidence["proof"]["hardware_attestation_claimed"] is False
assert {item["id"] for item in evidence["evidence"]} >= {
    "docker-runtime-preview",
    "phase2-golden-runtime-loop",
    "work-inbox-read-first",
    "activity-timeline",
}
assert {item["id"] for item in evidence["non_claims"]} >= {
    "vm-iso-boot-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "hardware-attestation-proof",
}
assert "Runtime Home" in home
assert "Docker Onboarding Status" in home
assert "onboarding JSON" in home
assert "Recovery Center" in home
assert "recovery JSON" in home
assert "Work Inbox" in home
assert "Inbox Workflows" in home
assert "Activity Timeline" in home
assert "timeline JSON" in home
assert "Capability Store" in home
assert "capabilities JSON" in home
assert "Approval Center" in home
assert "approvals JSON" in home
assert "Observed Proof Uploader" in home
assert "proofs JSON" in home
assert "Release Trust Panel" in home
assert "release trust JSON" in home
assert "Attestation Status" in home
assert "attestation JSON" in home
assert "Evidence Dashboard" in home
assert "evidence JSON" in home
assert prompt["ok"] is True
assert prompt["intent"] == "greeting", prompt
assert "DuckDuckGo" not in json.dumps(prompt)
assert activity["activity_feed_ready"] is True
assert len(activity["events"]) >= 1

combined = "\n".join(p.read_text(errors="ignore") for p in root.glob("*.json"))
for forbidden in ("AGENTOS_TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "xoxb-", "sk-"):
    assert forbidden not in combined
PY

echo "docker runtime preview python smoke: PASS"
