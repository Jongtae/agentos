"""CONNECT-DECIDE-01 (#1296): the owner's own MCP servers in a Work, every call decided by AgentOS.

Connection and Delegation Contract §3/§4: an AI-side hand is used only where
AgentOS decides each call.  This module is the thin glue around the CLIs'
own facilities; it holds no authority itself.

* **Which servers.** Only servers the owner confirmed for an engine
  (``CONFIRMED_KEY``, empty by default).  A server the owner merely has in
  their CLI is never started by a Work (contract §10: a local server runs
  code on the owner's Mac).
* **No copy.** A definition is read from the owner's CLI configuration at
  launch time and never stored by AgentOS.  For Codex, values that may be
  secret (server env and HTTP header values) travel only in the CLI process
  environment, named by ``env_vars`` / ``env_http_headers`` and withheld from
  the model's shell; never in arguments, logs or Evidence.
* **One decision point.** Claude Code asks its ``--permission-prompt-tool``;
  Codex runs ``codex_permission_hook`` as a ``PreToolUse`` hook (observed on
  codex-cli 0.153.4: the hook sees the tool name and input, a ``deny`` holds,
  empty output lets the call run, and without ``--dangerously-bypass-hook-trust``
  a session-flag hook is skipped, so that flag is required).
* **Names only.** The decision keys on the server and operation names; core
  code never names a particular server, service or site (C16).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

#: Owner state: ``{engine_id: [server name, ...]}`` the owner confirmed for Works.
CONFIRMED_KEY = 'ai_mcp_servers'
ENGINES = ('claude-code', 'codex')
NAME = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
#: AgentOS's own bridge; never an owner server.
RESERVED = frozenset({'agentos'})
#: Environment names AgentOS sets for the CLI itself; an owner server may not replace them.
RESERVED_ENV = frozenset({'HOME', 'PATH', 'LANG', 'PYTHONPATH', 'USER', 'LOGNAME', 'CODEX_HOME',
                          'CLAUDE_CODE_OAUTH_TOKEN', 'TMPDIR'})
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
MAX_SERVERS = 8
#: claude.ai connectors arrive with the Claude Code login, under this tool-name prefix.
AI_CONNECTION_PREFIX = 'mcp__claude_ai_'
#: The codex-cli flag without which a session-flag hook is skipped (observed, 0.153.4).
CODEX_HOOK_TRUST_FLAG = '--dangerously-bypass-hook-trust'
CODEX_MCP_GET_SECONDS = 10


def confirmed(store, engine_id):
    """The server names the owner confirmed for this engine, validated; anything malformed is dropped."""
    rows = (store.config(CONFIRMED_KEY, {}) or {}) if store is not None else {}
    names = rows.get(engine_id) if isinstance(rows, dict) else None
    return [name for name in (names if isinstance(names, list) else [])
            if isinstance(name, str) and NAME.match(name) and name not in RESERVED][:MAX_SERVERS]


def set_confirmed(store, engine_id, names):
    """Replace the owner's confirmed servers for one engine; returns the stored list."""
    if engine_id not in ENGINES:
        raise ValueError('지원하는 AI를 선택하세요.')
    clean = []
    for name in names or ():
        if not isinstance(name, str) or not NAME.match(name) or name in RESERVED:
            raise ValueError('MCP 서버 이름 형식이 아닙니다.')
        if name not in clean:
            clean.append(name)
    if len(clean) > MAX_SERVERS:
        raise ValueError(f'MCP 서버는 {MAX_SERVERS}개까지입니다.')
    rows = store.config(CONFIRMED_KEY, {}) or {}
    rows = dict(rows) if isinstance(rows, dict) else {}
    rows[engine_id] = clean
    store.put(CONFIRMED_KEY, rows)
    return clean


def all_confirmed(store):
    """Every confirmed server name, across engines."""
    return {name for engine_id in ENGINES for name in confirmed(store, engine_id)}


def tool_server(tool_name):
    """``(kind, service, operation)`` for an AI-side MCP tool name, or None.

    ``kind`` is ``ai-connection`` for a claude.ai connector (service name as
    the owner sees it) or ``owner-mcp`` for a server the owner configured.
    AgentOS's own bridge tools and anything that is not an MCP tool name are None.
    """
    if not isinstance(tool_name, str) or len(tool_name) > 200 or not tool_name.startswith('mcp__'):
        return None
    if tool_name.startswith(AI_CONNECTION_PREFIX):
        server, _sep, operation = tool_name[len(AI_CONNECTION_PREFIX):].rpartition('__')
        service = server.replace('_', ' ').strip()[:60]
        return ('ai-connection', service, operation[:60]) if service and operation else None
    server, sep, operation = tool_name[len('mcp__'):].partition('__')
    if not sep or not server or not operation or server in RESERVED:
        return None
    return ('owner-mcp', server[:64], operation[:60])


# -- Codex ---------------------------------------------------------------------------

def codex_definition(binary, name, env, runner=subprocess.run):
    """The owner's Codex definition of one server, read through ``codex mcp get --json``; None if absent/disabled.

    Run under the turn's own environment (``CODEX_HOME`` is the owner's
    profile) without ``--ignore-user-config``, so the owner's configuration is
    what Codex itself reports.  Nothing is stored.
    """
    try:
        done = runner([binary, 'mcp', 'get', name, '--json'], env=env, stdin=subprocess.DEVNULL,
                      capture_output=True, text=True, timeout=CODEX_MCP_GET_SECONDS, shell=False)
        data = json.loads(done.stdout) if done.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('enabled') is False or not isinstance(data.get('transport'), dict):
        return None
    return data['transport']


def _toml(value):
    return json.dumps(value, ensure_ascii=False)


def codex_launch(definitions):
    """``(config args, env values, secret env names)`` that load confirmed servers into one Codex turn.

    ``definitions`` maps server name to its transport.  A server whose
    definition cannot be expressed without putting a value in an argument is
    skipped, never half-loaded.
    """
    args, env, secret = [], {}, []
    for index, (name, transport) in enumerate(sorted(definitions.items())):
        if not NAME.match(name) or name in RESERVED or not isinstance(transport, dict):
            continue
        prefix = f'mcp_servers.{name}'
        server_args, server_env = [], {}
        kind = transport.get('type')
        if kind == 'stdio' and isinstance(transport.get('command'), str) and transport['command']:
            server_args += ['-c', f'{prefix}.command={_toml(transport["command"])}']
            if isinstance(transport.get('args'), list) and all(isinstance(a, str) for a in transport['args']):
                server_args += ['-c', f'{prefix}.args={_toml(transport["args"])}']
            if isinstance(transport.get('cwd'), str) and transport['cwd']:
                server_args += ['-c', f'{prefix}.cwd={_toml(transport["cwd"])}']
            values = transport.get('env') if isinstance(transport.get('env'), dict) else {}
            if not all(isinstance(k, str) and ENV_NAME.match(k) and k not in RESERVED_ENV and isinstance(v, str)
                       for k, v in values.items()):
                continue
            server_env.update(values)
            forwarded = sorted(values)
        elif kind == 'streamable_http' and isinstance(transport.get('url'), str) and transport['url'].startswith('https://'):
            server_args += ['-c', f'{prefix}.url={_toml(transport["url"])}']
            literal = transport.get('http_headers') if isinstance(transport.get('http_headers'), dict) else {}
            named = transport.get('env_http_headers') if isinstance(transport.get('env_http_headers'), dict) else {}
            if not all(isinstance(h, str) and isinstance(v, str) for h, v in literal.items()) \
                    or not all(isinstance(h, str) and isinstance(v, str) and ENV_NAME.match(v) for h, v in named.items()):
                continue
            # A literal header value (often a key) becomes an environment value Codex reads by name.
            headers = dict(named)
            for number, (header, value) in enumerate(sorted(literal.items())):
                variable = f'AGENTOS_MCP_{index}_H{number}'
                headers[header] = variable
                server_env[variable] = value
            if headers:
                server_args += ['-c', f'{prefix}.env_http_headers={_toml(headers)}']
            token = transport.get('bearer_token_env_var')
            if isinstance(token, str) and ENV_NAME.match(token):
                server_args += ['-c', f'{prefix}.bearer_token_env_var={_toml(token)}']
            # Variables the owner's definition names come from AgentOS's own environment when set there.
            for variable in [*named.values(), *([token] if isinstance(token, str) and ENV_NAME.match(token) else [])]:
                if variable in os.environ:
                    server_env[variable] = os.environ[variable]
            if any(k in RESERVED_ENV for k in server_env):
                continue
            forwarded = []
        else:
            continue
        if any(k in env and env[k] != v for k, v in server_env.items()):
            continue    # two servers would need one name with different values
        if kind == 'stdio' and forwarded:
            server_args += ['-c', f'{prefix}.env_vars={_toml(forwarded)}']
        # The hook decides each call; Codex's own reviewer is not a second decision (#709 pattern).
        server_args += ['-c', f'{prefix}.default_tools_approval_mode="approve"']
        args += server_args
        env.update(server_env)
        secret += sorted(server_env)
    if secret:
        # The model's shell commands never inherit these values.
        args += ['-c', f'shell_environment_policy.exclude={_toml(sorted(set(secret)))}']
    return args, env, sorted(set(secret))


def codex_hook_arguments(relay):
    """The session-flag ``PreToolUse`` hook that sends every MCP tool call to AgentOS, plus the trust flag it needs."""
    command = shlex.join((sys.executable, '-m', 'personal_agent.codex_permission_hook', '--relay', str(relay)))
    hook = f'hooks.PreToolUse=[{{matcher={_toml("^mcp__")},hooks=[{{type="command",command={_toml(command)}}}]}}]'
    return [CODEX_HOOK_TRUST_FLAG, '-c', hook]


# -- Claude Code ---------------------------------------------------------------------

def claude_definitions(home, names):
    """The owner's user-scope Claude Code definitions of the confirmed servers (``~/.claude.json``); nothing stored."""
    try:
        data = json.loads((Path(home) / '.claude.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    servers = data.get('mcpServers') if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return {}
    return {name: dict(servers[name]) for name in names
            if name in servers and isinstance(servers[name], dict) and name not in RESERVED}
