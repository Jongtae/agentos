#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.appliance_platform import RECOVERY_MODE_SCHEMA_VERSION, build_recovery_mode_contract


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != RECOVERY_MODE_SCHEMA_VERSION:
        errors.append(f'schema_version must be {RECOVERY_MODE_SCHEMA_VERSION}')
    if payload.get('recovery_label') != 'Recovery':
        errors.append('recovery_label must be Recovery')
    if payload.get('default_rejoin_path') != ['Recovery', 'Return to AgentOS', 'ai>']:
        errors.append('default_rejoin_path must be Recovery -> Return to AgentOS -> ai>')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Export AgentOS recovery mode contract')
    parser.add_argument('--output', default='')
    parser.add_argument('--validate', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        errors = validate_payload(payload)
        result = {'ok': not errors, 'errors': errors, 'schema_version': payload.get('schema_version', '')}
        print(json.dumps(result, ensure_ascii=True) if args.json else ('PASS' if result['ok'] else 'FAIL'))
        if not args.json and errors:
            for error in errors:
                print(f'- {error}')
        return 0 if result['ok'] else 1
    payload = build_recovery_mode_contract()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
