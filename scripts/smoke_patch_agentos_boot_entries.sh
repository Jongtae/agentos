#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ISO_ROOT="$TMP_DIR/iso-root"
mkdir -p "$ISO_ROOT/boot/grub"
cat > "$ISO_ROOT/boot/grub/grub.cfg" <<'EOF'
menuentry "Try or Install Ubuntu" {
  linux /casper/vmlinuz quiet splash
}
menuentry "Install Ubuntu" {
  linux /casper/vmlinuz only-ubiquity
}
menuentry "Ubuntu (safe graphics)" {
  linux /casper/vmlinuz nomodeset
}
grub_platform
if [ "$grub_platform" = "efi" ]; then
menuentry "UEFI Firmware Settings" { fwsetup }
fi
EOF

REPORT="$TMP_DIR/patch-report.json"
python3 "$ROOT_DIR/scripts/patch_agentos_boot_entries.py" --iso-root "$ISO_ROOT" --output "$REPORT" >/dev/null

rg -q 'Continue to AgentOS' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'AgentOS Recovery' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'console=tty0' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'console=ttyAMA0,115200n8' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'maxcpus=1' "$ISO_ROOT/boot/grub/grub.cfg"
if rg -q 'console=tty1|systemd.journald.forward_to_console=1|--- console=tty0' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: visible tty must stay reserved for the operator prompt" >&2
  exit 1
fi
rg -q 'systemd.unit=multi-user.target' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'plymouth.enable=0' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'systemd.mask=snapd.apparmor.service' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'systemd.mask=casper-md5check.service' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'systemd.mask=serial-getty@ttyS0.service' "$ISO_ROOT/boot/grub/grub.cfg"
if rg -q 'systemd.mask=serial-getty@ttyAMA0.service|systemd.mask=serial-getty@ttyS0.service ---' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: ttyAMA0 must remain available and trailing console separators must be removed" >&2
  exit 1
fi
rg -q '^terminal_input console$' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q '^terminal_output console$' "$ISO_ROOT/boot/grub/grub.cfg"
if rg -q '^serial --unit=|terminal_input console serial|terminal_output console serial|terminal_input serial console|terminal_output serial console' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: GRUB must remain display-console first; serial terminal wiring breaks visible UTM boot" >&2
  exit 1
fi
rg -q 'set timeout_style=hidden' "$ISO_ROOT/boot/grub/grub.cfg"
rg -q 'set timeout=1' "$ISO_ROOT/boot/grub/grub.cfg"
if rg -q '\bquiet\b|\bsplash\b' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: desktop boot args remain in headless default path" >&2
  exit 1
fi
if rg -q '^grub_platform$' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: standalone grub_platform command remains" >&2
  exit 1
fi
if rg -q 'Install AgentOS' "$ISO_ROOT/boot/grub/grub.cfg"; then
  echo "patch agentos boot entries smoke: unexpected top-level Install AgentOS peer" >&2
  exit 1
fi

python3 - "$REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["installer_hidden_default_path"] is True
assert payload["continue_present"] is True
assert payload["install_present"] is False
assert payload["install_path_available"] is True
assert payload["recovery_present"] is True
assert payload["default_boot_target_label"] == "Continue to AgentOS"
assert payload["default_boot_target_entry_index"] == 0
assert payload["grub_default_target_configured"] is True
assert payload["default_boot_target_configured"] is True
assert payload["forbidden_labels_remaining"] == []
print("patch agentos boot entries smoke: PASS")
PY
