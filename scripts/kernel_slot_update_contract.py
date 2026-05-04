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

from kernel.appliance_platform import SLOT_UPDATE_SCHEMA_VERSION, build_slot_update_contract


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SLOT_UPDATE_SCHEMA_VERSION:
        errors.append(f'schema_version must be {SLOT_UPDATE_SCHEMA_VERSION}')
    if payload.get('update_model') != 'image_based_ab_updates':
        errors.append('update_model must be image_based_ab_updates')
    if payload.get('active_slot') == payload.get('inactive_slot'):
        errors.append('active_slot and inactive_slot must differ')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Export AgentOS slot update contract')
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
    payload = build_slot_update_contract()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
