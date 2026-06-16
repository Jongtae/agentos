#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
MAILDIR_REL="mail/example"
MAILDIR="$WORKSPACE/$MAILDIR_REL"
DOC="$ROOT_DIR/docs/architecture/maildir-inbox-intake-proof-boundary.md"
ROADMAP="$ROOT_DIR/docs/next-roadmap.md"
README="$ROOT_DIR/README.md"

mkdir -p "$MAILDIR/cur" "$MAILDIR/new" "$MAILDIR/tmp"

cat >"$MAILDIR/new/1710000000.M1.agentos:2," <<'MSG'
Message-ID: <agentos-maildir-1@example.test>
From: Ops <ops@example.test>
To: AgentOS <agentos@example.test>
Subject: Runtime handoff
Date: Tue, 16 Jun 2026 12:00:00 +0000

Please summarize the runtime handoff and prepare a local draft.
MSG

cat >"$MAILDIR/cur/1710000001.M2.agentos:2,S" <<'MSG'
Message-ID: <agentos-maildir-2@example.test>
References: <agentos-maildir-1@example.test>
In-Reply-To: <agentos-maildir-1@example.test>
From: AgentOS <agentos@example.test>
To: Ops <ops@example.test>
Subject: Re: Runtime handoff
Date: Tue, 16 Jun 2026 12:10:00 +0000

Draft response remains local and does not send external mail.
MSG

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/kernel_inbox_normalized_intake.py" \
  --workspace "$WORKSPACE" \
  --maildir "$MAILDIR_REL" \
  --session-id "session=maildir-smoke;request=req-maildir;approval=read-only" \
  --json >"$TMP_DIR/intake.json"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/kernel_inbox_proof_baseline.py" \
  --workspace "$WORKSPACE" \
  --maildir "$MAILDIR_REL" \
  --session-id "session=maildir-smoke;request=req-maildir;approval=read-only" \
  --json >"$TMP_DIR/proof.json"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/kernel_inbox_workflow.py" \
  --workspace "$WORKSPACE" \
  --maildir "$MAILDIR_REL" \
  --session-id "session=maildir-smoke;request=req-maildir;approval=read-only" \
  --output "$TMP_DIR/workflow.json" \
  --json >/dev/null

python3 - "$TMP_DIR/intake.json" "$TMP_DIR/proof.json" "$TMP_DIR/workflow.json" "$DOC" "$ROADMAP" "$README" <<'PY'
from pathlib import Path
import json
import sys

intake = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
proof = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
workflow = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
doc = Path(sys.argv[4]).read_text(encoding="utf-8")
roadmap = Path(sys.argv[5]).read_text(encoding="utf-8")
readme = Path(sys.argv[6]).read_text(encoding="utf-8")

assert intake["source_kind"] == "maildir", intake
assert intake["path_kind"] == "adapter", intake
assert intake["proof"]["ok"] is True, intake
assert intake["summary"]["message_count"] == 2, intake
assert intake["summary"]["message_intake_count"] == 2, intake
assert intake["summary"]["attachment_count"] == 0, intake
assert intake["summary"]["session_correlated"] is True, intake
assert intake["summary"]["request_correlated"] is False, intake
assert intake["summary"]["approval_correlated"] is False, intake

adapter_report = proof["adapter_report"]
assert adapter_report["summary"]["inbox_adapter_required"] is True, proof
assert adapter_report["summary"]["inbox_execution_ready"] is True, proof
assert adapter_report["summary"]["message_thread_correlated"] is True, proof
assert adapter_report["summary"]["attachment_visibility_ok"] is True, proof
assert adapter_report["proof"]["adapter_kind"] == "maildir", proof

assert workflow["schema_version"] == "agentos-inbox-triage-summary-response-workflow.v1", workflow
assert workflow["workflow_ready"] is True, workflow
assert workflow["path_kind"] == "adapter", workflow
assert workflow["source_kind"] == "maildir", workflow
assert workflow["steps"][0]["id"] == "inbox_intake", workflow
assert workflow["steps"][1]["id"] == "inbox_proof", workflow
assert all(step["ok"] is True for step in workflow["steps"]), workflow
assert workflow["summary"]["inbox_execution_ready"] is True, workflow
assert workflow["summary"]["inbox_adapter_required"] is True, workflow

for term in [
    "Status: Local user-owned proof boundary, not production mailbox sync",
    "source_kind: maildir",
    "path_kind: adapter",
    "inbox_adapter_required: true",
    "proof.adapter_kind: maildir",
    "send messages",
    "delete messages",
    "app ecosystem",
    "replacement",
]:
    assert term in doc, f"missing doc term: {term}"

assert "maildir-inbox-intake-proof-epic" in roadmap
assert "Active task: P2-78" in roadmap
assert "Maildir inbox intake | Active" in readme

for forbidden in [
    "production mailbox sync is complete",
    "external mailbox mutations are supported",
    "full app ecosystem replacement is complete",
]:
    combined = "\n".join([doc, roadmap, readme])
    assert forbidden not in combined, f"forbidden claim found: {forbidden}"
PY

echo "maildir inbox intake proof boundary smoke: PASS"
