#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-golden-demo.v1"

PRACTICAL_SMOKES = [
    "scripts/smoke_phase2_intent_eval.sh",
    "scripts/smoke_phase2_runtime_preview.sh",
    "scripts/smoke_phase2_setup_status.sh",
    "scripts/smoke_phase2_data_boundary.sh",
    "scripts/smoke_phase2_capability_result.sh",
    "scripts/smoke_phase2_core_dispatch.sh",
    "scripts/smoke_phase2_gmail_fixture.sh",
    "scripts/smoke_phase2_calendar_fixture.sh",
    "scripts/smoke_phase2_records.sh",
    "scripts/smoke_phase2_activity_vocabulary.sh",
    "scripts/smoke_phase2_lifecycle_recovery.sh",
    "scripts/smoke_phase2_run_cli.sh",
    "scripts/smoke_gmail_setup_page.sh",
    "scripts/smoke_gmail_live_missing_credentials.sh",
    "scripts/smoke_phase2_gmail_live_blocked.sh",
    "scripts/smoke_gmail_live_acceptance_pack.sh",
    "scripts/smoke_calendar_live_acceptance_pack.sh",
    "scripts/smoke_calendar_live_adapter_candidate_boundary.sh",
    "scripts/smoke_browser_fallback_observed_acceptance_pack.sh",
    "scripts/smoke_vm_iso_proof_preflight.sh",
    "scripts/smoke_public_preview_operations.sh",
    "scripts/smoke_release_manifest_checksum_preflight.sh",
    "scripts/smoke_inbox_capability_ownership_boundary.sh",
    "scripts/smoke_maildir_inbox_intake_proof_boundary.sh",
    "scripts/smoke_inbox_workflow_promotion_boundary.sh",
    "scripts/smoke_verified_boot_attestation_boundary.sh",
    "scripts/smoke_observed_proof_intake_boundary.sh",
    "scripts/smoke_observed_proof_intake_validator.sh",
    "scripts/smoke_capability_graduation_registry.sh",
    "scripts/smoke_docker_product_layer_completion.sh",
    "scripts/smoke_docker_customer_onboarding_quickstart.sh",
    "scripts/smoke_docker_onboarding_status_contract.sh",
    "scripts/smoke_docker_guided_demo_journey.sh",
    "scripts/smoke_docker_preview_readiness_board.sh",
    "scripts/smoke_docker_next_work_board.sh",
    "scripts/smoke_docker_observed_proof_request_board.sh",
    "scripts/smoke_docker_recovery_drill_board.sh",
    "scripts/smoke_docker_session_report.sh",
    "scripts/smoke_docker_customer_proof_packet.sh",
    "scripts/smoke_docker_customer_handoff_bundle.sh",
    "scripts/smoke_docker_proof_promotion_center.sh",
    "scripts/smoke_docker_product_layer_map.sh",
    "scripts/smoke_docker_release_trust_panel.sh",
]

EXPLICIT_BLOCKERS = [
    {
        "id": "gmail-oauth-live",
        "reason": "Real Gmail OAuth credentials are not available in automated local proof.",
        "recovery_action": "Provide explicit credentials and run a non-mutating read/search/draft live adapter smoke.",
    },
    {
        "id": "vm-iso-proof",
        "reason": "VM/ISO proof is outside this local quick runner and must not be claimed unless observed.",
        "recovery_action": "Run the documented VM/ISO proof flow and attach observed logs before release signoff.",
    },
]


def run_golden_demo(root: Path) -> dict:
    results = []
    for smoke in PRACTICAL_SMOKES:
        path = root / smoke
        proc = subprocess.run([str(path)], cwd=root, text=True, capture_output=True, check=False)
        results.append(
            {
                "name": smoke,
                "returncode": proc.returncode,
                "ok": proc.returncode == 0,
                "stdout_tail": _tail(proc.stdout),
                "stderr_tail": _tail(proc.stderr),
            }
        )
    ok = all(result["ok"] for result in results)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "practical_smoke_count": len(results),
        "practical_smokes_passed": sum(1 for result in results if result["ok"]),
        "results": results,
        "explicit_blockers": EXPLICIT_BLOCKERS,
        "proof": {
            "ok": ok,
            "docker_local_smoke_completed": ok,
            "gmail_oauth_live_completed": False,
            "vm_iso_proof_completed": False,
            "runtime_proof_completed": ok,
        },
    }


def _tail(value: str, limit: int = 500) -> str:
    text = value.strip()
    return text[-limit:] if len(text) > limit else text


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 2 golden demo acceptance proof")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    payload = run_golden_demo(root)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
