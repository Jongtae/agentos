"""Where the evaluation loop keeps its local, never-committed state."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / 'src'
BUNDLED_SCENARIOS = REPO / 'evals' / 'scenarios'
SANDBOX_SITE = Path(__file__).resolve().parent / 'sandbox_site'

#: The owner's live AgentOS data folder and port.  Sandboxes never use either.
LIVE_DATA = Path.home() / '.local' / 'share' / 'agentos'
LIVE_PORTS = frozenset({8787, 8788})


def eval_home(environ=None):
    """Root of the local evaluation state: seeds, sandboxes, logs, reports, budget."""
    environ = os.environ if environ is None else environ
    return Path(environ.get('AGENTOS_EVAL_HOME') or Path.home() / '.local' / 'share' / 'agentos-evals').expanduser()


def local_scenario_dirs(environ=None):
    """Owner-local scenario folders read in addition to the bundled synthetic set."""
    environ = os.environ if environ is None else environ
    dirs = [eval_home(environ) / 'scenarios']
    extra = environ.get('AGENTOS_EVAL_SCENARIOS', '')
    dirs.extend(Path(item).expanduser() for item in extra.split(os.pathsep) if item)
    return dirs
