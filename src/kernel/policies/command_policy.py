"""
Command Policy — classifies bash commands as allowed / approval_required / blocked.
This is pure logic: no LLM, no tools, no framework dependencies.
"""
from __future__ import annotations

import re
from typing import Literal

# ──────────────────────────────────────────────
# Hard-blocked patterns (refuse outright, no approval possible)
# ──────────────────────────────────────────────
_BLOCKED_PATTERNS: list[str] = [
    r"\brm\s+-[rRfF]*[rR][fF]?[rRfF]*",   # rm -rf, rm -fr, rm -r, etc.
    r"\brm\s+--force",
    r"--no-preserve-root",
    r"\bsudo\b",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r">\s*/dev/(?!null)",                   # write to device (except /dev/null)
    r"\bkill\s+-9\s+1\b",                  # kill init
    r"\bpkill\s+.*init\b",
    r"curl\s+.*\|\s*(bash|sh|zsh|fish)",    # curl pipe to shell
    r"wget\s+.*\|\s*(bash|sh|zsh|fish)",
    r"\bchmod\s+777\b",
    r"\bchmod\s+-R\s+777\b",
    r"\bshred\b",
    r"\bwipe\b",
    r":(){:|:&};:",                         # fork bomb
]

_COMPILED_BLOCKED = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

# ──────────────────────────────────────────────
# Safe allowlist (execute without approval)
# ──────────────────────────────────────────────
_ALLOWED_PREFIXES: set[str] = {
    "ls", "ll", "la",
    "cat", "less", "more", "head", "tail",
    "grep", "egrep", "fgrep", "rg",
    "find", "locate",
    "echo", "printf",
    "pwd", "cd",
    "mkdir",
    "cp",
    "mv",
    "touch",
    "wc", "sort", "uniq", "cut", "awk", "sed", "tr",
    "diff", "patch",
    "which", "whereis", "type",
    "env", "printenv", "export",
    "date", "cal", "uptime",
    "python3", "python",
    "pip3", "pip",
    "git",
    "node", "npm", "npx",
    "make",
    "jq", "yq",
    "curl -s", "curl --silent",
    "wget -q", "wget --quiet",
    "zip", "unzip", "tar",
}


CommandClass = Literal["allowed", "approval_required", "blocked"]


def classify(cmd: str) -> CommandClass:
    """
    Classify a command string.

    Returns:
        "blocked"           — refuse, never execute
        "approval_required" — pause, ask user
        "allowed"           — execute immediately
    """
    cmd_stripped = cmd.strip()
    if not cmd_stripped:
        return "allowed"

    # Check hard-block first
    if any(p.search(cmd_stripped) for p in _COMPILED_BLOCKED):
        return "blocked"

    # Check allowlist by first token (or first two tokens for flags like "curl -s")
    tokens = cmd_stripped.split()
    first = tokens[0] if tokens else ""
    first_two = " ".join(tokens[:2]) if len(tokens) >= 2 else first

    if first_two in _ALLOWED_PREFIXES or first in _ALLOWED_PREFIXES:
        return "allowed"

    return "approval_required"


def describe_block(cmd: str) -> str | None:
    """Return the matching block pattern description, or None if not blocked."""
    for pattern, compiled in zip(_BLOCKED_PATTERNS, _COMPILED_BLOCKED):
        if compiled.search(cmd.strip()):
            return f"Matches blocked pattern: {pattern}"
    return None
