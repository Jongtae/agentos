#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

export PYTHONPATH="$ROOT_DIR/src"
export AGENTOS_INSTALLED_BOOT_FILE="$tmpdir/installed.env"
export AGENTOS_SLOT_SWITCH_EVIDENCE_FILE="$tmpdir/slot-switch.env"

cat > "$AGENTOS_SLOT_SWITCH_EVIDENCE_FILE" <<'EOF'
planned_slot=B
observed_slot=B
switch_confirmed=true
evidence_status=ready
transition_kind=booted_planned_slot
EOF

bash "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot" >/dev/null

out="$tmpdir/installed-boot-to-codex.json"
python3 "$ROOT_DIR/scripts/kernel_installed_boot_to_codex.py" --workspace ./workspaces/default --output "$out"
python3 "$ROOT_DIR/scripts/kernel_installed_boot_to_codex.py" --validate "$out" --json >/dev/null

echo "installed boot to codex smoke: PASS"
