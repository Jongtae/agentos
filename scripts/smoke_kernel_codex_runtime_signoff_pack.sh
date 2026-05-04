#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

export PYTHONPATH="$ROOT_DIR/src"
export AGENTOS_STATE_ROOT="$tmpdir/state-root"
export AGENTOS_INSTALL_REQUEST_FILE="$tmpdir/install.env"
export AGENTOS_INSTALLED_BOOT_FILE="$tmpdir/installed.env"
export AGENTOS_SLOT_SWITCH_EVIDENCE_FILE="$tmpdir/slot-switch.env"

slots_dir="$AGENTOS_STATE_ROOT/slots"
mkdir -p "$slots_dir"
cat > "$slots_dir/slot-state.env" <<'EOF'
active_slot=A
inactive_slot=B
rollback_slot=A
next_slot=B
health_state=healthy
EOF
cat > "$slots_dir/next-boot.env" <<'EOF'
bootable_slot=B
staged_from_slot=A
payload_version=v-test
payload_channel=preview
payload_digest=abc123
payload_file=/tmp/payload.json
EOF
cat > "$AGENTOS_SLOT_SWITCH_EVIDENCE_FILE" <<'EOF'
planned_slot=B
observed_slot=B
switch_confirmed=true
evidence_status=ready
transition_kind=booted_planned_slot
EOF

bash "$ROOT_DIR/image-assets/live/bin/agentos-state-root-init" >/dev/null
bash "$ROOT_DIR/image-assets/live/bin/agentos-install-appliance" >/dev/null 2>&1 || test "$?" = 10
bash "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot" >/dev/null

out="$tmpdir/runtime-signoff-pack.json"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_signoff_pack.py" --workspace ./workspaces/default --output "$out"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_signoff_pack.py" --validate "$out" --json >/dev/null

echo "codex runtime signoff pack smoke: PASS"
