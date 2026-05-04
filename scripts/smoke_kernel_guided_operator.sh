#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

mkdir -p "$WORKSPACE/documents" "$WORKSPACE/data"
cat >"$WORKSPACE/spec.yaml" <<'EOF'
name: guided-operator-smoke
tools:
  bash: true
  file: true
  web: true
kernel_engine:
  provider: ollama
  mode: single
  ollama:
    command: missing-ollama-binary
    timeout_sec: 10
    model: smollm2:135m-instruct-q5_K_M
EOF
cat >"$WORKSPACE/documents/agentos-first-run.md" <<'EOF'
# First run
EOF

OUT_JSON="$WORKSPACE/guided-operator.json"
AGENTOS_SESSION_MANAGED=1 AGENTOS_SESSION_ENTRY=local_tty1 \
  "$ROOT_DIR/scripts/agentos-kernelctl" guided-operator --workspace "$WORKSPACE" --json >"$OUT_JSON"

python3 - "$OUT_JSON" "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
workspace = str(Path(sys.argv[2]).resolve())

assert payload["schema_version"] == "agentos-guided-operator-surface.v1"
assert payload["task_vocabulary_version"] == "agentos-task-centric-runtime.v1"
assert payload["state_summary_version"] == "agentos-state-summary.v1"
assert payload["guided_operator_surface_reachable"] is True
assert payload["runtime_entry_mode"] == "tty"
top = payload["top_tasks"]
assert [item["id"] for item in top] == [
    "ask",
    "open_document",
    "fetch_web",
    "review_inbox",
    "export_proof",
    "recover_rejoin",
    "ask_from_telegram",
    "search_and_reply",
    "review_telegram_ingress",
]
assert [item["surface"] for item in top] == [
    "managed_session",
    "document_access",
    "web_access",
    "inbox_workflow",
    "proof_export",
    "recovery_path",
    "telegram_ask",
    "research_workflow",
    "telegram_ingress_status",
]
assert top[0]["command_hint"] == f"agentos-shell --workspace {workspace} --managed-runtime"
assert top[3]["command_hint"] == f"agentos-kernelctl inbox-workflow --workspace {workspace} --json"
assert top[3]["handoff"]["target_surface"] == "inbox_workflow"
assert top[6]["command_hint"] == f"agentos-shell --workspace {workspace} --managed-runtime --telegram-ask"
assert top[7]["command_hint"] == (
    f"agentos-kernelctl research-workflow --workspace {workspace} "
    "--message-text 'search agentos roadmap' --chat-id 1001 --json"
)
assert top[8]["command_hint"] == f"agentos-shell --workspace {workspace} --managed-runtime --telegram-ingress-status"
assert top[0]["handoff"]["target_surface"] == "managed_session"
assert top[0]["handoff"]["managed_runtime_target"] == "codex_cli_managed_session"
assert top[0]["handoff"]["continuity"] == "same_workspace"
assert top[1]["handoff"]["target_surface"] == "document_access"
assert top[2]["handoff"]["target_surface"] == "web_access"
assert top[5]["handoff"]["continuity"] == "rejoin_path"
top_task_success = all(item["status"] == "ready" for item in top)
recovery_visible = bool(payload["recovery_affordance_visible"])
assert top[1]["command_hint"] == f"agentos-kernelctl document-access --workspace {workspace} --path documents/agentos-first-run.md --json"
assert top[2]["command_input"]["required"] == ["url"]
assert top[7]["handoff"]["target_surface"] == "research_workflow"
assert top[7]["handoff"]["launch_mode"] == "tool_call"
assert payload["task_readiness_hint"]["workspace_writable"] is True
assert payload["task_vocabulary"]["baseline_task_kinds"] == ["ask", "document", "web", "inbox", "proof", "recovery"]
assert payload["task_vocabulary"]["telegram_task_kinds"] == ["telegram_ask", "telegram_search_reply", "telegram_ingress_status"]
assert payload["task_vocabulary"]["telegram_task_ids"] == ["ask_from_telegram", "search_and_reply", "review_telegram_ingress"]
summary = payload["state_summary"]
assert payload["recovery_affordance"]["visible"] == recovery_visible
assert payload["recovery_affordance"]["label"] == "AgentOS Recovery"
assert payload["recovery_affordance"]["default_action_label"] == "Return to AgentOS"
assert payload["recovery_affordance"]["default_action_command"] == "agentos-kernelctl runtime-entry --json"
assert payload["recovery_affordance"]["runtime_rejoin_target"] == "codex_cli_managed_session"
assert payload["recovery_affordance"]["rejoin_target"] == "setup_session"
assert "safe shell" in payload["recovery_affordance"]["description"]
assert payload["recovery_affordance"]["entry_points"]
assert payload["recovery_affordance"]["degraded_preview_label"] == "Degraded preview mode"
assert summary["recovery_path_available"] == recovery_visible
assert summary["schema_version"] == "agentos-state-summary.v1"
assert summary["runtime_entry_mode"] == payload["runtime_entry_mode"]
assert summary["workspace_writable"] is True
assert summary["runtime_entry_mode"] == "tty"
assert summary["session_origin"] == "local_managed_tty1"
assert payload["operator_context"]["session_origin"] == "local_managed_tty1"
assert payload["state"] in {"runtime_ready", "runtime_degraded", "workspace_blocked", "provider_unavailable", "proof_export_unavailable"}
assert top_task_success == (payload["state"] in {"runtime_ready", "runtime_degraded"})
recover_task = next(item for item in top if item["id"] == "recover_rejoin")
assert bool(recover_task["ready"]) == recovery_visible
assert payload["state"] != "runtime_ready" or top_task_success
assert summary["provider_model_ready"] is False
assert summary["provider_model_ready"] == payload["top_tasks"][0]["ready"]
assert summary["telegram_ingress_ready"] is True
assert summary["telegram_polling_enabled"] is False
assert summary["telegram_bot_token_configured"] is False
PY
