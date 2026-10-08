#!/bin/sh
# CI-only install smoke check (#1167, #1176): install AgentOS from a clean
# HOME, start it, and require the setup page to answer HTTP 200 and the MCP
# bridge to import. Used by .github/workflows/install-smoke.yml on every
# platform job so the check itself is identical everywhere.
#
#   sh scripts/dev/install_smoke.sh installer   # one-line scripts/install.sh
#   sh scripts/dev/install_smoke.sh homebrew    # brew install jongtae/agentos/agentos
#
# SMOKE_HTTP / SMOKE_NULL replace the HTTP client and its null device, e.g.
# Windows curl.exe and NUL from inside WSL2 to check localhost forwarding.
set -eu

mode=${1:-installer}
port=18787
home=$(mktemp -d)
here=$(cd "$(dirname "$0")" && pwd)

case "$mode" in
  installer)
    env -i HOME="$home" PATH=/usr/bin:/bin:/usr/sbin:/sbin AGENTOS_NO_START=1 sh "$here/../install.sh"
    run() { env -i HOME="$home" PATH="$home/.local/bin:/usr/bin:/bin" "$@"; }
    python="$home/.local/share/uv/tools/personal-agentos/bin/python"
    ;;
  homebrew)
    brew install jongtae/agentos/agentos
    brew list --versions agentos
    run() { env HOME="$home" "$@"; }
    python="$(brew --prefix)/opt/agentos/libexec/bin/python"
    ;;
  *) echo "usage: $0 installer|homebrew" >&2; exit 2 ;;
esac

run agentos start --no-browser --port "$port" </dev/null >"$home/start.log" 2>&1 &
server=$!
http=${SMOKE_HTTP:-curl}
code=000
for _ in $(seq 1 90); do
  code=$("$http" -s -o "${SMOKE_NULL:-/dev/null}" -w '%{http_code}' "http://127.0.0.1:$port/" || true)
  [ "$code" = "200" ] && break
  sleep 1
done
cat "$home/start.log"
echo "setup page HTTP status: $code"
kill "$server" 2>/dev/null || true
[ "$code" = "200" ]
"$python" -c "import mcp.server.stdio; print('MCP bridge import ok')"
