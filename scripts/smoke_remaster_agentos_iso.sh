#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_BIN="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN" "$TMP_DIR/out"

cat > "$FAKE_BIN/bsdtar" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [ "${args[$i]}" = "-C" ]; then
    target="${args[$((i+1))]}"
  fi
  if [ "${args[$i]}" = "-xf" ]; then
    archive="${args[$((i+1))]}"
  fi
done
if [[ "${archive:-}" == *.tar.gz ]]; then
  exec /usr/bin/tar "$@"
fi
mkdir -p "$target/casper"
printf 'stub squashfs
' > "$target/casper/filesystem.squashfs"
EOS
chmod +x "$FAKE_BIN/bsdtar"

cat > "$FAKE_BIN/unsquashfs" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
out=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [ "${args[$i]}" = "-d" ]; then
    out="${args[$((i+1))]}"
  fi
done
mkdir -p "$out/usr/local/bin" "$out/etc/xdg/autostart"
EOS
chmod +x "$FAKE_BIN/unsquashfs"

cat > "$FAKE_BIN/mksquashfs" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
log_path="$(cd "$(dirname "$0")/.." && pwd)/mksquashfs-args.log"
printf '%s\n' "$*" >> "$log_path"
printf 'stub repacked squashfs
' > "$2"
EOS
chmod +x "$FAKE_BIN/mksquashfs"

cat > "$FAKE_BIN/xorriso" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
if printf '%s\n' "$*" | grep -q -- "-report_system_area cmd"; then
  cat <<'REPORT'
-volid 'AgentOS Smoke'
-boot_image any cat_path='/boot.catalog'
-boot_image grub bin_path='/boot/grub/i386-pc/eltorito.img'
-boot_image any boot_info_table=on
-boot_image grub grub2_boot_info=on
REPORT
  exit 0
fi
out=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [ "${args[$i]}" = "-outdev" ]; then
    out="${args[$((i+1))]}"
  fi
done
printf 'stub remastered iso
' > "$out"
EOS
chmod +x "$FAKE_BIN/xorriso"

BASE="$TMP_DIR/base.iso"
printf 'stub base iso
' > "$BASE"
PREP_OUT="$($ROOT_DIR/scripts/prepare_iso_assets.sh --version vsmoke-remaster --output-dir "$TMP_DIR/assets")"
BUNDLE="$(printf '%s
' "$PREP_OUT" | sed -n 's/^bundle:[[:space:]]*//p' | tail -n1)"
MANIFEST="$(printf '%s
' "$PREP_OUT" | sed -n 's/^manifest:[[:space:]]*//p' | tail -n1)"
OUT_ISO="$TMP_DIR/out/agentos-remastered.iso"
OUT_MANIFEST="$TMP_DIR/out/remaster-manifest.txt"

MKSQUASHFS_ARGS_LOG="$TMP_DIR/mksquashfs-args.log"
PATH="$FAKE_BIN:$PATH" AGENTOS_REMASTER_STUB_MODE=1 "$ROOT_DIR/scripts/remaster_agentos_iso.sh"   --base-image "$BASE"   --asset-bundle "$BUNDLE"   --asset-manifest "$MANIFEST"   --output-iso "$OUT_ISO"   --work-dir "$TMP_DIR/work"   --version vsmoke-remaster   --build-manifest "$OUT_MANIFEST" >/dev/null

[ -f "$OUT_ISO" ]
[ -f "$OUT_MANIFEST" ]
rg -q '^build_mode=remaster_pipeline$' "$OUT_MANIFEST"
rg -q '^welcome_shell_injected=true$' "$OUT_MANIFEST"
rg -q '^recovery_shell_injected=true$' "$OUT_MANIFEST"
rg -q '^boot_assets_injected=true$' "$OUT_MANIFEST"
rg -q '^boot_patch_report=' "$OUT_MANIFEST"
rg -q '^boot_target_activation_report=' "$OUT_MANIFEST"
rg -q '^boot_target_activated=true$' "$OUT_MANIFEST"
rg -q '^boot_flow_proof=' "$OUT_MANIFEST"
rg -q '^boot_flow_proof_included=true$' "$OUT_MANIFEST"
rg -q '^vm_first_screen_evidence=' "$OUT_MANIFEST"
rg -q '^vm_first_screen_evidence_included=true$' "$OUT_MANIFEST"
rg -q '^installer_hidden_default_path=true$' "$OUT_MANIFEST"
rg -q '^patched_squashfs_paths=' "$OUT_MANIFEST"
rg -q '^active_live_source_report=' "$OUT_MANIFEST"
rg -q -- '-all-root' "$MKSQUASHFS_ARGS_LOG"

BOOT_TARGET_REPORT_PATH="$(sed -n 's/^boot_target_activation_report=//p' "$OUT_MANIFEST" | tail -n1)"
[ -f "$BOOT_TARGET_REPORT_PATH" ]
python3 "$ROOT_DIR/scripts/verify_boot_target_activation.py" --validate "$BOOT_TARGET_REPORT_PATH" --json >/dev/null

BOOT_FLOW_PROOF_PATH="$(sed -n 's/^boot_flow_proof=//p' "$OUT_MANIFEST" | tail -n1)"
[ -f "$BOOT_FLOW_PROOF_PATH" ]
python3 "$ROOT_DIR/scripts/verify_remastered_boot_flow.py" --validate "$BOOT_FLOW_PROOF_PATH" --json >/dev/null

VM_FIRST_SCREEN_PATH="$(sed -n 's/^vm_first_screen_evidence=//p' "$OUT_MANIFEST" | tail -n1)"
[ -f "$VM_FIRST_SCREEN_PATH" ]
python3 "$ROOT_DIR/scripts/verify_vm_first_screen_evidence.py" --validate "$VM_FIRST_SCREEN_PATH" --json >/dev/null

echo "remaster agentos iso smoke: PASS"
