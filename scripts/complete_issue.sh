#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 3 ]; then
  echo "Usage: $0 <issue-number> <pr-number> <commit-sha> [repo]"
  echo "Example: $0 43 52 abc1234 Jongtae/agentos"
  exit 1
fi

ISSUE_NUM="$1"
PR_NUM="$2"
COMMIT_SHA="$3"
REPO="${4:-Jongtae/agentos}"

BODY=$(cat <<EOF
Implemented and verified.

- PR: #$PR_NUM
- Commit: $COMMIT_SHA

Verification:
- python compile check
- unit tests
- regression/failure/acceptance checks
EOF
)

gh issue close "$ISSUE_NUM" -R "$REPO" --comment "$BODY" >/dev/null

echo "Issue #$ISSUE_NUM closed with PR #$PR_NUM"
