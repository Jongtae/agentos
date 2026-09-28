"""Daily spend cap for the judge model (default USD 10 a day).

The ledger is a small JSON file in the eval home, shared by every concurrent
scorer through an exclusive file lock.  A judge call first *reserves* its
worst-case cost (estimated input tokens plus the output-token ceiling); the
call is refused when the reservation would cross the cap.  After the call the
reservation is *settled* to the observed token usage; a call whose usage is
unknown keeps the worst-case charge.  Prices are per million tokens and
configurable, because provider prices change and are not read from anywhere.
"""
import datetime
import fcntl
import json
import os
import time
from pathlib import Path

DEFAULT_CAP_USD = 10.0
#: Conservative defaults (USD per 1M tokens); override with the CLI or environment.
DEFAULT_PRICE_IN = 2.0
DEFAULT_PRICE_OUT = 8.0


def estimate_tokens(text):
    """A deliberately high token estimate for mixed Korean/English text (no tokenizer needed)."""
    return max(1, len(text) // 2)


class JudgeBudget:
    def __init__(self, path, cap_usd=DEFAULT_CAP_USD, price_in=DEFAULT_PRICE_IN, price_out=DEFAULT_PRICE_OUT,
                 clock=time.time):
        if cap_usd < 0 or price_in < 0 or price_out < 0:
            raise ValueError('budget and prices must not be negative')
        self.path = Path(path)
        self.cap = float(cap_usd)
        self.price_in = float(price_in)
        self.price_out = float(price_out)
        self.clock = clock

    @classmethod
    def from_environ(cls, path, environ=None, **overrides):
        environ = os.environ if environ is None else environ
        values = {'cap_usd': float(environ.get('AGENTOS_EVAL_JUDGE_CAP_USD', DEFAULT_CAP_USD)),
                  'price_in': float(environ.get('AGENTOS_EVAL_JUDGE_PRICE_IN', DEFAULT_PRICE_IN)),
                  'price_out': float(environ.get('AGENTOS_EVAL_JUDGE_PRICE_OUT', DEFAULT_PRICE_OUT))}
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls(path, **values)

    def cost(self, tokens_in, tokens_out):
        return (tokens_in * self.price_in + tokens_out * self.price_out) / 1_000_000

    def today(self):
        return datetime.datetime.fromtimestamp(self.clock()).strftime('%Y-%m-%d')

    def _update(self, change):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with os.fdopen(os.dup(fd), 'r+') as handle:
                try:
                    ledger = json.loads(handle.read() or '{}')
                except ValueError:
                    ledger = {}
                ledger = ledger if isinstance(ledger, dict) else {}
                day = ledger.setdefault(self.today(), {'calls': 0, 'refused': 0, 'input_tokens': 0,
                                                       'output_tokens': 0, 'usd': 0.0})
                result = change(day)
                # Keep a month of history; older days are not needed for the cap.
                for key in sorted(ledger)[:-31]:
                    ledger.pop(key, None)
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(ledger, indent=1, sort_keys=True))
                return result
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def reserve(self, tokens_in, max_tokens_out):
        """Reserve a worst-case charge; returns the reserved USD, or None when the cap refuses it."""
        charge = self.cost(tokens_in, max_tokens_out)

        def change(day):
            if day['usd'] + charge > self.cap:
                day['refused'] += 1
                return None
            day['usd'] = round(day['usd'] + charge, 6)
            day['calls'] += 1
            return charge
        return self._update(change)

    def settle(self, reserved, tokens_in=None, tokens_out=None):
        """Replace a reservation by the observed usage; unknown usage keeps the reserved charge."""
        if reserved is None or tokens_in is None or tokens_out is None:
            return reserved
        actual = self.cost(tokens_in, tokens_out)

        def change(day):
            day['usd'] = round(max(0.0, day['usd'] - reserved + actual), 6)
            day['input_tokens'] += int(tokens_in)
            day['output_tokens'] += int(tokens_out)
            return actual
        return self._update(change)

    def status(self):
        def read(day):
            return dict(day)
        day = self._update(read)
        return {**day, 'date': self.today(), 'cap_usd': self.cap, 'remaining_usd': round(max(0.0, self.cap - day['usd']), 6)}
