#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: docker command is not installed or not on PATH"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: docker compose is unavailable"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: Docker daemon is not running or not reachable"
  echo "recovery: start Docker Desktop, then rerun scripts/smoke_docker_runtime_preview.sh"
  exit 1
fi

TMP_CID=""
cleanup() {
  if [ -n "$TMP_CID" ]; then
    docker rm -f "$TMP_CID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

dump_container_diagnostics() {
  if [ -z "$TMP_CID" ]; then
    return
  fi
  echo "docker runtime preview smoke: container status"
  docker ps -a --filter "id=$TMP_CID" --no-trunc || true
  echo "docker runtime preview smoke: container logs"
  docker logs "$TMP_CID" || true
}

docker compose config >/dev/null
docker compose build agent-os >/dev/null

TMP_CID="$(
  docker run -d \
    -p 18787:8787 \
    -e DEFAULT_WORKSPACE=/app/workspaces/default \
    -e AGENTOS_USER_DATA_ROOT=/var/lib/agentos/user \
    -e AGENTOS_DOCKER_TELEGRAM_POLLING=false \
    agent-os:latest
)"

READY=false
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18787/healthz >/dev/null 2>&1; then
    READY=true
    break
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$TMP_CID" 2>/dev/null || true)" != "true" ]; then
    echo "docker runtime preview smoke: FAIL"
    echo "reason: container exited before /healthz became ready"
    dump_container_diagnostics
    exit 1
  fi
  sleep 1
done

if [ "$READY" != "true" ]; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: /healthz did not become ready before timeout"
  dump_container_diagnostics
  exit 1
fi

curl -fsS http://127.0.0.1:18787/healthz >/dev/null
curl -fsS http://127.0.0.1:18787/ > /tmp/agentos-docker-home.html
curl -fsS http://127.0.0.1:18787/api/status > /tmp/agentos-docker-status.json
curl -fsS http://127.0.0.1:18787/api/product > /tmp/agentos-docker-product.json
curl -fsS http://127.0.0.1:18787/api/onboarding > /tmp/agentos-docker-onboarding.json
curl -fsS http://127.0.0.1:18787/api/demo-journey > /tmp/agentos-docker-demo-journey.json
curl -fsS http://127.0.0.1:18787/api/work-inbox > /tmp/agentos-docker-work-inbox.json
curl -fsS http://127.0.0.1:18787/api/timeline > /tmp/agentos-docker-timeline.json
curl -fsS http://127.0.0.1:18787/api/capabilities > /tmp/agentos-docker-capabilities.json
curl -fsS http://127.0.0.1:18787/api/approvals > /tmp/agentos-docker-approvals.json
curl -fsS http://127.0.0.1:18787/api/proofs > /tmp/agentos-docker-proofs.json
curl -fsS http://127.0.0.1:18787/api/release-trust > /tmp/agentos-docker-release-trust.json
curl -fsS http://127.0.0.1:18787/api/attestation > /tmp/agentos-docker-attestation.json
curl -fsS http://127.0.0.1:18787/api/recovery > /tmp/agentos-docker-recovery.json
curl -fsS http://127.0.0.1:18787/api/evidence > /tmp/agentos-docker-evidence.json
curl -fsS http://127.0.0.1:18787/api/proof-packet > /tmp/agentos-docker-proof-packet.json
curl -fsS http://127.0.0.1:18787/api/customer-handoff > /tmp/agentos-docker-customer-handoff.json

python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/agentos-docker-status.json").read_text())
product = json.loads(Path("/tmp/agentos-docker-product.json").read_text())
onboarding = json.loads(Path("/tmp/agentos-docker-onboarding.json").read_text())
demo_journey = json.loads(Path("/tmp/agentos-docker-demo-journey.json").read_text())
work_inbox = json.loads(Path("/tmp/agentos-docker-work-inbox.json").read_text())
timeline = json.loads(Path("/tmp/agentos-docker-timeline.json").read_text())
capabilities = json.loads(Path("/tmp/agentos-docker-capabilities.json").read_text())
approvals = json.loads(Path("/tmp/agentos-docker-approvals.json").read_text())
proofs = json.loads(Path("/tmp/agentos-docker-proofs.json").read_text())
release_trust = json.loads(Path("/tmp/agentos-docker-release-trust.json").read_text())
attestation = json.loads(Path("/tmp/agentos-docker-attestation.json").read_text())
recovery = json.loads(Path("/tmp/agentos-docker-recovery.json").read_text())
evidence = json.loads(Path("/tmp/agentos-docker-evidence.json").read_text())
proof_packet = json.loads(Path("/tmp/agentos-docker-proof-packet.json").read_text())
customer_handoff = json.loads(Path("/tmp/agentos-docker-customer-handoff.json").read_text())
home = Path("/tmp/agentos-docker-home.html").read_text()
assert payload["proof"]["docker_preview_surface_ready"] is True
assert payload["proof"]["product_layer_runtime_home_ready"] is True
assert payload["proof"]["boot_or_iso_proof"] is False
assert payload["proof"]["secrets_redacted"] is True
assert payload["telegram"]["transport"] == "polling_preview"
assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["docker_main_try_path"] is True
assert product["proof"]["boot_or_iso_proof_claimed"] is False
assert product["onboarding_status"]["schema_version"] == "agentos-product-layer-onboarding-status.v1"
assert product["guided_demo_journey"]["schema_version"] == "agentos-product-layer-guided-demo-journey.v1"
assert product["customer_proof_packet"]["schema_version"] == "agentos-product-layer-customer-proof-packet.v1"
assert product["customer_handoff_bundle"]["schema_version"] == "agentos-product-layer-customer-handoff-bundle.v1"
assert onboarding["schema_version"] == "agentos-product-layer-onboarding-status.v1"
assert demo_journey["schema_version"] == "agentos-product-layer-guided-demo-journey.v1"
assert demo_journey["proof"]["customer_guided_journey_ready"] is True
assert demo_journey["proof"]["boot_or_iso_proof_claimed"] is False
assert demo_journey["proof"]["live_oauth_claimed"] is False
assert demo_journey["proof"]["external_mutation_claimed"] is False
assert {item["id"] for item in demo_journey["expected_outcomes"]} >= {
    "runtime_reachable",
    "proof_boundaries_visible",
    "recovery_next_steps_visible",
}
assert demo_journey["completion_summary"]["id"] == "docker_guided_demo_complete"
assert len(demo_journey["completion_summary"]["next_blockers"]) >= 3
assert onboarding["proof"]["docker_preview_ready"] is True
assert onboarding["proof"]["requires_api_key_for_basic_preview"] is False
assert onboarding["proof"]["boot_or_iso_proof_claimed"] is False
assert onboarding["proof"]["live_oauth_claimed"] is False
assert onboarding["proof"]["hardware_attestation_claimed"] is False
assert onboarding["validation"]["onboarding_status_contract_smoke"] == "scripts/smoke_docker_onboarding_status_contract.sh"
assert {item["id"] for item in onboarding["readiness_checklist"]} >= {
    "quickstart_documented",
    "preview_entrypoints_available",
    "basic_preview_no_api_key",
    "docker_validation_available",
    "observed_proof_boundaries_visible",
}
assert work_inbox["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert work_inbox["proof"]["read_first_only"] is True
assert work_inbox["proof"]["external_mutation_claimed"] is False
assert timeline["schema_version"] == "agentos-product-layer-activity-timeline.v1"
assert timeline["proof"]["docker_preview_ready"] is True
assert timeline["proof"]["external_app_execution_claimed"] is False
assert timeline["proof"]["live_provider_proof_claimed"] is False
assert timeline["proof"]["customer_facing_timeline_ready"] is True
assert capabilities["schema_version"] == "agentos-product-layer-capability-store.v1"
assert capabilities["proof"]["docker_preview_ready"] is True
assert capabilities["proof"]["destructive_action_executed_by_default"] is False
assert capabilities["proof"]["external_write_claimed"] is False
assert capabilities["proof"]["customer_facing_capability_store_ready"] is True
assert approvals["schema_version"] == "agentos-product-layer-approval-center.v1"
assert approvals["proof"]["docker_preview_ready"] is True
assert approvals["proof"]["approval_execution_claimed"] is False
assert approvals["proof"]["destructive_action_executed_by_default"] is False
assert approvals["proof"]["external_write_claimed"] is False
assert approvals["proof"]["customer_facing_approval_center_ready"] is True
assert proofs["schema_version"] == "agentos-product-layer-observed-proof-uploader.v1"
assert proofs["proof"]["docker_preview_ready"] is True
assert proofs["proof"]["file_upload_execution_claimed"] is False
assert proofs["proof"]["claim_promotion_claimed"] is False
assert proofs["proof"]["secret_material_allowed"] is False
assert release_trust["schema_version"] == "agentos-product-layer-release-trust-panel.v1"
assert release_trust["proof"]["docker_preview_ready"] is True
assert release_trust["proof"]["release_artifact_observed"] is False
assert release_trust["proof"]["signing_observed"] is False
assert release_trust["proof"]["release_uploaded"] is False
assert release_trust["proof"]["vm_iso_release_proof_completed"] is False
assert attestation["schema_version"] == "agentos-product-layer-attestation-status.v1"
assert attestation["proof"]["docker_preview_ready"] is True
assert attestation["proof"]["secure_boot_observed"] is False
assert attestation["proof"]["tpm_pcr_observed"] is False
assert attestation["proof"]["event_log_observed"] is False
assert attestation["proof"]["hardware_attestation_observed"] is False
assert attestation["boundary"]["docker_is_attestation_proof"] is False
assert recovery["schema_version"] == "agentos-product-layer-recovery-center.v1"
assert recovery["proof"]["docker_preview_ready"] is True
assert recovery["proof"]["boot_or_iso_proof_claimed"] is False
assert recovery["proof"]["live_oauth_claimed"] is False
assert recovery["proof"]["live_browser_proof_claimed"] is False
assert recovery["proof"]["customer_facing_recovery_ready"] is True
assert evidence["schema_version"] == "agentos-product-layer-evidence-dashboard.v1"
assert evidence["proof"]["docker_preview_ready"] is True
assert evidence["proof"]["boot_or_iso_proof_claimed"] is False
assert evidence["proof"]["live_oauth_claimed"] is False
assert evidence["proof"]["customer_facing_evidence_ready"] is True
assert proof_packet["schema_version"] == "agentos-product-layer-customer-proof-packet.v1"
assert proof_packet["proof"]["customer_packet_ready"] is True
assert proof_packet["proof"]["claim_promotion_automatic"] is False
assert {item["id"] for item in proof_packet["readiness_checklist"]} >= {
    "completed_claims_present",
    "validation_commands_present",
    "proof_sources_linked",
    "non_claims_explicit",
    "automatic_claim_promotion_disabled",
}
assert customer_handoff["schema_version"] == "agentos-product-layer-customer-handoff-bundle.v1"
assert customer_handoff["proof"]["customer_handoff_ready"] is True
assert customer_handoff["proof"]["boot_or_iso_proof_claimed"] is False
assert "Runtime Home" in home
assert "Docker Onboarding Status" in home
assert "onboarding JSON" in home
assert "Recovery Center" in home
assert "recovery JSON" in home
assert "Work Inbox" in home
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
assert "Customer Handoff Bundle" in home
assert "customer handoff JSON" in home
PY

curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"message":"hi"}' \
  http://127.0.0.1:18787/api/prompt > /tmp/agentos-docker-prompt.json

python3 - <<'PY'
import json
from pathlib import Path
text = Path("/tmp/agentos-docker-prompt.json").read_text()
payload = json.loads(text)
assert payload["ok"] is True, payload
assert payload["intent"] in {"greeting", "unknown_needs_clarification", "status", "runtime_status"}, payload
for forbidden in ("AGENTOS_TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "xoxb-", "sk-"):
    assert forbidden not in text
PY

curl -fsS http://127.0.0.1:18787/api/activity > /tmp/agentos-docker-activity.json
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/agentos-docker-activity.json").read_text())
assert payload["activity_feed_ready"] is True
assert isinstance(payload["events"], list)
PY

echo "docker runtime preview smoke: PASS"
