#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

VALID="$TMP_DIR/valid-observed-proof.json"
INVALID="$TMP_DIR/invalid-observed-proof.json"

cat >"$VALID" <<'JSON'
{
  "schema_version": "agentos-observed-proof-intake.v1",
  "proof_surface": "gmail_readonly_live",
  "claim": "AgentOS can read and summarize a tester-approved Gmail query without mutation.",
  "status": "observed",
  "observed_by": "tester",
  "observed_at_utc": "2026-06-16T08:30:00Z",
  "evidence": [
    {
      "kind": "issue_comment",
      "path_or_url": "https://github.com/Jongtae/agentos/issues/135#issuecomment-example",
      "redaction": "tokens and private mailbox content removed"
    }
  ],
  "remaining_non_claims": [
    "send/delete/archive are not proven"
  ],
  "blockers": []
}
JSON

cat >"$INVALID" <<'JSON'
{
  "schema_version": "agentos-observed-proof-intake.v1",
  "proof_surface": "gmail_readonly_live",
  "claim": "This record accidentally includes a refresh_token and no blocker.",
  "status": "blocked",
  "observed_by": "tester",
  "observed_at_utc": "2026-06-16T08:30:00Z",
  "evidence": [],
  "remaining_non_claims": [],
  "blockers": []
}
JSON

python3 "$ROOT_DIR/scripts/observed_proof_intake_validate.py" "$VALID" --json | python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["ok"], payload'
if python3 "$ROOT_DIR/scripts/observed_proof_intake_validate.py" "$INVALID" --json >/tmp/agentos-invalid-proof.out 2>/tmp/agentos-invalid-proof.err; then
  echo "expected invalid proof record to fail" >&2
  exit 1
fi
python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/agentos-invalid-proof.out").read_text(encoding="utf-8"))
assert not payload["ok"], payload
assert any("refresh_token" in error for error in payload["errors"]), payload
assert any("blocker" in error for error in payload["errors"]), payload
PY

grep -q "observed-proof-intake-schema.json" "$ROOT_DIR/docs/architecture/observed-proof-intake-boundary.md"
grep -q "scripts/observed_proof_intake_validate.py" "$ROOT_DIR/TASKS.md"
grep -q "scripts/smoke_observed_proof_intake_validator.sh" "$ROOT_DIR/scripts/phase2_golden_demo_runner.py"

echo "observed proof intake validator smoke: PASS"
