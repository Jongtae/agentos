#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 'agentos-recovery-reentry-after-slot-switch.v1'
LAYOUT_DIRNAME = 'recovery-reentry-after-slot-switch'
REFERENCE_FILES = [
    ROOT_DIR / 'docs' / 'reference' / 'installed-reboot-slot-proof-v1.md',
    ROOT_DIR / 'docs' / 'reference' / 'rollback-and-recovery-slot-logic-v1.md',
    ROOT_DIR / 'docs' / 'reference' / 'agentos-recovery-path-contract-v1.md',
]
EXPECTED_RETURN_PATH = 'AgentOS Recovery -> Return to AgentOS -> ai>'


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _load_json(path: str) -> dict:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding='utf-8'))


def build_markdown(*, label: str, manifest: dict, copied_references: list[str]) -> str:
    summary = manifest['summary']
    artifacts = manifest['artifacts']
    lines = [
        '# AgentOS Recovery Re-entry After Slot Switch',
        '',
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        '',
        '## Artifact chain',
        '',
        f"1. Installed reboot slot proof: `{artifacts['installed_reboot_slot_proof_json']}`",
        f"2. Slot recovery logic: `{artifacts['slot_recovery_logic_json']}`",
        '',
        '## Proof summary',
        '',
        f"- Reboot proof ok: `{summary['reboot_proof_ok']}`",
        f"- Recovery required: `{summary['recovery_required']}`",
        f"- Recovery path ok: `{summary['recovery_path_ok']}`",
        f"- Return action ok: `{summary['return_action_ok']}`",
        f"- Expected return path: `{summary['expected_return_path']}`",
        '',
        '## Included references',
        '',
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return '\n'.join(lines) + '\n'


def build_recovery_reentry_after_slot_switch(*, report_dir: str, snapshot_label: str, installed_reboot_slot_proof: str, slot_recovery_logic: str) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"recovery-reentry-after-slot-switch-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    reboot_payload = _load_json(installed_reboot_slot_proof)
    recovery_payload = _load_json(slot_recovery_logic)

    references_dir = run_dir / 'references'
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            dest = references_dir / ref.name
            shutil.copyfile(ref, dest)
            copied_references.append(str(dest))

    summary = {
        'ok': False,
        'reboot_proof_ok': bool((reboot_payload.get('summary') or {}).get('ok') is True),
        'recovery_required': bool(recovery_payload.get('recovery_required', (recovery_payload.get('summary') or {}).get('recovery_required', False))),
        'recovery_path_ok': (recovery_payload.get('return_action') or (recovery_payload.get('summary') or {}).get('return_action', '')) == 'return_to_agentos' or (recovery_payload.get('return_action') or '') == 'return_to_agentos',
        'return_action_ok': (recovery_payload.get('return_path') or (recovery_payload.get('summary') or {}).get('return_path', '')) == EXPECTED_RETURN_PATH,
        'expected_return_path': EXPECTED_RETURN_PATH,
        'reference_count': len(copied_references),
    }
    summary['ok'] = all([
        summary['reboot_proof_ok'],
        summary['recovery_required'],
        summary['recovery_path_ok'],
        summary['return_action_ok'],
    ])

    markdown = run_dir / 'recovery-reentry-after-slot-switch.md'
    manifest = run_dir / 'recovery-reentry-after-slot-switch.json'
    latest = root / 'latest-recovery-reentry-after-slot-switch.json'
    payload = {
        'schema_version': SCHEMA_VERSION,
        'generated_at_utc': _utc_now(),
        'run_label': snapshot_label or 'current',
        'run_root': str(root),
        'run_dir': str(run_dir),
        'references': copied_references,
        'artifacts': {
            'recovery_reentry_after_slot_switch_markdown': str(markdown),
            'recovery_reentry_after_slot_switch_json': str(manifest),
            'latest_recovery_reentry_after_slot_switch_json': str(latest),
            'installed_reboot_slot_proof_json': str(installed_reboot_slot_proof),
            'slot_recovery_logic_json': str(slot_recovery_logic),
        },
        'components': {
            'installed_reboot_slot_proof': reboot_payload,
            'slot_recovery_logic': recovery_payload,
        },
        'summary': summary,
    }
    markdown.write_text(build_markdown(label=snapshot_label or 'current', manifest=payload, copied_references=copied_references), encoding='utf-8')
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    latest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    return payload


def validate_recovery_reentry_after_slot_switch(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    summary = payload.get('summary') or {}
    for key in ('reboot_proof_ok', 'recovery_required', 'recovery_path_ok', 'return_action_ok', 'ok'):
        if summary.get(key) is not True:
            errors.append(f'summary.{key} must be true')
    if summary.get('expected_return_path') != EXPECTED_RETURN_PATH:
        errors.append(f'summary.expected_return_path must be {EXPECTED_RETURN_PATH}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Export AgentOS recovery re-entry after slot switch proof')
    parser.add_argument('--report-dir', default='./workspaces/default/artifacts')
    parser.add_argument('--snapshot-label', default='current')
    parser.add_argument('--installed-reboot-slot-proof', default='')
    parser.add_argument('--slot-recovery-logic', default='')
    parser.add_argument('--output', default='')
    parser.add_argument('--validate', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        errors = validate_recovery_reentry_after_slot_switch(payload)
        result = {'ok': not errors, 'errors': errors, 'schema_version': payload.get('schema_version', '')}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print('PASS' if result['ok'] else 'FAIL')
            for error in errors:
                print(f'- {error}')
        return 0 if result['ok'] else 1

    payload = build_recovery_reentry_after_slot_switch(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        installed_reboot_slot_proof=args.installed_reboot_slot_proof,
        slot_recovery_logic=args.slot_recovery_logic,
    )
    errors = validate_recovery_reentry_after_slot_switch(payload)
    payload['summary']['ok'] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Proof: {payload['artifacts']['recovery_reentry_after_slot_switch_markdown']}")
        print(f"Manifest: {payload['artifacts']['recovery_reentry_after_slot_switch_json']}")
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
