"""Secrets never reach the judge prompt (pilot boundary: no secret in any model prompt).

Adopts AgentOS's own deterministic redaction instead of a new one: the
credential shapes of ``personal_agent.bounded_execution.SECRET_PATTERN`` (the
pattern ``current_context.redact_known_secrets`` applies) plus the literal
values of every stored secret slot, read at run time from the seed's and the
live profile's ``connections.json``.  The values are only held in memory.
"""
import json
import sys
from pathlib import Path

from .paths import LIVE_DATA, SRC

MIN_LITERAL = 8
REDACTED = '[redacted]'


def secret_pattern():
    if str(SRC) not in sys.path:
        sys.path.append(str(SRC))
    from personal_agent.bounded_execution import SECRET_PATTERN
    return SECRET_PATTERN


def secret_values(folders):
    """Literal secret values stored in the ``private/connections.json`` of each data folder."""
    values = set()
    for folder in folders:
        if not folder:
            continue
        try:
            data = json.loads((Path(folder) / 'private' / 'connections.json').read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            values.update(value for value in data.values() if isinstance(value, str) and len(value) >= MIN_LITERAL)
    return values


class Redactor:
    def __init__(self, values=(), pattern=None):
        # Longest first, so a value that contains another is replaced whole.
        self.values = sorted(set(values), key=len, reverse=True)
        self.pattern = pattern if pattern is not None else secret_pattern()

    @classmethod
    def for_seed(cls, seed=None):
        return cls(secret_values([seed, LIVE_DATA]))

    def __call__(self, text):
        text = str(text or '')
        for value in self.values:
            text = text.replace(value, REDACTED)
        return self.pattern.sub(REDACTED, text)
