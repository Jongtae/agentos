#!/usr/bin/env bash
set -euo pipefail

# M35 foundation script: keep install path deterministic and online-first.
export DEBIAN_FRONTEND=noninteractive

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLICY_FILE="$SCRIPT_DIR/apt-packages.policy"
INSTALL_PREFIX="${AGENTOS_INSTALL_PREFIX:-/opt/agentos}"
RUNTIME_BUNDLE_DIR="${AGENTOS_RUNTIME_BUNDLE_DIR:-$SCRIPT_DIR/../runtime/agentos}"
APP_ROOT="${AGENTOS_APP_ROOT:-/usr/lib/agentos}"
INSTALL_ROOT="${AGENTOS_INSTALL_ROOT:-/}"
DEFAULT_WORKSPACE="${AGENTOS_DEFAULT_WORKSPACE:-/home/ubuntu/agentos-ws}"
SEED_WORKSPACE="${AGENTOS_SEED_WORKSPACE:-/var/lib/agentos/workspaces/default}"
AGENTOS_RUNTIME_USER="${AGENTOS_RUNTIME_USER:-${AGENTOS_USER:-ubuntu}}"
AGENTOS_MODELS_ROOT="${AGENTOS_MODELS_ROOT:-/var/lib/agentos/models}"
if [ "$INSTALL_ROOT" = "/" ]; then
  EFFECTIVE_MODELS_ROOT="$AGENTOS_MODELS_ROOT"
else
  EFFECTIVE_MODELS_ROOT="$INSTALL_ROOT$AGENTOS_MODELS_ROOT"
fi

if [ ! -f "$POLICY_FILE" ]; then
  echo "[agentos-postinstall] missing apt policy file: $POLICY_FILE" >&2
  exit 1
fi

declare -a core_packages=()
declare -a optional_packages=()

while IFS='|' read -r pkg min_version major tier; do
  pkg="${pkg//[[:space:]]/}"
  min_version="${min_version//[[:space:]]/}"
  major="${major//[[:space:]]/}"
  tier="${tier//[[:space:]]/}"
  if [ -z "$pkg" ] || [[ "$pkg" == \#* ]]; then
    continue
  fi
  case "$tier" in
    core)
      core_packages+=("$pkg")
      ;;
    optional)
      optional_packages+=("$pkg")
      ;;
    *)
      echo "[agentos-postinstall] invalid tier '$tier' in $POLICY_FILE for package '$pkg'" >&2
      exit 1
      ;;
  esac
done < "$POLICY_FILE"

apt-get update
apt-get install -y --no-install-recommends "${core_packages[@]}"

verify_policy_entry() {
  local pkg="$1"
  local min_version="$2"
  local required_major="$3"
  local tier="$4"

  local installed_version=""
  if ! installed_version="$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null)"; then
    if [ "$tier" = "core" ]; then
      echo "[agentos-postinstall] required package missing: $pkg" >&2
      exit 1
    fi
    echo "[agentos-postinstall] optional package not installed: $pkg"
    return 0
  fi

  if [ -n "$min_version" ] && ! dpkg --compare-versions "$installed_version" ge "$min_version"; then
    if [ "$tier" = "core" ]; then
      echo "[agentos-postinstall] $pkg version '$installed_version' does not satisfy min '$min_version'" >&2
      exit 1
    fi
    echo "[agentos-postinstall] optional package $pkg version '$installed_version' is below '$min_version'"
    return 0
  fi

  if [ -n "$required_major" ]; then
    local normalized installed_major
    normalized="$(printf '%s' "$installed_version" | sed -E 's/^[0-9]+://')"
    installed_major="$(printf '%s' "$normalized" | sed -E 's/^([0-9]+).*/\1/')"
    if [ "$installed_major" != "$required_major" ]; then
      if [ "$tier" = "core" ]; then
        echo "[agentos-postinstall] $pkg major '$installed_major' does not match required '$required_major'" >&2
        exit 1
      fi
      echo "[agentos-postinstall] optional package $pkg major '$installed_major' != '$required_major'"
      return 0
    fi
  fi
}

while IFS='|' read -r pkg min_version major tier; do
  pkg="${pkg//[[:space:]]/}"
  min_version="${min_version//[[:space:]]/}"
  major="${major//[[:space:]]/}"
  tier="${tier//[[:space:]]/}"
  if [ -z "$pkg" ] || [[ "$pkg" == \#* ]]; then
    continue
  fi
  verify_policy_entry "$pkg" "$min_version" "$major" "$tier"
done < "$POLICY_FILE"

if [ "${#optional_packages[@]}" -gt 0 ]; then
  echo "[agentos-postinstall] optional packages policy tracked: ${optional_packages[*]}"
  echo "[agentos-postinstall] local LLM default path prefers Ollama when available."
fi

if [ ! -d "$RUNTIME_BUNDLE_DIR" ]; then
  echo "[agentos-postinstall] missing runtime bundle: $RUNTIME_BUNDLE_DIR" >&2
  exit 1
fi

mkdir -p "$(dirname "$APP_ROOT")"
rm -rf "$APP_ROOT"
mkdir -p "$APP_ROOT"
cp -R "$RUNTIME_BUNDLE_DIR/." "$APP_ROOT/"

mkdir -p "$SEED_WORKSPACE/documents" "$SEED_WORKSPACE/artifacts" "$DEFAULT_WORKSPACE/documents" "$DEFAULT_WORKSPACE/artifacts" "$DEFAULT_WORKSPACE/data"
mkdir -p "$EFFECTIVE_MODELS_ROOT"
if [ ! -f "$SEED_WORKSPACE/spec.yaml" ]; then
  cat > "$SEED_WORKSPACE/spec.yaml" <<'SPEC'
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
SPEC
fi
if [ ! -f "$SEED_WORKSPACE/documents/agentos-first-run.md" ]; then
  cat > "$SEED_WORKSPACE/documents/agentos-first-run.md" <<'DOC'
# AgentOS First Run

This workspace document proves repo-free native document access on a fresh AgentOS image.

- runtime: Codex-managed AgentOS session
- capability goal: document + web + summary
- proof path: installed `agentos-kernelctl` surfaces only
DOC
fi

if [ ! -f "$DEFAULT_WORKSPACE/spec.yaml" ]; then
  cp "$SEED_WORKSPACE/spec.yaml" "$DEFAULT_WORKSPACE/spec.yaml"
fi
if [ ! -f "$DEFAULT_WORKSPACE/documents/agentos-first-run.md" ]; then
  cp "$SEED_WORKSPACE/documents/agentos-first-run.md" "$DEFAULT_WORKSPACE/documents/agentos-first-run.md"
fi

# Repo-free first-run must work from the installed image without a copied repo.
# Keep the default workspace writable for the managed AgentOS session user and
# permissive enough for live-session boot paths where ownership is fixed later.
chmod -R a+rwX "$SEED_WORKSPACE"
chmod -R a+rwX "$DEFAULT_WORKSPACE"
chmod -R a+rwX "$EFFECTIVE_MODELS_ROOT"
if id -u "$AGENTOS_RUNTIME_USER" >/dev/null 2>&1; then
  chown -R "$AGENTOS_RUNTIME_USER:$AGENTOS_RUNTIME_USER" "$SEED_WORKSPACE"
  chown -R "$AGENTOS_RUNTIME_USER:$AGENTOS_RUNTIME_USER" "$DEFAULT_WORKSPACE"
  chown -R "$AGENTOS_RUNTIME_USER:$AGENTOS_RUNTIME_USER" "$EFFECTIVE_MODELS_ROOT"
fi

BUNDLED_OLLAMA_ASSET_ROOT="$APP_ROOT/assets/ollama"
if [ -d "$BUNDLED_OLLAMA_ASSET_ROOT/usr-local-root" ]; then
  cp -R "$BUNDLED_OLLAMA_ASSET_ROOT/usr-local-root/." "$INSTALL_ROOT/usr/local/"
  echo "[agentos-postinstall] bundled Ollama binary staged into $INSTALL_ROOT/usr/local"
fi
if [ -d "$BUNDLED_OLLAMA_ASSET_ROOT/models" ]; then
  rm -rf "$EFFECTIVE_MODELS_ROOT"
  mkdir -p "$(dirname "$EFFECTIVE_MODELS_ROOT")"
  cp -R "$BUNDLED_OLLAMA_ASSET_ROOT/models" "$EFFECTIVE_MODELS_ROOT"
  chmod -R a+rwX "$EFFECTIVE_MODELS_ROOT"
  if id -u "$AGENTOS_RUNTIME_USER" >/dev/null 2>&1; then
    chown -R "$AGENTOS_RUNTIME_USER:$AGENTOS_RUNTIME_USER" "$EFFECTIVE_MODELS_ROOT"
  fi
  echo "[agentos-postinstall] bundled Ollama model store staged into $EFFECTIVE_MODELS_ROOT"
fi

mkdir -p "$INSTALL_ROOT/usr/local/bin"
cat > "$INSTALL_ROOT/usr/local/bin/agentos-ollama-serve" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME="${HOME:-/var/lib/agentos}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/var/lib/agentos/models}"
exec /usr/local/bin/ollama serve
EOF
chmod 0755 "$INSTALL_ROOT/usr/local/bin/agentos-ollama-serve"
cat > "$INSTALL_ROOT/usr/local/bin/agentos-engine-availability-refresh" <<'EOF'
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
chmod 0755 "$INSTALL_ROOT/usr/local/bin/agentos-engine-availability-refresh"

mkdir -p "$INSTALL_ROOT/etc/systemd/system/multi-user.target.wants"
cat > "$INSTALL_ROOT/etc/systemd/system/agentos-ollama.service" <<'EOF'
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
ln -sf ../agentos-ollama.service "$INSTALL_ROOT/etc/systemd/system/multi-user.target.wants/agentos-ollama.service"
cat > "$INSTALL_ROOT/etc/systemd/system/agentos-engine-availability.service" <<'EOF'
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
ln -sf ../agentos-engine-availability.service "$INSTALL_ROOT/etc/systemd/system/multi-user.target.wants/agentos-engine-availability.service"

cd "$APP_ROOT"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

BOOT_VISUALS_INSTALLER="$APP_ROOT/scripts/install_agentos_boot_visuals.sh"
if [ -x "$BOOT_VISUALS_INSTALLER" ]; then
  "$BOOT_VISUALS_INSTALLER" || echo "[agentos-postinstall] boot visuals install fell back to default boot visuals"
else
  echo "[agentos-postinstall] boot visuals installer not found: $BOOT_VISUALS_INSTALLER"
fi

AGENTOS_REPO_ROOT="$APP_ROOT" \
AGENTOS_RUNTIME_ROOT="$APP_ROOT" \
AGENTOS_RUNTIME_ROOT_EMBED="$APP_ROOT" \
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
DEFAULT_WORKSPACE="$DEFAULT_WORKSPACE" \
AGENTOS_DEFAULT_WORKSPACE="$DEFAULT_WORKSPACE" \
AGENTOS_INSTALLED_DEFAULT_WORKSPACE="$DEFAULT_WORKSPACE" \
AGENTOS_INSTALLED_SEED_WORKSPACE="$SEED_WORKSPACE" \
AGENTOS_ENABLE_SYSTEMD=1 \
"$APP_ROOT/scripts/install_kernel_boot_integration.sh"
