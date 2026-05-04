#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <version-tag> [repo]"
  echo "Example: $0 v0.1.0 Jongtae/agentos"
  exit 1
fi

TAG="$1"
REPO="${2:-Jongtae/agentos}"
EXPECTED_TAG="v$(python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str((Path.cwd() / "src").resolve()))
from version import APP_VERSION
print(APP_VERSION)
PY
)"

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Tag must match semantic format: vMAJOR.MINOR.PATCH"
  exit 1
fi

if [ "$TAG" != "$EXPECTED_TAG" ]; then
  echo "Tag/version mismatch:"
  echo "- requested tag: $TAG"
  echo "- APP_VERSION:   $EXPECTED_TAG"
  echo "Run scripts/bump_version.sh ${TAG#v} first, commit, then retry."
  exit 1
fi

# Ensure clean working tree for reliable release cut.
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit/stash changes before release cut."
  exit 1
fi

# Prevent duplicate release tags.
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  echo "Release $TAG already exists in $REPO"
  exit 1
fi

# Push local main branch state first.
git checkout main >/dev/null
git pull --ff-only origin main >/dev/null
git push origin main >/dev/null

LAST_TAG=""
if git describe --tags --abbrev=0 >/dev/null 2>&1; then
  LAST_TAG="$(git describe --tags --abbrev=0)"
fi

if [ -n "$LAST_TAG" ]; then
  RANGE="$LAST_TAG..HEAD"
  NOTES_HEADER="Changes since $LAST_TAG"
else
  RANGE="HEAD"
  NOTES_HEADER="Initial release"
fi

TMP_NOTES="$(mktemp)"
trap 'rm -f "$TMP_NOTES"' EXIT

{
  echo "## $NOTES_HEADER"
  echo
  git log --no-merges --pretty='- %s (%h)' "$RANGE"
  echo
  echo "## Verification"
  echo "- CI workflow green"
  echo "- acceptance checks pass"
} > "$TMP_NOTES"

git tag "$TAG"
git push origin "$TAG"

gh release create "$TAG" -R "$REPO" --title "$TAG" --notes-file "$TMP_NOTES"

echo "Release created: $TAG"
