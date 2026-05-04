#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/ws"
HOME_DIR="$TMP_DIR/home"
OUT_JSON="$TMP_DIR/llm-setup.json"

HOME="$HOME_DIR" "$ROOT_DIR/scripts/agentos-kernelctl" llm-setup \
  --workspace "$WORKSPACE" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["schema_version"] == "agentos-llm-setup.v1", payload
assert payload["provider"] == "ollama", payload
assert payload["selected_model"] == "smollm2:135m-instruct-q5_K_M", payload
assert payload["codex_model"] == "gpt-4o-mini", payload
PY

HOME="$HOME_DIR" "$ROOT_DIR/scripts/agentos-kernelctl" llm-setup \
  --workspace "$WORKSPACE" \
  --set-provider codex \
  --openai-api-key test-openai-key-placeholder \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" "$HOME_DIR/.config/agentos/env" "$WORKSPACE/spec.yaml" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
env_text = open(sys.argv[2], encoding="utf-8").read()
spec_text = open(sys.argv[3], encoding="utf-8").read()
assert payload["provider"] == "codex", payload
assert payload["selected_model"] == "gpt-4o-mini", payload
assert "test-openai-key-placeholder" not in json.dumps(payload), payload
assert "OPENAI_API_KEY=test-openai-key-placeholder" in env_text
assert "provider: codex" in spec_text
assert "model: gpt-4o-mini" in spec_text
PY

echo "smoke_kernel_llm_setup: PASS"
