#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <issue-number> <branch-name> [repo]"
  echo "Example: $0 43 codex/m5-01 Jongtae/agentos"
  exit 1
fi

ISSUE_NUM="$1"
BRANCH_NAME="$2"
REPO="${3:-Jongtae/agentos}"

# Ensure working tree is clean before branching
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit or stash changes first."
  exit 1
fi

git checkout -b "$BRANCH_NAME"

gh issue edit "$ISSUE_NUM" -R "$REPO" --remove-label "status:ready" --add-label "status:in-progress" >/dev/null || true

gh issue comment "$ISSUE_NUM" -R "$REPO" --body "Started in branch \`$BRANCH_NAME\`." >/dev/null

echo "Issue #$ISSUE_NUM started on branch $BRANCH_NAME"
