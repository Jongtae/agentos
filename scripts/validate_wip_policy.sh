#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Jongtae/agentos}"

IN_PROGRESS_COUNT=$(gh issue list -R "$REPO" --state open --label "status:in-progress" --limit 100 --json number | jq 'length')

if [ "$IN_PROGRESS_COUNT" -gt 1 ]; then
  echo "WIP policy violation: more than one issue is in-progress ($IN_PROGRESS_COUNT)."
  gh issue list -R "$REPO" --state open --label "status:in-progress" --limit 100
  exit 1
fi

echo "WIP policy OK (in-progress issues: $IN_PROGRESS_COUNT)"
