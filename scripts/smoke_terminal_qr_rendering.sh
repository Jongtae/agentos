#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

URL="http://198.51.100.12:8787/setup"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

scripts/agentos-terminal-qr "$URL" > "$OUT"

python3 - "$OUT" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
lines = [line for line in plain.splitlines() if line]

assert lines, "QR output is empty"
assert len(lines) == 37, f"expected large version-3 QR height with quiet zone, got {len(lines)}"
assert all(len(line) == 74 for line in lines), sorted(set(len(line) for line in lines))
assert "#" not in plain, "QR should not fall back to hash glyphs"
assert "▀" not in plain and "▄" not in plain and "█" not in plain, "default QR should use background blocks, not half-block glyphs"
assert "\x1b[47m" in text and "\x1b[40m" in text, "large QR should preserve white/black background modules"
PY

grep -q -- '--large' cmd/agentos-operator-tui/main.go

echo "terminal qr rendering smoke: PASS"
