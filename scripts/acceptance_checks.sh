#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

echo "[1/25] Python compile check"
python3 -m py_compile $(rg --files src -g '*.py')

echo "[2/25] Unit tests"
python3 -m unittest discover -s tests -v

echo "[3/25] Regression checks"
scripts/regression_checks.sh

echo "[4/25] Failure matrix"
scripts/failure_matrix.sh

echo "[5/25] No-TUI smoke (fake codex)"
scripts/smoke_no_tui_fake_codex.sh

echo "[6/25] Snapshot schema validation"
scripts/validate_snapshot_output.sh

echo "[7/25] Demo boot flow"
scripts/demo_boot_flow.sh

echo "[8/25] Diagnostics bundle validation"
scripts/validate_diagnostics_bundle.sh

echo "[9/25] Phase2 runner smoke"
scripts/smoke_phase2_runner.sh

echo "[10/25] Phase2 migration/fallback smoke"
scripts/smoke_phase2_migration_fallback.sh

echo "[11/25] Memory recall benchmark smoke"
scripts/smoke_memory_recall_benchmark.sh

echo "[12/25] Memory index rebuild smoke"
scripts/smoke_memory_index_rebuild.sh

echo "[13/25] Memory summarizer quality smoke"
scripts/smoke_memory_summarizer_quality.sh

echo "[14/25] Browser worker boundary smoke"
scripts/smoke_browser_worker_boundary.sh

echo "[15/25] Browser action matrix smoke"
scripts/smoke_browser_action_matrix.sh

echo "[16/25] Runtime trace smoke"
scripts/smoke_runtime_trace.sh

echo "[17/25] Runtime trace validator smoke"
scripts/smoke_runtime_trace_validator.sh

echo "[18/25] Runtime trace retention smoke"
scripts/smoke_runtime_trace_retention.sh

echo "[19/25] Runtime governance report smoke"
scripts/smoke_runtime_governance_report.sh

echo "[20/25] Runtime policy actions smoke"
scripts/smoke_runtime_policy_actions.sh

echo "[21/25] Runtime policy execution smoke"
scripts/smoke_runtime_policy_execution.sh

echo "[22/25] Runtime remediation orchestration smoke"
scripts/smoke_runtime_remediation_orchestration.sh

echo "[23/25] Runtime autoremediation smoke"
scripts/smoke_runtime_autoremediation.sh

echo "[24/25] Runtime autoremediation cycle smoke"
scripts/smoke_runtime_autoremediation_cycle.sh

echo "[25/25] Runtime autoremediation supervisor smoke"
scripts/smoke_runtime_autoremediation_supervisor.sh

echo "All acceptance checks passed."
