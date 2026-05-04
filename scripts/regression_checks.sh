#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

python3 <<'PY'
from __future__ import annotations

import http.server
import socketserver
import tempfile
import threading
from functools import partial
from pathlib import Path

from kernel.policies.command_policy import classify
from workspace.sandbox import safe_path
from kernel.tools.web_tool import WebTool

checks = []

# M4-01 / M4-02 / M4-03 policy classification
checks.append(("bash_allowed", classify("ls -la") == "allowed"))
checks.append(("bash_approval_required", classify("chmod 755 test.sh") == "approval_required"))
checks.append(("bash_blocked", classify("rm -rf /") == "blocked"))

# M4-04 sandbox traversal block
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    ok = False
    try:
        safe_path(root, "../../etc/passwd")
    except ValueError:
        ok = True
    checks.append(("sandbox_traversal_block", ok))

# M4-05 web fetch
web = WebTool()
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    index = root / "index.html"
    index.write_text("<html><body>hello-agentos</body></html>", encoding="utf-8")

    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    handler = partial(SilentHandler, directory=str(root))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        out = web.run({"url": f"http://127.0.0.1:{port}/index.html"})
        httpd.shutdown()

checks.append(("web_fetch_basic", isinstance(out, str) and "hello-agentos" in out and not out.startswith("[error]")))

print("Regression Checks")
print("=================")
all_ok = True
for name, ok in checks:
    print(f"{name:28} {'PASS' if ok else 'FAIL'}")
    all_ok = all_ok and ok

if not all_ok:
    raise SystemExit(1)
PY
