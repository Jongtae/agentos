#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

echo "[1/26] Python compile check"
python3 -m py_compile $(rg --files src -g '*.py')

echo "[2/26] Unit tests"
python3 -m unittest discover -s tests -v

echo "[3/26] Regression checks"
scripts/regression_checks.sh

echo "[4/26] Failure matrix"
scripts/failure_matrix.sh

echo "[5/26] No-TUI smoke (fake codex)"
scripts/smoke_no_tui_fake_codex.sh

echo "[6/26] Snapshot schema validation"
scripts/validate_snapshot_output.sh

echo "[7/26] Demo boot flow"
scripts/demo_boot_flow.sh

echo "[8/26] Diagnostics bundle validation"
scripts/validate_diagnostics_bundle.sh

echo "[9/26] Phase2 runner smoke"
scripts/smoke_phase2_runner.sh

echo "[10/26] Phase2 migration/fallback smoke"
scripts/smoke_phase2_migration_fallback.sh

echo "[11/26] Memory recall benchmark smoke"
scripts/smoke_memory_recall_benchmark.sh

echo "[12/26] Memory index rebuild smoke"
scripts/smoke_memory_index_rebuild.sh

echo "[13/26] Memory summarizer quality smoke"
scripts/smoke_memory_summarizer_quality.sh

echo "[14/26] Browser worker boundary smoke"
scripts/smoke_browser_worker_boundary.sh

echo "[15/26] Browser action matrix smoke"
scripts/smoke_browser_action_matrix.sh

echo "[16/26] Runtime trace smoke"
scripts/smoke_runtime_trace.sh

echo "[17/26] Runtime trace validator smoke"
scripts/smoke_runtime_trace_validator.sh

echo "[18/26] Runtime trace retention smoke"
scripts/smoke_runtime_trace_retention.sh

echo "[19/26] Runtime governance report smoke"
scripts/smoke_runtime_governance_report.sh

echo "[20/26] Runtime policy actions smoke"
scripts/smoke_runtime_policy_actions.sh

echo "[21/26] Runtime policy execution smoke"
scripts/smoke_runtime_policy_execution.sh

echo "[22/26] Runtime remediation orchestration smoke"
scripts/smoke_runtime_remediation_orchestration.sh

echo "[23/26] Runtime autoremediation smoke"
scripts/smoke_runtime_autoremediation.sh

echo "[24/26] Runtime autoremediation cycle smoke"
scripts/smoke_runtime_autoremediation_cycle.sh

echo "[25/26] Runtime autoremediation supervisor smoke"
scripts/smoke_runtime_autoremediation_supervisor.sh

echo "[26/26] Hardening direction judge smoke"
scripts/smoke_hardening_direction_judge.sh

echo "All acceptance checks passed."
