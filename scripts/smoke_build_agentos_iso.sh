#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! command -v rg >/dev/null 2>&1; then
  rg() {
    grep -aE "$@"
  }
fi

OUT_DIR="$TMP_DIR/out"
FAKE_BIN_DIR="$TMP_DIR/bin"
BASE_IMAGE="$TMP_DIR/base.iso"
VERSION="vsmoke-iso-$(date +%s)-$$"
MANIFEST_PATH="$ROOT_DIR/build-output/manifest-${VERSION}.txt"
ASSET_BUNDLE_PATH="$ROOT_DIR/build-output/iso-assets/$VERSION/agentos-iso-assets.tar.gz"
ASSET_MANIFEST_PATH="$ROOT_DIR/build-output/iso-assets/$VERSION/asset-manifest.txt"

mkdir -p "$FAKE_BIN_DIR" "$OUT_DIR"

cat > "$FAKE_BIN_DIR/bsdtar" <<'EOS'
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
printf 'stub squashfs\n' > "$target/casper/filesystem.squashfs"
mkdir -p "$target/boot/grub"
cat > "$target/boot/grub/grub.cfg" <<'EOF'
menuentry "Try or Install Ubuntu" {
  linux /casper/vmlinuz quiet splash
}
menuentry "Install Ubuntu" {
  linux /casper/vmlinuz only-ubiquity
}
menuentry "Ubuntu (safe graphics)" {
  linux /casper/vmlinuz nomodeset
}
EOF
EOS
chmod +x "$FAKE_BIN_DIR/bsdtar"

cat > "$FAKE_BIN_DIR/unsquashfs" <<'EOS'
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
chmod +x "$FAKE_BIN_DIR/unsquashfs"

cat > "$FAKE_BIN_DIR/mksquashfs" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
log_path="$(cd "$(dirname "$0")/.." && pwd)/mksquashfs-args.log"
printf '%s\n' "$*" >> "$log_path"
printf 'stub repacked squashfs\n' > "$2"
EOS
chmod +x "$FAKE_BIN_DIR/mksquashfs"

cat > "$FAKE_BIN_DIR/xorriso" <<'EOS'
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
printf 'stub remastered iso\n' > "$out"
EOS
chmod +x "$FAKE_BIN_DIR/xorriso"

STAGE_BUNDLED_OLLAMA_STUB="$TMP_DIR/stage-bundled-ollama.py"
cat > "$STAGE_BUNDLED_OLLAMA_STUB" <<'EOS'
#!/usr/bin/env python3
from pathlib import Path
import argparse, json, os
parser = argparse.ArgumentParser()
parser.add_argument("--live-root", required=True)
parser.add_argument("--runtime-root", required=True)
parser.add_argument("--cache-dir", required=True)
parser.add_argument("--arch", default="amd64")
parser.add_argument("--output", required=True)
args = parser.parse_args()
live_root = Path(args.live_root)
runtime_root = Path(args.runtime_root)
(live_root / "usr/local/bin").mkdir(parents=True, exist_ok=True)
(live_root / "usr/local").mkdir(parents=True, exist_ok=True)
(live_root / "usr/local/ollama").write_text("stub ollama", encoding="utf-8")
link = live_root / "usr/local/bin/ollama"
if link.exists() or link.is_symlink():
    link.unlink()
os.symlink("../ollama", link)
manifest = live_root / "var/lib/agentos/models/manifests/registry.ollama.ai/library/smollm2/135m-instruct-q5_K_M"
manifest.parent.mkdir(parents=True, exist_ok=True)
manifest.write_text('{"config":{"digest":"sha256:abc"},"layers":[]}', encoding="utf-8")
blobs = live_root / "var/lib/agentos/models/blobs"
blobs.mkdir(parents=True, exist_ok=True)
(blobs / "sha256-abc").write_text("blob", encoding="utf-8")
runtime_asset = runtime_root / "assets/ollama/usr-local-root"
runtime_asset.mkdir(parents=True, exist_ok=True)
(runtime_asset / "ollama").write_text("stub ollama", encoding="utf-8")
runtime_manifest = runtime_root / "assets/ollama/models/manifests/registry.ollama.ai/library/smollm2/135m-instruct-q5_K_M"
runtime_manifest.parent.mkdir(parents=True, exist_ok=True)
runtime_manifest.write_text('{"config":{"digest":"sha256:abc"},"layers":[]}', encoding="utf-8")
runtime_blobs = runtime_root / "assets/ollama/models/blobs"
runtime_blobs.mkdir(parents=True, exist_ok=True)
(runtime_blobs / "sha256-abc").write_text("blob", encoding="utf-8")
(live_root / "etc/systemd/system/multi-user.target.wants").mkdir(parents=True, exist_ok=True)
(live_root / "etc/systemd/system/agentos-ollama.service").write_text("[Service]\nExecStart=/usr/local/bin/agentos-ollama-serve\n", encoding="utf-8")
service_link = live_root / "etc/systemd/system/multi-user.target.wants/agentos-ollama.service"
if service_link.exists() or service_link.is_symlink():
    service_link.unlink()
os.symlink("../agentos-ollama.service", service_link)
Path(args.output).write_text(json.dumps({"arch": args.arch, "bundled_local_provider_staged": True, "bundled_local_model_staged": True, "bundled_local_service_staged": True, "bundled_local_firstrun_service_staged": True}), encoding="utf-8")
EOS
chmod +x "$STAGE_BUNDLED_OLLAMA_STUB"

VERIFY_BUNDLED_OLLAMA_STUB="$TMP_DIR/verify-bundled-ollama.py"
cat > "$VERIFY_BUNDLED_OLLAMA_STUB" <<'EOS'
#!/usr/bin/env python3
from pathlib import Path
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument("--live-root", required=True)
parser.add_argument("--runtime-root", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({"bundled_local_provider_staged": True, "bundled_local_model_staged": True, "bundled_local_service_staged": True, "bundled_local_firstrun_service_staged": True}), encoding="utf-8")
EOS
chmod +x "$VERIFY_BUNDLED_OLLAMA_STUB"

STAGE_GUEST_AGENT_STUB="$TMP_DIR/stage-guest-agent.py"
cat > "$STAGE_GUEST_AGENT_STUB" <<'EOS'
#!/usr/bin/env python3
from pathlib import Path
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument("--live-root", required=True)
parser.add_argument("--cache-dir", required=True)
parser.add_argument("--arch", default="amd64")
parser.add_argument("--output", required=True)
args = parser.parse_args()
live_root = Path(args.live_root)
(live_root / "usr/sbin").mkdir(parents=True, exist_ok=True)
(live_root / "usr/sbin/qemu-ga").write_text("stub qemu guest agent", encoding="utf-8")
(live_root / "etc/systemd/system/multi-user.target.wants").mkdir(parents=True, exist_ok=True)
(live_root / "etc/systemd/system/qemu-guest-agent.service").write_text("[Service]\nExecStart=/usr/sbin/qemu-ga\n", encoding="utf-8")
Path(args.output).write_text(json.dumps({"staged": True}), encoding="utf-8")
EOS
chmod +x "$STAGE_GUEST_AGENT_STUB"

VERIFY_GUEST_AGENT_STUB="$TMP_DIR/verify-guest-agent.py"
cat > "$VERIFY_GUEST_AGENT_STUB" <<'EOS'
#!/usr/bin/env python3
from pathlib import Path
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument("--live-root", required=True)
parser.add_argument("--apt-policy", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    "live_guest_agent_bootstrap_staged": True,
    "live_guest_agent_prestaged": True,
    "live_guest_agent_reachability_path": "prestaged",
}), encoding="utf-8")
EOS
chmod +x "$VERIFY_GUEST_AGENT_STUB"

FAKE_OPERATOR_TUI="$TMP_DIR/agentos-operator-tui"
cat > "$FAKE_OPERATOR_TUI" <<'EOS'
#!/usr/bin/env sh
printf 'fake agentos operator tui\n'
EOS
chmod 0755 "$FAKE_OPERATOR_TUI"
export AGENTOS_OPERATOR_TUI_BIN="$FAKE_OPERATOR_TUI"

export AGENTOS_STAGE_GUEST_AGENT_CMD="$STAGE_GUEST_AGENT_STUB"
export AGENTOS_GUEST_AGENT_STAGING_CMD="$VERIFY_GUEST_AGENT_STUB"

printf 'agentos-smoke-base-image' > "$BASE_IMAGE"

if [ -f "$MANIFEST_PATH" ]; then
  rm -f "$MANIFEST_PATH"
fi
rm -f "$ASSET_BUNDLE_PATH" "$ASSET_MANIFEST_PATH"

BUILD_OUT="$TMP_DIR/build.out"
MKSQUASHFS_ARGS_LOG="$TMP_DIR/mksquashfs-args.log"
AGENTOS_STAGE_BUNDLED_OLLAMA_CMD="$STAGE_BUNDLED_OLLAMA_STUB" \
AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD="$VERIFY_BUNDLED_OLLAMA_STUB" \
PATH="$FAKE_BIN_DIR:$PATH" "$ROOT_DIR/scripts/build_agentos_iso.sh" \
  --version "$VERSION" \
  --output-dir "$OUT_DIR" \
  --base-image "$BASE_IMAGE" > "$BUILD_OUT"

ISO_PATH="$OUT_DIR/agentos-${VERSION}-amd64.iso"
SHA_PATH="$OUT_DIR/SHA256SUMS"
RELEASE_METADATA_PATH="$OUT_DIR/agentos-release-metadata.json"

if [ ! -f "$ISO_PATH" ]; then
  echo "[build-iso-smoke] missing ISO output"
  exit 1
fi

if ! rg -q 'stub remastered iso' "$ISO_PATH"; then
  echo "[build-iso-smoke] expected remastered ISO marker"
  exit 1
fi

if ! rg -q -- '-all-root' "$MKSQUASHFS_ARGS_LOG"; then
  echo "[build-iso-smoke] expected remaster squashfs to be rebuilt with -all-root"
  cat "$MKSQUASHFS_ARGS_LOG"
  exit 1
fi

if [ ! -f "$SHA_PATH" ]; then
  echo "[build-iso-smoke] missing SHA256SUMS"
  exit 1
fi

if [ ! -f "$RELEASE_METADATA_PATH" ]; then
  echo "[build-iso-smoke] missing release metadata"
  exit 1
fi

if ! rg -q "Artifact type: iso" "$BUILD_OUT"; then
  echo "[build-iso-smoke] build summary missing artifact type"
  exit 1
fi

if ! rg -q "Release metadata: ${RELEASE_METADATA_PATH}" "$BUILD_OUT"; then
  echo "[build-iso-smoke] build summary missing release metadata path"
  exit 1
fi

if ! rg -q "Build mode: remaster_pipeline" "$BUILD_OUT"; then
  echo "[build-iso-smoke] build summary missing remaster pipeline mode"
  exit 1
fi

if ! rg -q "GRUB theme contract: agentos_minimal_appliance_grub.v1" "$BUILD_OUT"; then
  echo "[build-iso-smoke] build summary missing grub theme contract"
  exit 1
fi

if ! rg -q "Splash theme contract: agentos_minimal_appliance_splash.v1" "$BUILD_OUT"; then
  echo "[build-iso-smoke] build summary missing splash theme contract"
  exit 1
fi

if ! rg -q "agentos-${VERSION}-amd64.iso" "$SHA_PATH"; then
  echo "[build-iso-smoke] SHA256SUMS missing ISO entry"
  exit 1
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "[build-iso-smoke] missing build manifest"
  exit 1
fi

if ! rg -q "build_mode=remaster_pipeline" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing remaster build mode"
  exit 1
fi

if ! rg -q "welcome_shell_injected=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing welcome shell injection marker"
  exit 1
fi

if ! rg -q "installer_hidden_default_path=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing installer-hidden marker"
  exit 1
fi

if ! rg -q "boot_flow_proof_included=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing boot flow proof marker"
  exit 1
fi

if ! rg -q "boot_target_activated=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing boot target activation marker"
  exit 1
fi

if ! rg -q "boot_target_activation_report=" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing boot target activation report"
  exit 1
fi

if ! rg -q "patched_squashfs_paths=" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing patched squashfs list"
  exit 1
fi

if ! rg -q "active_live_source_report=" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing active live source report"
  exit 1
fi

if ! rg -q "vm_first_screen_evidence_included=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing VM first-screen evidence marker"
  exit 1
fi

if ! rg -q "base_image=${BASE_IMAGE}" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing base image path"
  exit 1
fi

if [ ! -f "$ASSET_BUNDLE_PATH" ]; then
  echo "[build-iso-smoke] missing iso asset bundle"
  exit 1
fi

if [ ! -f "$ASSET_MANIFEST_PATH" ]; then
  echo "[build-iso-smoke] missing iso asset manifest"
  exit 1
fi

if ! rg -q "asset_bundle=${ASSET_BUNDLE_PATH}" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] build manifest missing asset bundle entry"
  exit 1
fi

if ! rg -q "asset_manifest=${ASSET_MANIFEST_PATH}" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] build manifest missing asset manifest entry"
  exit 1
fi

if ! rg -q "bundled_local_provider_staged=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing bundled local provider marker"
  exit 1
fi

if ! rg -q "bundled_local_model_staged=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing bundled local model marker"
  exit 1
fi

if ! rg -q "bundled_local_service_staged=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing bundled local service marker"
  exit 1
fi
if ! rg -q "bundled_local_firstrun_service_staged=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing bundled local firstrun service marker"
  exit 1
fi

if ! rg -q "headless_live_session_bootstrap_service_staged=true" "$MANIFEST_PATH"; then
  echo "[build-iso-smoke] manifest missing headless live bootstrap service marker"
  exit 1
fi

python3 - "$RELEASE_METADATA_PATH" "$VERSION" "$ISO_PATH" "$SHA_PATH" "$MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("artifact_type") != "iso":
    raise SystemExit("release metadata artifact_type mismatch")
if payload.get("agentos_version") != sys.argv[2]:
    raise SystemExit("release metadata version mismatch")
if payload.get("distribution_contract") != "agentos_managed_session":
    raise SystemExit("release metadata distribution contract mismatch")
if payload.get("primary_entry_contract") != "agentos_setup_to_ai_shell":
    raise SystemExit("release metadata entry contract mismatch")
if payload.get("output_path") != sys.argv[3]:
    raise SystemExit("release metadata output path mismatch")
if payload.get("sha256sums_path") != sys.argv[4]:
    raise SystemExit("release metadata sha path mismatch")
if payload.get("build_manifest_path") != sys.argv[5]:
    raise SystemExit("release metadata manifest path mismatch")
if payload.get("grub_theme_contract") != "agentos_minimal_appliance_grub.v1":
    raise SystemExit("release metadata grub theme contract mismatch")
if payload.get("splash_theme_contract") != "agentos_minimal_appliance_splash.v1":
    raise SystemExit("release metadata splash theme contract mismatch")
if payload.get("boot_flow_proof_contract") != "agentos-remastered-boot-flow-proof.v1":
    raise SystemExit("release metadata boot flow proof contract mismatch")
if payload.get("boot_flow_proof_included") is not True:
    raise SystemExit("release metadata boot flow proof included mismatch")
if payload.get("default_boot_target_contract") != "agentos_continue_boot_target.v1":
    raise SystemExit("release metadata default boot target contract mismatch")
if payload.get("default_boot_target_label") != "Continue to AgentOS":
    raise SystemExit("release metadata default boot target label mismatch")
if payload.get("boot_target_activated") is not True:
    raise SystemExit("release metadata boot target activation mismatch")
if payload.get("vm_first_screen_evidence_contract") != "agentos_vm_first_screen_evidence.v1":
    raise SystemExit("release metadata VM first-screen evidence contract mismatch")
if payload.get("vm_first_screen_evidence_included") is not True:
    raise SystemExit("release metadata VM first-screen evidence included mismatch")
if payload.get("iso_default_boot_path") != "continue_to_agentos_default_path":
    raise SystemExit("release metadata default boot path mismatch")
if payload.get("installer_hidden_default_path") is not True:
    raise SystemExit("release metadata installer-hidden flag mismatch")
if payload.get("agentos_welcome_assets_staged") is not True:
    raise SystemExit("release metadata welcome assets staged mismatch")
if payload.get("agentos_welcome_runtime_observed") is not False:
    raise SystemExit("release metadata welcome runtime observed should stay false at build time")
if payload.get("agentos_welcome_owns_first_screen") is not False:
    raise SystemExit("release metadata must not overclaim first-screen ownership at build time")
if payload.get("bundled_local_provider_staged") is not True:
    raise SystemExit("release metadata bundled local provider staged mismatch")
if payload.get("bundled_local_model_staged") is not True:
    raise SystemExit("release metadata bundled local model staged mismatch")
if payload.get("bundled_local_service_staged") is not True:
    raise SystemExit("release metadata bundled local service staged mismatch")
if payload.get("bundled_local_firstrun_service_staged") is not True:
    raise SystemExit("release metadata bundled local firstrun service staged mismatch")
PY

python3 "$ROOT_DIR/scripts/release_identity_manifest.py" validate --input "$RELEASE_METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_release_identity_contract.py" --metadata "$RELEASE_METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_install_validation_contract.py" --metadata "$RELEASE_METADATA_PATH" --json >/dev/null

FETCH_STUB="$TMP_DIR/fetch-base-image.sh"
cat > "$FETCH_STUB" <<EOS
#!/usr/bin/env sh
printf '%s\n' "$BASE_IMAGE"
EOS
chmod +x "$FETCH_STUB"

DOWNLOAD_OUT="$TMP_DIR/download.out"
DOWNLOAD_DIR="$TMP_DIR/out-download"
mkdir -p "$DOWNLOAD_DIR"
AGENTOS_STAGE_BUNDLED_OLLAMA_CMD="$STAGE_BUNDLED_OLLAMA_STUB" \
AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD="$VERIFY_BUNDLED_OLLAMA_STUB" \
AGENTOS_FETCH_BASE_IMAGE_CMD="$FETCH_STUB" PATH="$FAKE_BIN_DIR:$PATH" "$ROOT_DIR/scripts/build_agentos_iso.sh" \
  --version "${VERSION}-download" \
  --output-dir "$DOWNLOAD_DIR" \
  --download-base-image > "$DOWNLOAD_OUT"

DOWNLOAD_ISO_PATH="$DOWNLOAD_DIR/agentos-${VERSION}-download-amd64.iso"
if [ ! -f "$DOWNLOAD_ISO_PATH" ]; then
  echo "[build-iso-smoke] missing ISO output for download flow"
  exit 1
fi

if ! rg -q 'stub remastered iso' "$DOWNLOAD_ISO_PATH"; then
  echo "[build-iso-smoke] download flow expected remastered ISO marker"
  exit 1
fi

if ! rg -q "Build mode: remaster_pipeline" "$DOWNLOAD_OUT"; then
  echo "[build-iso-smoke] download flow summary missing remaster pipeline mode"
  exit 1
fi

if ! rg -q "Base image: ${BASE_IMAGE}" "$DOWNLOAD_OUT"; then
  echo "[build-iso-smoke] download flow summary missing resolved base image"
  exit 1
fi

SERVER_COMPAT_BASE="$TMP_DIR/ubuntu-24.04.4-live-server-amd64.iso"
cp "$BASE_IMAGE" "$SERVER_COMPAT_BASE"
SERVER_ERR="$TMP_DIR/server.err"
if AGENTOS_STAGE_BUNDLED_OLLAMA_CMD="$STAGE_BUNDLED_OLLAMA_STUB" \
  AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD="$VERIFY_BUNDLED_OLLAMA_STUB" \
  PATH="$FAKE_BIN_DIR:$PATH" "$ROOT_DIR/scripts/build_agentos_iso.sh" \
  --version "${VERSION}-server-denied" \
  --output-dir "$TMP_DIR/out-server-denied" \
  --base-image "$SERVER_COMPAT_BASE" > /dev/null 2>"$SERVER_ERR"; then
  echo "[build-iso-smoke] expected live-server base image to be rejected by default"
  exit 1
fi

if ! rg -q "Refusing Ubuntu live-server base image" "$SERVER_ERR"; then
  echo "[build-iso-smoke] expected live-server rejection message"
  exit 1
fi

AGENTOS_STAGE_BUNDLED_OLLAMA_CMD="$STAGE_BUNDLED_OLLAMA_STUB" \
AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD="$VERIFY_BUNDLED_OLLAMA_STUB" \
PATH="$FAKE_BIN_DIR:$PATH" "$ROOT_DIR/scripts/build_agentos_iso.sh" \
  --version "${VERSION}-server-headless" \
  --output-dir "$TMP_DIR/out-server-headless" \
  --base-image "$SERVER_COMPAT_BASE" \
  --headless-acceptance-base > "$TMP_DIR/server-headless.out"

SERVER_HEADLESS_MANIFEST="$ROOT_DIR/build-output/manifest-${VERSION}-server-headless.txt"
SERVER_HEADLESS_METADATA="$TMP_DIR/out-server-headless/agentos-release-metadata.json"
if ! rg -q "base_image_type=headless-live-server-iso" "$SERVER_HEADLESS_MANIFEST"; then
  echo "[build-iso-smoke] headless live-server build manifest missing headless base image type"
  exit 1
fi

if ! rg -q "Base image type: headless-live-server-iso" "$TMP_DIR/server-headless.out"; then
  echo "[build-iso-smoke] headless live-server build summary missing headless base image type"
  exit 1
fi

python3 "$ROOT_DIR/scripts/verify_release_identity_contract.py" \
  --metadata "$SERVER_HEADLESS_METADATA" \
  --json >/dev/null

AGENTOS_STAGE_BUNDLED_OLLAMA_CMD="$STAGE_BUNDLED_OLLAMA_STUB" \
AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD="$VERIFY_BUNDLED_OLLAMA_STUB" \
PATH="$FAKE_BIN_DIR:$PATH" "$ROOT_DIR/scripts/build_agentos_iso.sh" \
  --version "${VERSION}-server-compat" \
  --output-dir "$TMP_DIR/out-server-compat" \
  --base-image "$SERVER_COMPAT_BASE" \
  --allow-server-installer-compat > /dev/null

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-shell$'; then
  echo "[build-iso-smoke] asset bundle missing agentos-shell"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-operator-tui$'; then
  echo "[build-iso-smoke] asset bundle missing agentos-operator-tui"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/runtime/agentos/scripts/kernel_llm_setup.py$'; then
  echo "[build-iso-smoke] runtime bundle missing kernel_llm_setup.py"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-firstrun$'; then
  echo "[build-iso-smoke] asset bundle missing agentos-firstrun"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-terminal-qr$'; then
  echo "[build-iso-smoke] asset bundle missing terminal QR renderer"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-telegram-live-loop-daemon$'; then
  echo "[build-iso-smoke] asset bundle missing Telegram live loop daemon"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-telegram-webhook-daemon$'; then
  echo "[build-iso-smoke] asset bundle missing Telegram webhook daemon"
  exit 1
fi

python3 - "$ROOT_DIR/scripts/agentos-terminal-qr" <<'PY'
import pathlib
import sys

namespace = {}
exec(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"), namespace)
for url in ("https://t.me/BotFather", "https://web.telegram.org/", "https://desktop.telegram.org/"):
    rows = namespace["STATIC_QR"][url]
    terminal_columns = (len(rows) + 8) * 2
    if terminal_columns > 80:
        raise SystemExit(f"terminal QR for {url} is {terminal_columns} columns; expected <= 80")
dynamic_rows = namespace["_encode_version3_l"]("http://198.51.100.12:8787/setup")
if len(dynamic_rows) != 29 or len(dynamic_rows[0]) != 29:
    raise SystemExit("dynamic setup-page QR must render as QR version 3")
if (len(dynamic_rows) + 8) * 2 > 80:
    raise SystemExit("dynamic setup-page QR must fit 80-column TTY")
PY

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/bin/agentos-live-firstrun-service$'; then
  echo "[build-iso-smoke] asset bundle missing live firstrun wrapper"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/live/bin/agentos-live-session-bootstrap$'; then
  echo "[build-iso-smoke] asset bundle missing live session bootstrap"
  exit 1
fi

if ! tar -xOf "$ASSET_BUNDLE_PATH" iso-assets/postinstall/apt-packages.policy | rg -q '^qemu-guest-agent\|'; then
  echo "[build-iso-smoke] apt policy missing qemu-guest-agent"
  exit 1
fi

if ! tar -xOf "$ASSET_BUNDLE_PATH" iso-assets/postinstall/apt-packages.policy | rg -q '^qrencode\|'; then
  echo "[build-iso-smoke] apt policy missing qrencode"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/systemd/agentos-kernel.service$'; then
  echo "[build-iso-smoke] asset bundle missing kernel service"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/systemd/agentos-telegram-live-loop.service$'; then
  echo "[build-iso-smoke] asset bundle missing Telegram live loop service"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/systemd/agentos-telegram-webhookd.service$'; then
  echo "[build-iso-smoke] asset bundle missing Telegram webhook service"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/boot/grub/theme.txt$'; then
  echo "[build-iso-smoke] asset bundle missing grub theme"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/boot/plymouth/agentos-minimal.plymouth$'; then
  echo "[build-iso-smoke] asset bundle missing plymouth theme"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/runtime/agentos/src/main.py$'; then
  echo "[build-iso-smoke] asset bundle missing runtime main entrypoint"
  exit 1
fi

if ! tar -tzf "$ASSET_BUNDLE_PATH" | rg -q '^iso-assets/runtime/agentos/scripts/install_kernel_boot_integration.sh$'; then
  echo "[build-iso-smoke] asset bundle missing runtime install integration script"
  exit 1
fi

rm -f "$MANIFEST_PATH" "$ASSET_BUNDLE_PATH" "$ASSET_MANIFEST_PATH"

echo "build agentos iso smoke: PASS"
