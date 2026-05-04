#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
OUT_DIR="$TMP_DIR/out"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-bridge-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
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
  workspace_root: "./sandbox"
network:
  web_allowlist:
    - "openai.com"
    - "github.com"
  browser_allowlist:
    - "openai.com"
    - "github.com"
EOF

mkdir -p "$WORKSPACE/sandbox"

OUT_JSON1="$TMP_DIR/bridge1.json"
scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" --output-dir "$OUT_DIR" --json > "$OUT_JSON1"

python3 - "$OUT_JSON1" "$OUT_DIR" "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("ok", False):
    raise SystemExit("policy-bridge expected ok=true")
if payload.get("mechanism") != "apparmor":
    raise SystemExit("mechanism should be apparmor")
if payload.get("reload_recommended", True):
    raise SystemExit("first render should not force reload recommendation")

template_path = Path(payload["template_path"])
profile_path = Path(payload["profile_path"])
if not template_path.exists() or not profile_path.exists():
    raise SystemExit("expected template/profile artifacts")

profile_text = profile_path.read_text(encoding="utf-8")
expected_root = str((Path(sys.argv[3]) / "sandbox").resolve())
if expected_root not in profile_text:
    raise SystemExit("rendered profile missing resolved workspace root")
if "browser-allowlist-domain: openai.com" not in profile_text:
    raise SystemExit("rendered profile missing browser allowlist domain marker")
if "web-allowlist-domain: github.com" not in profile_text:
    raise SystemExit("rendered profile missing web allowlist domain marker")
if "destructive-action-approval-required: true" not in profile_text:
    raise SystemExit("rendered profile missing destructive action approval signal")

if payload.get("destructive_action_approval_required") is not True:
    raise SystemExit("bridge report should include destructive action approval signal")
if sorted(payload.get("network_allowlist", [])) != ["github.com", "openai.com"]:
    raise SystemExit("bridge report should include merged network_allowlist")
if payload.get("lifecycle", {}).get("last_action") != "render":
    raise SystemExit("expected lifecycle.last_action=render")
if payload.get("lifecycle_summary", {}).get("bridge_state") != "rendered":
    raise SystemExit("expected lifecycle_summary.bridge_state=rendered")
PY

python3 - "$WORKSPACE/spec.yaml" <<'PY'
import sys
from pathlib import Path
import yaml

spec_path = Path(sys.argv[1])
spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
spec["runtime"]["workspace_root"] = "./sandbox2"
spec_path.write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
PY
mkdir -p "$WORKSPACE/sandbox2"

OUT_JSON2="$TMP_DIR/bridge2.json"
scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" --output-dir "$OUT_DIR" --json > "$OUT_JSON2"

python3 - "$OUT_JSON2" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("workspace_root_changed", False):
    raise SystemExit("workspace root change should be detected")
if not payload.get("reload_recommended", False):
    raise SystemExit("reload should be recommended when workspace root changes")
if payload.get("lifecycle", {}).get("drift_state") != "drifted":
    raise SystemExit("expected lifecycle.drift_state=drifted")
PY

OUT_JSON3="$TMP_DIR/bridge3.json"
scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" --output-dir "$OUT_DIR" --disable --parser-cmd missing-parser --json > "$OUT_JSON3"

python3 - "$OUT_JSON3" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("disable_attempted") is not True:
    raise SystemExit("expected disable_attempted=true")
if payload.get("lifecycle", {}).get("last_action") != "disable":
    raise SystemExit("expected lifecycle.last_action=disable")
if payload.get("lifecycle", {}).get("disable_state") != "failed":
    raise SystemExit("expected lifecycle.disable_state=failed")
PY

echo "kernel policy bridge smoke: PASS"
