"""Subscription-engine discovery and connection records.

This module deliberately does not start an engine or inspect credential files.
Codex and Claude Code retain their official login sessions; AgentOS only
records an owner's choice for a later bounded adapter.
"""
import os
from dataclasses import dataclass
from shutil import which
from time import time

#: Where the official installers put these CLIs, searched after PATH (#932): a
#: launchd service starts with PATH=/usr/bin:/bin:/usr/sbin:/sbin and so finds
#: none of them.  Claude Code's native installer uses ~/.local/bin; Homebrew
#: uses /opt/homebrew/bin (Apple silicon) or /usr/local/bin.
INSTALL_DIRS = ('~/.local/bin', '/opt/homebrew/bin', '/usr/local/bin')


def find_cli(command, *, path=None, home=None):
    """``command`` on PATH, else in an official install directory; None when absent."""
    found = which(command, path=path)
    if found:
        return found
    base = os.path.expanduser('~') if home is None else str(home)
    dirs = [os.path.join(base, entry[2:]) if entry.startswith('~/') else entry for entry in INSTALL_DIRS]
    return which(command, path=os.pathsep.join(dirs))


@dataclass(frozen=True)
class SubscriptionEngine:
    id: str
    name: str
    command: str
    login_command: str
    login_url: str


ENGINES = {
    'codex': SubscriptionEngine('codex', 'Codex', 'codex', 'codex login', 'https://developers.openai.com/codex/cli/'),
    'claude-code': SubscriptionEngine('claude-code', 'Claude Code', 'claude', 'claude', 'https://docs.anthropic.com/en/docs/claude-code/overview'),
}


class SubscriptionEngines:
    """Find official CLIs without reading credentials or invoking a shell."""
    def __init__(self, finder=find_cli, clock=time):
        self.finder, self.clock = finder, clock

    def available(self):
        return [{'id': engine.id, 'name': engine.name,
                 'installed': bool(self.finder(engine.command)),
                 'login_command': engine.login_command, 'login_url': engine.login_url}
                for engine in ENGINES.values()]

    def connect(self, engine_id, officially_authenticated):
        if engine_id not in ENGINES:
            raise ValueError('지원하는 구독 엔진을 선택하세요.')
        engine = ENGINES[engine_id]
        if not self.finder(engine.command):
            raise ValueError(f'{engine.name} CLI를 찾지 못했습니다. 공식 설치 안내를 확인하세요.')
        if officially_authenticated is not True:
            raise ValueError('공식 로그인 완료를 확인한 뒤에만 연결할 수 있습니다.')
        return {'id': engine.id, 'connected_at': self.clock(),
                'authentication': 'owner-confirmed-official-login'}
