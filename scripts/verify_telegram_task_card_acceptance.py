#!/usr/bin/env python3
"""Produce a redacted P7-03 acceptance report from an owner's live store.

This script does not contact Telegram, read connection secrets, or print task
content.  The owner performs the paired-account observations described in
docs/validation/p7-03-telegram-task-card-continuity.md, then supplies the two
explicit observation flags below.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

from personal_agent.quickstart_store import QuickStore
from telegram_task_card_acceptance import report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path.home()/'.local/share/agentos',
                        help='AgentOS data directory; it is read only (default: ~/.local/share/agentos).')
    parser.add_argument('--web-confirmed', action='store_true',
                        help='Owner observed the shared Telegram and web history.')
    parser.add_argument('--restart-confirmed', action='store_true',
                        help='Owner observed the same paired flow after a restart.')
    args = parser.parse_args(argv)
    data_dir=args.data_dir.expanduser().resolve()
    database = data_dir / 'private' / 'quickstart.db'
    if not database.is_file():
        parser.error('AgentOS quickstart database was not found in --data-dir.')
    result = report(QuickStore(data_dir), args.web_confirmed or None, args.restart_confirmed or None)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
