#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 0.1.1"
  echo "Example: $0 v0.1.1"
  exit 1
fi

RAW="$1"
VER="${RAW#v}"

if [[ ! "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must match semantic format: MAJOR.MINOR.PATCH"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FILE="$ROOT_DIR/src/version.py"

if [ ! -f "$FILE" ]; then
  echo "Missing $FILE"
  exit 1
fi

python3 - "$FILE" "$VER" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
text = path.read_text(encoding="utf-8")
updated = re.sub(r'APP_VERSION\s*=\s*"[0-9]+\.[0-9]+\.[0-9]+"', f'APP_VERSION = "{version}"', text)
if updated == text:
    raise SystemExit("Could not update APP_VERSION in src/version.py")
path.write_text(updated, encoding="utf-8")
PY

echo "Updated APP_VERSION to $VER"
