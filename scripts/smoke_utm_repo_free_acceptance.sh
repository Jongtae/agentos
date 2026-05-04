#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

RELEASE_DIR="$TMP_DIR/release"
mkdir -p "$RELEASE_DIR"
ISO_PATH="$RELEASE_DIR/agentos-v-smoke-amd64.iso"
MANIFEST_PATH="$TMP_DIR/manifest-v-smoke.txt"
METADATA_PATH="$RELEASE_DIR/agentos-release-metadata.json"

printf 'stub iso\n' > "$ISO_PATH"
cat > "$MANIFEST_PATH" <<'EOF'
boot_target_activated=true
vm_first_screen_evidence_included=true
boot_flow_proof_included=true
EOF

python3 - <<PY
import json
from pathlib import Path

payload = {
    "agentos_version": "v-smoke",
    "output_path": str(Path("$ISO_PATH").resolve()),
    "build_manifest_path": str(Path("$MANIFEST_PATH").resolve()),
    "boot_target_activated": True,
}
Path("$METADATA_PATH").write_text(json.dumps(payload), encoding="utf-8")
PY

OUT="$(python3 "$ROOT_DIR/scripts/utm_repo_free_acceptance.py" --release-metadata "$METADATA_PATH" --dry-run --json)"
printf '%s' "$OUT" | python3 -c \
  "import json,sys; p=json.load(sys.stdin); \
  assert p['schema_version']=='agentos-utm-repo-free-acceptance.v1'; \
  assert p['iso']['version']=='v-smoke'; \
  assert p['summary']['guided_operator_surface_reachable'] is False; \
  assert p['summary']['workspace_writable'] is False; \
  assert p['summary']['recovery_degraded_acceptance_ready'] is False; \
  assert p['summary']['provider_ready'] is False; \
  assert p['summary']['first_prompt_success'] is False; \
  assert p['summary']['managed_reentry_ready'] is False; \
  assert p['summary']['usable_runtime_entry'] is False; \
  assert p['summary']['top_task_success'] is False; \
  assert p['summary'].get('research_workflow_ready', False) is False; \
  assert p['summary'].get('inbox_workflow_ready', False) is False; \
  assert p['summary'].get('telegram_thread_continuity_ready', False) is False; \
  assert p['summary'].get('inbox_reply_workflow_ready', False) is False; \
  assert p['summary'].get('research_brief_ready', False) is False; \
  assert p['summary'].get('brief_artifact_exported', False) is False; \
  assert p['summary']['pass'] is False; \
  planned=[str(command) for command in p['planned_commands']]; \
  assert any('document-access' in command for command in planned); \
  assert any('web-access' in command for command in planned); \
  assert any('guided-operator' in command for command in planned); \
  assert any('engine-availability' in command for command in planned); \
  assert any('inbox-proof' in command for command in planned); \
  assert any('vm-e2e-proof' in command for command in planned); \
  assert any('research-workflow' in command for command in planned); \
  assert any('inbox-workflow' in command for command in planned); \
  assert any('runtime-entry' in command for command in planned) or any('guided-operator' in command for command in planned); \
  assert 'research_workflow' in p['steps']; \
  assert 'inbox_workflow' in p['steps']; \
  assert 'telegram_thread_status' in p['steps']; \
  assert 'inbox_reply_workflow' in p['steps']; \
  assert 'research_brief' in p['steps']"

echo "utm repo-free acceptance smoke: PASS"
