# AgentOS managed shell session profile
# Installed by scripts/install_kernel_boot_integration.sh

AGENTOS_REPO_ROOT="__AGENTOS_REPO_ROOT__"
AGENTOS_RUNTIME_ROOT="__AGENTOS_REPO_ROOT__"
AGENTOS_WORKSPACE="__AGENTOS_WORKSPACE__"

agentos_emit_broker() {
  if [ "${AGENTOS_BROKER_BYPASS:-0}" = "1" ]; then
    return 0
  fi
  if [ ! -f "$AGENTOS_REPO_ROOT/src/broker_emit.py" ]; then
    return 0
  fi
  python3 "$AGENTOS_REPO_ROOT/src/broker_emit.py" \
    --workspace "$AGENTOS_WORKSPACE" \
    "$@" >/dev/null 2>&1 || true
}

if [ "${AGENTOS_BOOT_AUTOSTART:-1}" != "1" ]; then
  # Recovery shortcut: leave tty1 on the normal login shell.
  agentos_emit_broker \
    --kind override \
    --action boot_autostart_bypass \
    --state override \
    --reason "operator disabled AgentOS managed shell session autostart" \
    --component agentos-profile \
    --path tty1_autostart \
    --object-field "status=bypassed"
  return
fi

# Only launch from interactive login shells.
case "$-" in
  *i*) ;;
  *) return ;;
esac

# Keep root/recovery sessions on normal shell for safety.
if [ "$(id -u)" -eq 0 ]; then
  return
fi

if [ -n "${AGENTOS_SHELL_STARTED:-}" ]; then
  return
fi

if [ -n "${SSH_TTY:-}" ]; then
  return
fi

TTY_PATH="$(tty 2>/dev/null || true)"
if [ "$TTY_PATH" != "/dev/tty1" ]; then
  return
fi

export AGENTOS_SHELL_STARTED=1
export AGENTOS_REPO_ROOT="$AGENTOS_REPO_ROOT"
export AGENTOS_RUNTIME_ROOT="$AGENTOS_RUNTIME_ROOT"
export AGENTOS_OLLAMA_MODELS="${AGENTOS_OLLAMA_MODELS:-/var/lib/agentos/models}"
export OLLAMA_MODELS="$AGENTOS_OLLAMA_MODELS"
export AGENTOS_SESSION_MANAGED=1
export AGENTOS_SESSION_ENTRY=local_tty1
export AGENTOS_SESSION_BANNER_VERSION=phase49-v1
SESSION_ID="$(id -un):tty1"

agentos_print_managed_session_banner() {
  if [ "${AGENTOS_SESSION_BANNER_SHOWN:-0}" = "1" ]; then
    return
  fi
  cat <<EOF
=== AgentOS Managed Session ===
entry: local-tty1
mode: managed-shell
workspace: $AGENTOS_WORKSPACE
path: AgentOS Setup -> AgentOS Managed Session -> ai>
recovery: AGENTOS_BOOT_AUTOSTART=0 keeps tty1 on the normal login shell
EOF
  export AGENTOS_SESSION_BANNER_SHOWN=1
}

if [ "${AGENTOS_BROKER_OVERRIDE:-0}" = "1" ]; then
  agentos_emit_broker \
    --kind override \
    --action emergency_session_override \
    --state override \
    --reason "operator override requested for managed session entry" \
    --component agentos-profile \
    --path tty1_autostart \
    --object-field "tty=$TTY_PATH" \
    --object-field "status=override_active" \
    --correlation-field "session_id=$SESSION_ID"
fi
agentos_print_managed_session_banner
agentos_emit_broker \
  --kind session_entry \
  --action tty1_autostart \
  --state allowed \
  --reason "managed AgentOS shell session entry on tty1" \
  --component agentos-profile \
  --path tty1_autostart \
  --object-field "user_name=$(id -un)" \
  --object-field "tty=$TTY_PATH" \
  --metadata-field "stage=profile_autostart" \
  --correlation-field "session_id=$SESSION_ID"
if [ -x /usr/local/bin/agentos-firstrun ]; then
  export AGENTOS_SESSION_ID="$SESSION_ID"
  /usr/local/bin/agentos-firstrun --workspace "$AGENTOS_WORKSPACE" || true
fi
exec /usr/local/bin/agentos-shell --kernel-mode --workspace "$AGENTOS_WORKSPACE" --no-tui
