#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.appliance_platform import build_slot_state_summary

SCHEMA_VERSION = 'agentos-image-update-prototype.v1'


def _state_root() -> Path:
    return Path(os.environ.get('AGENTOS_STATE_ROOT', '/var/lib/agentos'))


def _slot_metadata_file(state_root: Path) -> Path:
    return Path(os.environ.get('AGENTOS_SLOT_METADATA_FILE', state_root / 'slots' / 'slot-state.env'))


def _next_boot_file(state_root: Path) -> Path:
    return Path(os.environ.get('AGENTOS_NEXT_BOOT_FILE', state_root / 'slots' / 'next-boot.env'))


def _payload_file(state_root: Path, target_slot: str) -> Path:
    return Path(os.environ.get('AGENTOS_UPDATE_PAYLOAD_FILE', state_root / 'slots' / target_slot / 'update-payload.json'))


def build_update_payload(*, version: str, channel: str, dry_run: bool, target_slot: str = '') -> dict:
    slot_state = build_slot_state_summary()
    state_root = _state_root()
    active_slot = str(slot_state.get('active_slot', 'A'))
    inactive_slot = str(slot_state.get('inactive_slot', 'B'))
    rollback_slot = str(slot_state.get('rollback_slot', active_slot))
    target_slot = (target_slot or str(slot_state.get('inactive_slot', inactive_slot))).strip() or inactive_slot
    payload_file = _payload_file(state_root, target_slot)
    next_boot_file = _next_boot_file(state_root)
    digest_source = f'{version}:{channel}:{active_slot}:{target_slot}'
    payload_digest = hashlib.sha256(digest_source.encode('utf-8')).hexdigest()
    return {
        'schema_version': SCHEMA_VERSION,
        'stage_status': 'dry_run' if dry_run else 'staged',
        'state_root': str(state_root),
        'active_slot': active_slot,
        'inactive_slot': inactive_slot,
        'rollback_slot': rollback_slot,
        'target_slot': target_slot,
        'next_slot': target_slot,
        'version': version,
        'channel': channel,
        'payload_digest': payload_digest,
        'payload_file': str(payload_file),
        'next_boot_file': str(next_boot_file),
        'bootable_on_reboot': True,
        'written_by': 'kernel_image_update_prototype.py',
    }


def stage_update(payload: dict) -> dict:
    state_root = Path(payload['state_root'])
    payload_file = Path(payload['payload_file'])
    next_boot_file = Path(payload['next_boot_file'])
    metadata_file = _slot_metadata_file(state_root)
    payload_file.parent.mkdir(parents=True, exist_ok=True)
    next_boot_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    payload_file.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    next_boot_file.write_text(
        '\n'.join([
            'schema_version=agentos-next-boot.v1',
            f"bootable_slot={payload['target_slot']}",
            f"staged_from_slot={payload['active_slot']}",
            f"rollback_slot={payload['rollback_slot']}",
            f"payload_file={payload['payload_file']}",
            f"payload_version={payload['version']}",
            f"payload_channel={payload['channel']}",
            f"payload_digest={payload['payload_digest']}",
            'written_by=kernel_image_update_prototype.py',
        ])
        + '\n',
        encoding='utf-8',
    )

    existing: dict[str, str] = {}
    if metadata_file.exists():
        for line in metadata_file.read_text(encoding='utf-8').splitlines():
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            existing[key.strip()] = value.strip()
    existing.setdefault('schema_version', 'agentos-slot-metadata.v1')
    existing['active_slot'] = payload['active_slot']
    existing['inactive_slot'] = payload['inactive_slot']
    existing['rollback_slot'] = payload['rollback_slot']
    existing['next_slot'] = payload['target_slot']
    existing['health_state'] = 'staged_update_pending'
    existing['written_by'] = 'kernel_image_update_prototype.py'
    metadata_file.write_text(''.join(f'{key}={value}\n' for key, value in existing.items()), encoding='utf-8')

    result = dict(payload)
    result['metadata_file'] = str(metadata_file)
    result['metadata_updated'] = True
    result['next_boot_written'] = True
    result['payload_written'] = True
    return result


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    if payload.get('active_slot') == payload.get('target_slot'):
        errors.append('target_slot must differ from active_slot')
    if not payload.get('payload_digest'):
        errors.append('payload_digest must be non-empty')
    if not payload.get('payload_file'):
        errors.append('payload_file must be non-empty')
    if not payload.get('next_boot_file'):
        errors.append('next_boot_file must be non-empty')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Stage an AgentOS inactive-slot image update prototype')
    parser.add_argument('--version', default='development')
    parser.add_argument('--channel', default='preview')
    parser.add_argument('--target-slot', default='')
    parser.add_argument('--dry-run', action='store_true')
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

    payload = build_update_payload(version=args.version, channel=args.channel, dry_run=args.dry_run, target_slot=args.target_slot)
    errors = validate_payload(payload)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    result = payload if args.dry_run else stage_update(payload)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json or not args.output:
        print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
