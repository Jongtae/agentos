#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PATCH_BOOT_ENTRIES_CMD="${AGENTOS_PATCH_BOOT_ENTRIES_CMD:-$ROOT_DIR/scripts/patch_agentos_boot_entries.py}"
BOOT_FLOW_PROOF_CMD="${AGENTOS_BOOT_FLOW_PROOF_CMD:-$ROOT_DIR/scripts/verify_remastered_boot_flow.py}"
BOOT_TARGET_ACTIVATION_CMD="${AGENTOS_BOOT_TARGET_ACTIVATION_CMD:-$ROOT_DIR/scripts/verify_boot_target_activation.py}"
VM_FIRST_SCREEN_EVIDENCE_CMD="${AGENTOS_VM_FIRST_SCREEN_EVIDENCE_CMD:-$ROOT_DIR/scripts/verify_vm_first_screen_evidence.py}"
DISABLE_UBUNTU_INSTALLER_CMD="${AGENTOS_DISABLE_UBUNTU_INSTALLER_CMD:-$ROOT_DIR/scripts/disable_ubuntu_installer_autostart.py}"
GUEST_AGENT_STAGING_CMD="${AGENTOS_GUEST_AGENT_STAGING_CMD:-$ROOT_DIR/scripts/verify_live_guest_agent_staging.py}"
STAGE_GUEST_AGENT_CMD="${AGENTOS_STAGE_GUEST_AGENT_CMD:-$ROOT_DIR/scripts/stage_live_guest_agent.py}"
STAGE_BUNDLED_OLLAMA_CMD="${AGENTOS_STAGE_BUNDLED_OLLAMA_CMD:-$ROOT_DIR/scripts/stage_bundled_ollama.py}"
VERIFY_BUNDLED_OLLAMA_CMD="${AGENTOS_VERIFY_BUNDLED_OLLAMA_CMD:-$ROOT_DIR/scripts/verify_bundled_ollama_staging.py}"
BASE_IMAGE=""
ASSET_BUNDLE=""
ASSET_MANIFEST=""
OUTPUT_ISO=""
WORK_DIR=""
VERSION=""
ARCH="amd64"
BUILD_MANIFEST=""

usage() {
  cat <<USAGE
Usage:
  scripts/remaster_agentos_iso.sh     --base-image <path>     --asset-bundle <path>     --asset-manifest <path>     --output-iso <path>     --work-dir <path>     --version <v>     [--arch amd64|arm64]     --build-manifest <path>
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base-image) shift; BASE_IMAGE="${1:-}" ;;
    --asset-bundle) shift; ASSET_BUNDLE="${1:-}" ;;
    --asset-manifest) shift; ASSET_MANIFEST="${1:-}" ;;
    --output-iso) shift; OUTPUT_ISO="${1:-}" ;;
    --work-dir) shift; WORK_DIR="${1:-}" ;;
    --version) shift; VERSION="${1:-}" ;;
    --arch) shift; ARCH="${1:-}" ;;
    --build-manifest) shift; BUILD_MANIFEST="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift || true
done

case "$ARCH" in
  amd64|arm64) ;;
  *) echo "Invalid --arch '$ARCH'. Supported: amd64, arm64." >&2; exit 2 ;;
esac

for value in "$BASE_IMAGE" "$ASSET_BUNDLE" "$ASSET_MANIFEST" "$OUTPUT_ISO" "$WORK_DIR" "$VERSION" "$BUILD_MANIFEST"; do
  if [ -z "$value" ]; then
    echo "missing required remaster argument" >&2
    usage >&2
    exit 2
  fi
done

purge_dir() {
  local target="$1"
  if [ ! -e "$target" ]; then
    return 0
  fi
  chflags -R nouchg "$target" 2>/dev/null || true
  chmod -R u+w "$target" 2>/dev/null || true
  find "$target" -exec chmod u+rwX {} + 2>/dev/null || true
  find "$target" -type l -exec chmod -h u+w {} + 2>/dev/null || true
  find "$target" -type d -exec chmod u+w {} + 2>/dev/null || true
  rm -rf "$target" 2>/dev/null || true
  if [ -e "$target" ]; then
    python3 - "$target" <<'PY'
import shutil
import sys
from pathlib import Path

target = Path(sys.argv[1])
if target.exists():
    shutil.rmtree(target, ignore_errors=True)
PY
  fi
  if [ -e "$target" ]; then
    find "$target" -mindepth 1 -depth -exec rm -rf {} + 2>/dev/null || true
    rmdir "$target" 2>/dev/null || true
  fi
  if [ -e "$target" ]; then
    echo "[remaster_agentos_iso] unable to purge work directory: $target" >&2
    exit 1
  fi
}

for path in "$BASE_IMAGE" "$ASSET_BUNDLE" "$ASSET_MANIFEST"; do
  if [ ! -f "$path" ]; then
    echo "required remaster input not found: $path" >&2
    exit 1
  fi
done

for tool in bsdtar unsquashfs mksquashfs xorriso; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "required remaster tool missing: $tool" >&2
    exit 1
  fi
done

xorriso_boot_replay_args() {
  local base_image="$1"
  local line
  local -a args=()
  local report
  if ! report="$(xorriso -indev "$base_image" -report_system_area cmd 2>/dev/null)"; then
    printf '%s\0' "-boot_image" "any" "replay"
    return 0
  fi
  while IFS= read -r line; do
    case "$line" in
      -volid*|-boot_image*|-append_partition*)
        eval "args+=($line)"
        ;;
    esac
  done <<< "$report"
  if [ "${#args[@]}" -eq 0 ]; then
    args=(-boot_image any replay)
  fi
  printf '%s\0' "${args[@]}"
}

if [ -d "$WORK_DIR" ]; then
  purge_dir "$WORK_DIR"
fi
mkdir -p "$WORK_DIR"
ISO_ROOT="$WORK_DIR/iso-root"
LIVE_ROOT="$WORK_DIR/live-root"
ASSET_ROOT="$WORK_DIR/assets"
mkdir -p "$ISO_ROOT" "$LIVE_ROOT" "$ASSET_ROOT"

if [ "${AGENTOS_REMASTER_STUB_MODE:-0}" = "1" ]; then
  mkdir -p "$ISO_ROOT/casper" "$ISO_ROOT/boot/grub" "$LIVE_ROOT/usr/local/bin" "$LIVE_ROOT/etc/xdg/autostart"
  printf 'stub squashfs
' > "$ISO_ROOT/casper/filesystem.squashfs"
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
EOF
else
  bsdtar -C "$ISO_ROOT" -xf "$BASE_IMAGE"
  chmod -R u+w "$ISO_ROOT" 2>/dev/null || true
  find "$ISO_ROOT" -type d -exec chmod u+w {} + 2>/dev/null || true
fi

tar -C "$ASSET_ROOT" -xzf "$ASSET_BUNDLE"

SQUASHFS_RELPATHS=()
while IFS= read -r squashfs_relpath; do
  if [ -n "$squashfs_relpath" ]; then
    SQUASHFS_RELPATHS+=("$squashfs_relpath")
  fi
done < <(python3 "$ROOT_DIR/scripts/live_source_paths.py" --iso-root "$ISO_ROOT")
if [ "${#SQUASHFS_RELPATHS[@]}" -eq 0 ]; then
  echo "unable to locate live filesystem squashfs in remaster tree" >&2
  exit 1
fi

mkdir -p "$ISO_ROOT/agentos/boot-assets"
mkdir -p \
  "$ISO_ROOT/agentos/postinstall" \
  "$ISO_ROOT/agentos/runtime"
cp -R "$ASSET_ROOT/iso-assets/boot/." "$ISO_ROOT/agentos/boot-assets/"
cp "$ASSET_MANIFEST" "$ISO_ROOT/agentos/asset-manifest.txt"
cp -R "$ASSET_ROOT/iso-assets/runtime/agentos" "$ISO_ROOT/agentos/runtime/"
cp -R "$ASSET_ROOT/iso-assets/postinstall/." "$ISO_ROOT/agentos/postinstall/"

prepare_live_root() {
  local live_root="$1"
  local report_dir="$2"
  local installer_report="$report_dir/ubuntu-installer-disable-report.json"
  local guest_agent_stage_report="$report_dir/live-guest-agent-stage-report.json"
  local guest_agent_staging_report="$report_dir/live-guest-agent-staging-report.json"
  local bundled_ollama_stage_report="$report_dir/bundled-ollama-stage-report.json"
  local bundled_ollama_verify_report="$report_dir/bundled-ollama-verify-report.json"

  mkdir -p \
    "$live_root/usr/local/bin" \
    "$live_root/etc/xdg/autostart" \
    "$live_root/etc/systemd/system/agentos-firstrun.service.d" \
    "$live_root/etc/systemd/system/multi-user.target.wants" \
    "$live_root/usr/local/share/agentos/boot-assets" \
    "$live_root/usr/lib/agentos" \
    "$live_root/var/lib/agentos/live-bootstrap" \
    "$live_root/var/lib/agentos/workspaces/default/documents" \
    "$report_dir"

  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-welcome-shell" "$live_root/usr/local/bin/agentos-welcome-shell"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-live-session-bootstrap" "$live_root/usr/local/bin/agentos-live-session-bootstrap"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-recovery-shell" "$live_root/usr/local/bin/agentos-recovery-shell"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-handoff" "$live_root/usr/local/bin/agentos-handoff"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-install-appliance" "$live_root/usr/local/bin/agentos-install-appliance"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-state-root-init" "$live_root/usr/local/bin/agentos-state-root-init"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-installed-boot" "$live_root/usr/local/bin/agentos-installed-boot"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-slot-switch-evidence" "$live_root/usr/local/bin/agentos-slot-switch-evidence"
  install -m 0755 "$ASSET_ROOT/iso-assets/live/bin/agentos-slot-metadata-init" "$live_root/usr/local/bin/agentos-slot-metadata-init"
  install -m 0755 "$ROOT_DIR/scripts/agentos-acceptance-proof-collector" "$live_root/usr/local/bin/agentos-acceptance-proof-collector"
  install -m 0755 "$ROOT_DIR/scripts/agentos-operator-console" "$live_root/usr/local/bin/agentos-operator-console"
  install -m 0755 "$ROOT_DIR/scripts/agentos-telegram-live-loop-daemon" "$live_root/usr/local/bin/agentos-telegram-live-loop-daemon"
  install -m 0755 "$ROOT_DIR/scripts/agentos-telegram-webhook-daemon" "$live_root/usr/local/bin/agentos-telegram-webhook-daemon"
  install -m 0755 "$ASSET_ROOT/iso-assets/bin/agentos-operator-tui" "$live_root/usr/local/bin/agentos-operator-tui"
  install -m 0755 "$ASSET_ROOT/iso-assets/bin/agentos-terminal-qr" "$live_root/usr/local/bin/agentos-terminal-qr"
  cat > "$live_root/usr/local/bin/agentos-ollama-serve" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME="${HOME:-/var/lib/agentos}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/var/lib/agentos/models}"
exec /usr/local/bin/ollama serve
EOF
  chmod 0755 "$live_root/usr/local/bin/agentos-ollama-serve"
  cat > "$live_root/usr/local/bin/agentos-engine-availability-refresh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
RUNTIME_ROOT="${AGENTOS_RUNTIME_ROOT:-/usr/lib/agentos}"
WORKSPACE="${AGENTOS_DEFAULT_WORKSPACE:-/var/lib/agentos/workspaces/default}"
SEED_WORKSPACE="${AGENTOS_SEED_WORKSPACE:-/var/lib/agentos/workspaces/default}"
STATUS_DIR="${AGENTOS_LIVE_BOOTSTRAP_STATE_DIR:-/var/lib/agentos/live-bootstrap}"
LOG_PATH="$STATUS_DIR/engine-availability-refresh.log"
mkdir -p "$STATUS_DIR"
mkdir -p "$WORKSPACE" "$WORKSPACE/documents" "$WORKSPACE/artifacts" "$WORKSPACE/data"
if [ -f "$SEED_WORKSPACE/spec.yaml" ] && [ ! -f "$WORKSPACE/spec.yaml" ]; then
  cp "$SEED_WORKSPACE/spec.yaml" "$WORKSPACE/spec.yaml"
fi
if [ -f "$SEED_WORKSPACE/documents/agentos-first-run.md" ] && [ ! -f "$WORKSPACE/documents/agentos-first-run.md" ]; then
  cp "$SEED_WORKSPACE/documents/agentos-first-run.md" "$WORKSPACE/documents/agentos-first-run.md"
fi
export PYTHONPATH="$RUNTIME_ROOT/src"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/var/lib/agentos/models}"
attempt=0
while [ "$attempt" -lt 18 ]; do
  if python3 "$RUNTIME_ROOT/scripts/kernel_engine_availability.py" --workspace "$WORKSPACE" --json --no-bootstrap >>"$LOG_PATH" 2>&1; then
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 10
done
exit 1
EOF
  chmod 0755 "$live_root/usr/local/bin/agentos-engine-availability-refresh"
  install -m 0644 "$ASSET_ROOT/iso-assets/live/session/agentos-welcome.desktop" "$live_root/etc/xdg/autostart/agentos-welcome.desktop"
  cp -R "$ASSET_ROOT/iso-assets/boot/." "$live_root/usr/local/share/agentos/boot-assets/"
  cp -R "$ASSET_ROOT/iso-assets/runtime/agentos/." "$live_root/usr/lib/agentos/"
  install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-operator-tty1.service" "$live_root/etc/systemd/system/agentos-operator-tty1.service"
  install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-telegram-live-loop.service" "$live_root/etc/systemd/system/agentos-telegram-live-loop.service"
  install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-telegram-webhookd.service" "$live_root/etc/systemd/system/agentos-telegram-webhookd.service"
  cat > "$live_root/etc/systemd/system/agentos-live-session-bootstrap.service" <<'EOF'
[Unit]
Description=AgentOS Headless Live Session Bootstrap
After=multi-user.target

[Service]
Type=simple
Environment=AGENTOS_WELCOME_ACTION=continue
Environment=AGENTOS_LIVE_BOOTSTRAP_STATE_DIR=/var/lib/agentos/live-bootstrap
Environment=AGENTOS_KERNELCTL_BIN=/usr/local/bin/agentos-kernelctl
ExecStart=/usr/local/bin/agentos-live-session-bootstrap
Restart=on-failure
RestartSec=10
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
  ln -sf ../agentos-live-session-bootstrap.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-live-session-bootstrap.service"
  ln -sf ../agentos-operator-tty1.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-operator-tty1.service"
  ln -sf ../agentos-telegram-live-loop.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-telegram-live-loop.service"
  ln -sf ../agentos-telegram-webhookd.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-telegram-webhookd.service"
  mkdir -p \
    "$live_root/etc/systemd/system/getty.target.wants" \
    "$live_root/etc/systemd/system/serial-getty@ttyAMA0.service.d"
  ln -sf /lib/systemd/system/serial-getty@.service "$live_root/etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service"
  cat > "$live_root/etc/systemd/system/serial-getty@ttyAMA0.service.d/10-agentos-autologin.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --noissue --autologin ubuntu --noclear --keep-baud 115200,38400,9600 %I $TERM
Type=idle
EOF
  ln -sf /dev/null "$live_root/etc/systemd/system/serial-getty@ttyS0.service"
  cat > "$live_root/etc/systemd/system/agentos-ollama.service" <<'EOF'
[Unit]
Description=AgentOS Bundled Ollama Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=HOME=/var/lib/agentos
Environment=OLLAMA_MODELS=/var/lib/agentos/models
ExecStart=/usr/local/bin/agentos-ollama-serve
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
  ln -sf ../agentos-ollama.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-ollama.service"
  cat > "$live_root/etc/systemd/system/agentos-acceptance-proof.service" <<'EOF'
[Unit]
Description=AgentOS Headless Acceptance Proof Collector
After=agentos-ollama.service network-online.target
Wants=agentos-ollama.service

[Service]
Type=simple
Environment=AGENTOS_RUNTIME_ROOT=/usr/lib/agentos
Environment=AGENTOS_DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws
Environment=AGENTOS_SEED_WORKSPACE=/var/lib/agentos/workspaces/default
Environment=AGENTOS_ACCEPTANCE_USER=ubuntu
Environment=AGENTOS_SERIAL_DIAG_TTY=/dev/ttyAMA0
Environment=OLLAMA_MODELS=/var/lib/agentos/models
ExecStart=/usr/local/bin/agentos-acceptance-proof-collector
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
  ln -sf ../agentos-acceptance-proof.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-acceptance-proof.service"
  cat > "$live_root/etc/systemd/system/agentos-engine-availability.service" <<'EOF'
[Unit]
Description=AgentOS Kernel Engine Availability Refresh
After=agentos-ollama.service network-online.target
Wants=agentos-ollama.service

[Service]
Type=oneshot
Environment=HOME=/var/lib/agentos
Environment=AGENTOS_RUNTIME_ROOT=/usr/lib/agentos
Environment=AGENTOS_DEFAULT_WORKSPACE=/var/lib/agentos/workspaces/default
Environment=AGENTOS_SEED_WORKSPACE=/var/lib/agentos/workspaces/default
Environment=OLLAMA_MODELS=/var/lib/agentos/models
ExecStart=/usr/local/bin/agentos-engine-availability-refresh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

  cat > "$live_root/var/lib/agentos/workspaces/default/spec.yaml" <<'EOF'
name: "agentos-default"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "ollama"
  mode: "single"
  codex:
    command: "codex"
    timeout_sec: 90
    model: "gpt-4o-mini"
    auto_bootstrap: true
  ollama:
    command: "ollama"
    timeout_sec: 90
    model: "smollm2:135m-instruct-q5_K_M"
    auto_bootstrap: true
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 12
  max_message_window: 20
  workspace_root: "./"
EOF
  cat > "$live_root/var/lib/agentos/workspaces/default/documents/agentos-first-run.md" <<'EOF'
# AgentOS First Run

This workspace document proves repo-free native document access on a freshly booted AgentOS image.

- runtime: Codex-managed AgentOS session
- capability goal: document + web + summary
- proof path: installed `agentos-kernelctl` surfaces only
EOF

  # Keep the image-baked reference workspace outside /home. Ubuntu live creates
  # the ephemeral ubuntu user/home during boot; pre-baking /home/ubuntu into the
  # squashfs can preserve host uid/gid metadata and break sudo/user ownership.
  # agentos-firstrun seeds the interactive workspace after the live user exists.
  chmod -R a+rwX "$live_root/var/lib/agentos/live-bootstrap"
  chmod -R a+rwX "$live_root/var/lib/agentos/workspaces/default"

  AGENTOS_INSTALL_ROOT="$live_root" \
  AGENTOS_ENABLE_SYSTEMD=0 \
  AGENTOS_BROKER_BYPASS=1 \
  AGENTOS_USER=ubuntu \
  AGENTOS_USER_HOME=/home/ubuntu \
  DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws \
  AGENTOS_DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws \
  AGENTOS_INSTALLED_DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws \
  AGENTOS_INSTALLED_SEED_WORKSPACE=/var/lib/agentos/workspaces/default \
  AGENTOS_RUNTIME_ROOT_EMBED=/usr/lib/agentos \
  "$live_root/usr/lib/agentos/scripts/install_kernel_boot_integration.sh" >/dev/null

  cat > "$live_root/etc/systemd/system/agentos-firstrun.service.d/10-live-window10.conf" <<'EOF'
[Unit]
After=agentos-ollama.service network-online.target
Wants=agentos-ollama.service

[Service]
User=root
WorkingDirectory=/usr/lib/agentos
Environment=AGENTOS_FIRSTRUN_CHOICE=local
Environment=AGENTOS_LIVE_USER=ubuntu
Environment=AGENTOS_LIVE_USER_HOME=/home/ubuntu
Environment=AGENTOS_DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws
Environment=DEFAULT_WORKSPACE=/home/ubuntu/agentos-ws
Environment=HOME=/home/ubuntu
Environment=AGENTOS_LIVE_BOOTSTRAP_STATE_DIR=/var/lib/agentos/live-bootstrap
Environment=AGENTOS_HANDOFF_PATH=/tmp/agentos-handoff.env
Environment=AGENTOS_KERNELCTL_BIN=/usr/local/bin/agentos-kernelctl
Environment=AGENTOS_LIVE_FIRSTRUN_MODE=prep-only
StandardInput=null
StandardOutput=journal
StandardError=journal
ExecStart=
ExecStart=/usr/local/bin/agentos-live-firstrun-service
EOF
  ln -sf ../agentos-firstrun.service "$live_root/etc/systemd/system/multi-user.target.wants/agentos-firstrun.service"

  python3 "$DISABLE_UBUNTU_INSTALLER_CMD" \
    --live-root "$live_root" \
    --output "$installer_report" >/dev/null

  python3 "$STAGE_GUEST_AGENT_CMD" \
    --live-root "$live_root" \
    --cache-dir "$WORK_DIR/package-cache" \
    --arch "$ARCH" \
    --output "$guest_agent_stage_report" >/dev/null

  python3 "$GUEST_AGENT_STAGING_CMD" \
    --live-root "$live_root" \
    --apt-policy "$ASSET_ROOT/iso-assets/postinstall/apt-packages.policy" \
    --output "$guest_agent_staging_report" >/dev/null

  python3 "$STAGE_BUNDLED_OLLAMA_CMD" \
    --live-root "$live_root" \
    --runtime-root "$live_root/usr/lib/agentos" \
    --cache-dir "$WORK_DIR/package-cache/ollama" \
    --arch "$ARCH" \
    --output "$bundled_ollama_stage_report" >/dev/null

  python3 "$VERIFY_BUNDLED_OLLAMA_CMD" \
    --live-root "$live_root" \
    --runtime-root "$live_root/usr/lib/agentos" \
    --output "$bundled_ollama_verify_report" >/dev/null

  chmod -R a+rwX "$live_root/var/lib/agentos/models"
}

PRIMARY_LIVE_ROOT=""
PRIMARY_INSTALLER_REPORT=""
PRIMARY_GUEST_AGENT_STAGE_REPORT=""
PRIMARY_GUEST_AGENT_STAGING_REPORT=""
PRIMARY_BUNDLED_OLLAMA_STAGE_REPORT=""
PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT=""
PATCHED_SQUASHFS_PATHS=()
REPORT_DIR_ROOT="$WORK_DIR/live-source-reports"
mkdir -p "$REPORT_DIR_ROOT" "$ISO_ROOT/agentos"

source_index=0
for squashfs_relpath in "${SQUASHFS_RELPATHS[@]}"; do
  SQUASHFS_PATH="$ISO_ROOT/$squashfs_relpath"
  if [ ! -f "$SQUASHFS_PATH" ]; then
    continue
  fi
  LIVE_ROOT="$WORK_DIR/live-root-$source_index"
  REPORT_DIR="$REPORT_DIR_ROOT/source-$source_index"
  purge_dir "$LIVE_ROOT"
  purge_dir "$REPORT_DIR"
  unsquashfs -force -no-xattrs -ignore-errors -no-exit-code -d "$LIVE_ROOT" "$SQUASHFS_PATH" >/dev/null
  prepare_live_root "$LIVE_ROOT" "$REPORT_DIR"
  mksquashfs "$LIVE_ROOT" "$SQUASHFS_PATH" -noappend -no-xattrs -all-root >/dev/null
  PATCHED_SQUASHFS_PATHS+=("$SQUASHFS_PATH")
  if [ -z "$PRIMARY_LIVE_ROOT" ]; then
    PRIMARY_LIVE_ROOT="$LIVE_ROOT"
    PRIMARY_INSTALLER_REPORT="$REPORT_DIR/ubuntu-installer-disable-report.json"
    PRIMARY_GUEST_AGENT_STAGE_REPORT="$REPORT_DIR/live-guest-agent-stage-report.json"
    PRIMARY_GUEST_AGENT_STAGING_REPORT="$REPORT_DIR/live-guest-agent-staging-report.json"
    PRIMARY_BUNDLED_OLLAMA_STAGE_REPORT="$REPORT_DIR/bundled-ollama-stage-report.json"
    PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT="$REPORT_DIR/bundled-ollama-verify-report.json"
    cp "$PRIMARY_INSTALLER_REPORT" "$ISO_ROOT/agentos/ubuntu-installer-disable-report.json"
    cp "$PRIMARY_GUEST_AGENT_STAGE_REPORT" "$ISO_ROOT/agentos/live-guest-agent-stage-report.json"
    cp "$PRIMARY_GUEST_AGENT_STAGING_REPORT" "$ISO_ROOT/agentos/live-guest-agent-staging-report.json"
    cp "$PRIMARY_BUNDLED_OLLAMA_STAGE_REPORT" "$ISO_ROOT/agentos/bundled-ollama-stage-report.json"
    cp "$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT" "$ISO_ROOT/agentos/bundled-ollama-verify-report.json"
  fi
  source_index=$((source_index + 1))
done

if [ "${#PATCHED_SQUASHFS_PATHS[@]}" -eq 0 ]; then
  echo "unable to patch any live filesystem squashfs in remaster tree" >&2
  exit 1
fi

ACTIVE_LIVE_SOURCE_REPORT="$ISO_ROOT/agentos/active-live-source-report.json"
python3 - "$ISO_ROOT" "$ACTIVE_LIVE_SOURCE_REPORT" "${PATCHED_SQUASHFS_PATHS[@]}" <<'PY'
import json
import sys
from pathlib import Path

iso_root = Path(sys.argv[1])
output = Path(sys.argv[2])
paths = [str(Path(path).resolve().relative_to(iso_root.resolve())) for path in sys.argv[3:]]
payload = {
    "iso_root": str(iso_root.resolve()),
    "patched_squashfs_paths": paths,
    "patched_squashfs_count": len(paths),
}
output.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
PY

BOOT_PATCH_REPORT="$WORK_DIR/boot-entry-patch-report.json"
python3 "$PATCH_BOOT_ENTRIES_CMD" --iso-root "$ISO_ROOT" --output "$BOOT_PATCH_REPORT" >/dev/null
BOOT_TARGET_ACTIVATION_REPORT="$ISO_ROOT/agentos/boot-target-activation.json"
python3 "$BOOT_TARGET_ACTIVATION_CMD" \
  --iso-root "$ISO_ROOT" \
  --boot-patch-report "$BOOT_PATCH_REPORT" \
  --output "$BOOT_TARGET_ACTIVATION_REPORT" >/dev/null
BOOT_FLOW_PROOF="$ISO_ROOT/agentos/boot-flow-proof.json"
python3 "$BOOT_FLOW_PROOF_CMD" \
  --iso-root "$ISO_ROOT" \
  --live-root "$PRIMARY_LIVE_ROOT" \
  --boot-patch-report "$BOOT_PATCH_REPORT" \
  --output "$BOOT_FLOW_PROOF" >/dev/null
VM_FIRST_SCREEN_EVIDENCE="$ISO_ROOT/agentos/vm-first-screen-evidence.json"
python3 "$VM_FIRST_SCREEN_EVIDENCE_CMD" \
  --iso-root "$ISO_ROOT" \
  --boot-flow-proof "$BOOT_FLOW_PROOF" \
  --boot-target-activation "$BOOT_TARGET_ACTIVATION_REPORT" \
  --output "$VM_FIRST_SCREEN_EVIDENCE" >/dev/null
INSTALLER_HIDDEN_DEFAULT_PATH="$(
  python3 - "$BOOT_PATCH_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("installer_hidden_default_path") else "false")
PY
)"
BOOT_TARGET_ACTIVATED="$(
  python3 - "$BOOT_TARGET_ACTIVATION_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("boot_target_activated") else "false")
PY
)"
LIVE_GUEST_AGENT_BOOTSTRAP_STAGED="$(
  python3 - "$PRIMARY_GUEST_AGENT_STAGING_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("live_guest_agent_bootstrap_staged") else "false")
PY
)"
LIVE_GUEST_AGENT_PRESTAGED="$(
  python3 - "$PRIMARY_GUEST_AGENT_STAGING_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("live_guest_agent_prestaged") else "false")
PY
)"
LIVE_GUEST_AGENT_REACHABILITY_PATH="$(
  python3 - "$PRIMARY_GUEST_AGENT_STAGING_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("live_guest_agent_reachability_path", "unstaged"))
PY
)"
UBUNTU_INSTALLER_MASKED="$(
  python3 - "$PRIMARY_INSTALLER_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("installer_masked") else "false")
PY
)"
AGENTOS_WELCOME_ASSETS_STAGED="$(
  python3 - "$PRIMARY_INSTALLER_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("agentos_welcome_owns_first_screen") else "false")
PY
)"
AGENTOS_WELCOME_OWNS_FIRST_SCREEN="false"
BUNDLED_LOCAL_PROVIDER_STAGED="$(
  python3 - "$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("bundled_local_provider_staged") else "false")
PY
)"
BUNDLED_LOCAL_MODEL_STAGED="$(
  python3 - "$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("bundled_local_model_staged") else "false")
PY
)"
BUNDLED_LOCAL_SERVICE_STAGED="$(
  python3 - "$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("bundled_local_service_staged") else "false")
PY
)"
BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED="$(
  python3 - "$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("bundled_local_firstrun_service_staged") else "false")
PY
)"
PATCHED_SQUASHFS_PATHS_MANIFEST="$(
  python3 - "$ISO_ROOT" "${PATCHED_SQUASHFS_PATHS[@]}" <<'PY'
import sys
from pathlib import Path

iso_root = Path(sys.argv[1]).resolve()
paths = [str(Path(path).resolve().relative_to(iso_root)) for path in sys.argv[2:]]
print(":".join(paths))
PY
)"

if [ "${AGENTOS_REMASTER_STUB_MODE:-0}" = "1" ]; then
  printf 'stub remastered iso for %s
' "$VERSION" > "$OUTPUT_ISO"
else
  BOOT_REPLAY_ARGS=()
  while IFS= read -r -d '' arg; do
    BOOT_REPLAY_ARGS+=("$arg")
  done < <(xorriso_boot_replay_args "$BASE_IMAGE")
  xorriso     -indev "$BASE_IMAGE"     -outdev "$OUTPUT_ISO"     -map "$ISO_ROOT" /     "${BOOT_REPLAY_ARGS[@]}"     -commit     -end >/dev/null 2>&1
fi

mkdir -p "$(dirname "$BUILD_MANIFEST")"
cat > "$BUILD_MANIFEST" <<MANIFEST
agentos_version=$VERSION
arch=$ARCH
build_mode=remaster_pipeline
base_image=$BASE_IMAGE
output_iso=$OUTPUT_ISO
asset_bundle=$ASSET_BUNDLE
asset_manifest=$ASSET_MANIFEST
remaster_work_dir=$WORK_DIR
live_root=$PRIMARY_LIVE_ROOT
iso_root=$ISO_ROOT
squashfs_path=${PATCHED_SQUASHFS_PATHS[0]}
patched_squashfs_paths=$PATCHED_SQUASHFS_PATHS_MANIFEST
active_live_source_report=$ACTIVE_LIVE_SOURCE_REPORT
boot_assets_injected=true
welcome_shell_injected=true
recovery_shell_injected=true
boot_patch_report=$BOOT_PATCH_REPORT
boot_target_activation_report=$BOOT_TARGET_ACTIVATION_REPORT
boot_target_activated=$BOOT_TARGET_ACTIVATED
boot_flow_proof=$BOOT_FLOW_PROOF
boot_flow_proof_included=true
vm_first_screen_evidence=$VM_FIRST_SCREEN_EVIDENCE
vm_first_screen_evidence_included=true
installer_hidden_default_path=$INSTALLER_HIDDEN_DEFAULT_PATH
ubuntu_installer_disable_report=$PRIMARY_INSTALLER_REPORT
ubuntu_installer_masked=$UBUNTU_INSTALLER_MASKED
agentos_welcome_assets_staged=$AGENTOS_WELCOME_ASSETS_STAGED
agentos_welcome_runtime_observed=false
agentos_welcome_owns_first_screen=$AGENTOS_WELCOME_OWNS_FIRST_SCREEN
live_guest_agent_staging_report=$PRIMARY_GUEST_AGENT_STAGING_REPORT
live_guest_agent_bootstrap_staged=$LIVE_GUEST_AGENT_BOOTSTRAP_STAGED
live_guest_agent_prestaged=$LIVE_GUEST_AGENT_PRESTAGED
live_guest_agent_reachability_path=$LIVE_GUEST_AGENT_REACHABILITY_PATH
headless_live_session_bootstrap_service_staged=true
bundled_ollama_stage_report=$PRIMARY_BUNDLED_OLLAMA_STAGE_REPORT
bundled_ollama_verify_report=$PRIMARY_BUNDLED_OLLAMA_VERIFY_REPORT
bundled_local_provider_staged=$BUNDLED_LOCAL_PROVIDER_STAGED
bundled_local_model_staged=$BUNDLED_LOCAL_MODEL_STAGED
bundled_local_service_staged=$BUNDLED_LOCAL_SERVICE_STAGED
bundled_local_firstrun_service_staged=$BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED
utc_remastered=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MANIFEST

echo "$OUTPUT_ISO"
