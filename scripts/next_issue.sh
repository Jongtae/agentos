#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Jongtae/agentos}"
BASE_BRANCH="${2:-main}"
BRANCH_PREFIX="${3:-codex/task}"

# Enforce single in-progress policy.
IN_PROGRESS=$(gh issue list -R "$REPO" --state open --label "status:in-progress" --limit 100 --json number,title)
COUNT=$(printf "%s" "$IN_PROGRESS" | jq 'length')
if [ "$COUNT" -gt 0 ]; then
  echo "There is already an in-progress issue:" 
  printf "%s" "$IN_PROGRESS" | jq -r '.[] | "- #\(.number) \(.title)"'
  echo "Complete or revert it before starting the next issue."
  exit 1
fi

# Pick next ready issue by priority labels then oldest number.
READY=$(gh issue list -R "$REPO" --state open --label "status:ready" --limit 200 --json number,title,labels)
if [ "$(printf "%s" "$READY" | jq 'length')" -eq 0 ]; then
  echo "No ready issues found."
  exit 0
fi

pick_issue() {
  local prio="$1"
  printf "%s" "$READY" | jq -r --arg p "$prio" '
    [ .[] | select(any(.labels[]?.name; . == $p)) ]
    | sort_by(.number)
    | .[0] // empty
  '
}

CAND=$(pick_issue "prio:p0")
if [ -z "$CAND" ]; then CAND=$(pick_issue "prio:p1"); fi
if [ -z "$CAND" ]; then CAND=$(pick_issue "prio:p2"); fi
if [ -z "$CAND" ]; then
  CAND=$(printf "%s" "$READY" | jq -r 'sort_by(.number) | .[0]')
fi

ISSUE_NUM=$(printf "%s" "$CAND" | jq -r '.number')
ISSUE_TITLE=$(printf "%s" "$CAND" | jq -r '.title')

SLUG=$(printf "%s" "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/\[[^]]+\]//g' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-+|-+$//g' | cut -c1-40)
BRANCH_NAME="$BRANCH_PREFIX-$ISSUE_NUM-$SLUG"

# start from main (or chosen base)
git checkout "$BASE_BRANCH" >/dev/null
git pull --ff-only origin "$BASE_BRANCH" >/dev/null
git checkout -b "$BRANCH_NAME" >/dev/null

gh issue edit "$ISSUE_NUM" -R "$REPO" --remove-label "status:ready" --add-label "status:in-progress" >/dev/null || true
gh issue comment "$ISSUE_NUM" -R "$REPO" --body "Started automatically in branch \`$BRANCH_NAME\`." >/dev/null

echo "Started #$ISSUE_NUM: $ISSUE_TITLE"
echo "Branch: $BRANCH_NAME"
