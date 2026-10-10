"""CONNECT-DECIDE-01 (#1296): Codex's ``PreToolUse`` hook that asks AgentOS about every MCP tool call.

Codex runs this once per matching call with the call on stdin (``tool_name``,
``tool_input``).  The service decides through the Work's relay, exactly as it
decides Claude Code's permission prompts (``QuickstartService.connector_permission``).

Output follows what codex-cli 0.153.4 accepts (observed): nothing on stdout
lets the call run; ``permissionDecision: deny`` with a non-empty reason
blocks it; ``allow`` is unsupported there.  Anything unexpected — no relay,
a malformed call, an exception — denies.
"""
from __future__ import annotations

import argparse
import json
import sys

from .cli_browser_relay import RelayClient

REFUSED_TEXT = 'AgentOS could not decide this action, so it was not run.'
MAX_INPUT_BYTES = 1_000_000
BRIDGE_PREFIX = 'mcp__agentos__'


def decide(call, relay):
    """``None`` to let the call run, else the refusal reason."""
    if not isinstance(call, dict) or not isinstance(call.get('tool_name'), str):
        return REFUSED_TEXT
    # AgentOS's own bridge decides its tools itself (#709); the matcher cannot exclude them
    # (Codex hook matchers are Rust regexes, without lookahead).  No owner server may be named
    # ``agentos`` (``owner_mcp.RESERVED``), so this prefix is only ever the bridge.
    if call['tool_name'].startswith(BRIDGE_PREFIX):
        return None
    try:
        decision = relay.call('connector_permission', {'tool_name': call['tool_name'],
                                                       'input': call.get('tool_input')})
    except Exception:
        return REFUSED_TEXT
    if isinstance(decision, dict) and decision.get('behavior') == 'allow':
        return None
    message = decision.get('message') if isinstance(decision, dict) else None
    return message if isinstance(message, str) and message.strip() else REFUSED_TEXT


def main(argv=None, stdin=None, stdout=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--relay', required=True)
    args = parser.parse_args(argv)
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    try:
        raw = stdin.read(MAX_INPUT_BYTES + 1)
        call = json.loads(raw) if len(raw) <= MAX_INPUT_BYTES else None
    except (ValueError, OSError):
        call = None
    reason = decide(call, RelayClient(args.relay))
    if reason is not None:
        stdout.write(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                         'permissionDecisionReason': reason[:500]}}, ensure_ascii=False))
    stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
