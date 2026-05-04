#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 - <<'PY' "$TMP_DIR"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
(root / 'checklist.json').write_text(json.dumps({'schema_version':'agentos-remastered-vm-boot-checklist.v1','summary':{'ok':True}}) + '\n', encoding='utf-8')
(root / 'first.json').write_text(json.dumps({'schema_version':'agentos-vm-first-screen-evidence.v1','evidence_status':'ready','expected_first_path':'Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>'}) + '\n', encoding='utf-8')
(root / 'target.json').write_text(json.dumps({'schema_version':'agentos-boot-target-activation.v1','default_boot_target_label':'Continue to AgentOS','activation_status':'ready'}) + '\n', encoding='utf-8')
PY

OUT="$TMP_DIR/proof-pack.json"
python3 "$ROOT_DIR/scripts/kernel_welcome_first_vm_proof_pack.py" \
  --report-dir "$TMP_DIR/reports" \
  --checklist-manifest "$TMP_DIR/checklist.json" \
  --vm-first-screen-evidence "$TMP_DIR/first.json" \
  --boot-target-activation "$TMP_DIR/target.json" \
  --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_welcome_first_vm_proof_pack.py" --validate "$OUT"
python3 - <<'PY' "$OUT"
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert payload['schema_version'] == 'agentos-welcome-first-vm-proof-pack.v1'
assert payload['summary']['ok'] is True
assert payload['summary']['welcome_first_proven'] is True
print('kernel welcome-first VM proof pack smoke: PASS')
PY
