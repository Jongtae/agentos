#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)/.."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
ARTIFACTS="$WORKSPACE/artifacts"
DOCS_ROOT="$TMP_DIR/docs-root"
mkdir -p "$ARTIFACTS" "$DOCS_ROOT/docs/runbooks"

cat >"$DOCS_ROOT/README.md" <<'EOF'
brew install --cask utm
AgentOS Setup -> AgentOS Managed Session -> ai>
AgentOS Recovery
AgentOS Recovery -> Return to AgentOS -> ai>
EOF

cat >"$DOCS_ROOT/docs/runbooks/vm-install-quickstart.md" <<'EOF'
Continue to AgentOS
Install AgentOS
make this appliance persistent
AgentOS Recovery
AgentOS Recovery -> Return to AgentOS -> ai>
AgentOS Setup -> AgentOS Managed Session -> ai>
EOF

cat >"$DOCS_ROOT/docs/runbooks/vm-install-guide.md" <<'EOF'
Continue to AgentOS
Install AgentOS
make this appliance persistent
AgentOS Recovery
AgentOS Recovery -> Return to AgentOS -> ai>
AgentOS Setup -> AgentOS Managed Session -> ai>
EOF

cat >"$DOCS_ROOT/docs/runbooks/agentos-operations-runbook.md" <<'EOF'
Continue to AgentOS
make this appliance persistent
AgentOS Recovery
AgentOS Recovery -> Return to AgentOS -> ai>
boot AgentOS -> tiny setup -> ai>
EOF

cat >"$DOCS_ROOT/docs/runbooks/distribution-packaging-runbook.md" <<'EOF'
AgentOS Setup -> AgentOS Managed Session -> ai>
AgentOS Recovery
advanced/fallback reference
EOF

OUT_JSON="$TMP_DIR/direct-boot-messaging-consistency.json"
python3 "$ROOT_DIR/scripts/kernel_direct_boot_messaging_consistency.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS/public-preview" \
  --docs-root "$DOCS_ROOT" \
  --snapshot-label smoke \
  --output "$OUT_JSON" \
  --json

python3 "$ROOT_DIR/scripts/kernel_direct_boot_messaging_consistency.py" --validate "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload["schema_version"] == "agentos-direct-boot-messaging-consistency.v1"
assert payload["summary"]["overall_state"] == "ready"
assert payload["summary"]["boot_messaging"] == "ready"
assert payload["summary"]["setup_messaging"] == "ready"
assert payload["summary"]["install_later_messaging"] == "ready"
assert payload["summary"]["recovery_messaging"] == "ready"
assert payload["canonical_language"]["recovery_summary_path"] == ["AgentOS Recovery", "Return to AgentOS", "ai>"]
assert pathlib.Path(payload["artifacts"]["direct_boot_messaging_consistency_manifest_json"]).exists()
print("kernel direct-boot messaging consistency smoke: PASS")
PY
