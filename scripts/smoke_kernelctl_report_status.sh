#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/root"
WORKSPACE="$TMP_DIR/workspace"
REPORT_DIR="$TMP_DIR/reports"
mkdir -p "$WORKSPACE" "$REPORT_DIR"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
#!/bin/sh
set -eu
out_file=""
prompt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done
if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
  msg='HEALTH_OK'
else
  msg='{"summary":"noop","steps":[]}'
fi
if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE/spec.yaml" <<EOS
name: "kernel-report-status-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOS

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh"

for i in 1 2; do
  python3 - "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh" "$i" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
i = sys.argv[2]
body = p.read_text(encoding='utf-8')
body = body.replace('--kernel-mode', f'--kernel-mode-{i}')
p.write_text(body, encoding='utf-8')
PY

  "$ROOT_DIR/scripts/agentos-kernelctl" repair \
    --workspace "$WORKSPACE" \
    --install-root "$INSTALL_ROOT" \
    --report-dir "$REPORT_DIR" \
    --json >/dev/null
done

OUT_JSON="$TMP_DIR/report-status.json"
"$ROOT_DIR/scripts/agentos-kernelctl" report-status --report-dir "$REPORT_DIR" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get("ok", False):
    raise SystemExit("expected report-status ok=true")
if payload.get("report_count", 0) < 2:
    raise SystemExit("expected at least 2 report files")
if payload.get("valid_json_count", 0) < 2:
    raise SystemExit("expected valid_json_count >= 2")
newest = payload.get("newest_report", {})
if not newest.get("path"):
    raise SystemExit("expected newest_report path")
shadow = payload.get("shadow_summary", {})
if not shadow.get("available", False):
    raise SystemExit("expected shadow_summary.available=true")
coverage = shadow.get("coverage_summary", {}) or {}
if "policy_target_count" not in coverage:
    raise SystemExit("expected shadow_summary.coverage_summary")
alignment = payload.get("alignment_summary", {})
if not alignment.get("available", False):
    raise SystemExit("expected alignment_summary.available=true")
if not isinstance(alignment.get("policy_targets", []), list):
    raise SystemExit("expected alignment_summary.policy_targets list")
if alignment.get("next_policy_target") != "destructive_action_approval":
    raise SystemExit("expected alignment_summary.next_policy_target=destructive_action_approval")
if "destructive_action_approval" not in alignment.get("supported_policy_targets", []):
    raise SystemExit("expected alignment_summary.supported_policy_targets to include destructive_action_approval")
PY

echo "kernelctl report-status smoke: PASS"
