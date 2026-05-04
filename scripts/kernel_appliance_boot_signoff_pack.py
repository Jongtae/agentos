#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 'agentos-appliance-boot-signoff-pack.v1'
LAYOUT_DIRNAME = 'appliance-boot-signoff-packs'
REFERENCE_FILES = [
    ROOT_DIR / 'docs' / 'reference' / 'welcome-first-vm-proof-pack-v1.md',
    ROOT_DIR / 'docs' / 'reference' / 'installed-reboot-slot-proof-v1.md',
    ROOT_DIR / 'docs' / 'reference' / 'recovery-reentry-after-slot-switch-v1.md',
]
EXPECTED_PRIMARY_PATH = 'Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>'
EXPECTED_INSTALLED_PATH = 'Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>'
EXPECTED_RECOVERY_PATH = 'AgentOS Recovery -> Return to AgentOS -> ai>'


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
        '# AgentOS Appliance Boot Signoff Pack',
        '',
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        '',
        '## Artifact chain',
        '',
        f"1. Welcome-first VM proof pack: `{artifacts['welcome_first_vm_proof_pack_json']}`",
        f"2. Installed reboot slot proof: `{artifacts['installed_reboot_slot_proof_json']}`",
        f"3. Recovery re-entry after slot switch: `{artifacts['recovery_reentry_after_slot_switch_json']}`",
        '',
        '## Signoff summary',
        '',
        f"- Welcome-first path ok: `{summary['welcome_first_ok']}`",
        f"- Installed reboot path ok: `{summary['installed_reboot_ok']}`",
        f"- Recovery re-entry path ok: `{summary['recovery_reentry_ok']}`",
        f"- Signoff ready: `{summary['ok']}`",
        f"- Expected primary path: `{summary['expected_primary_path']}`",
        f"- Expected installed path: `{summary['expected_installed_path']}`",
        f"- Expected recovery path: `{summary['expected_recovery_path']}`",
        '',
        '## Included references',
        '',
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return '\n'.join(lines) + '\n'


def build_appliance_boot_signoff_pack(*, report_dir: str, snapshot_label: str, welcome_first_vm_proof_pack: str, installed_reboot_slot_proof: str, recovery_reentry_after_slot_switch: str) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"appliance-boot-signoff-pack-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    welcome_payload = _load_json(welcome_first_vm_proof_pack)
    reboot_payload = _load_json(installed_reboot_slot_proof)
    recovery_payload = _load_json(recovery_reentry_after_slot_switch)

    references_dir = run_dir / 'references'
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            dest = references_dir / ref.name
            shutil.copyfile(ref, dest)
            copied_references.append(str(dest))

    welcome_summary = welcome_payload.get('summary') or {}
    reboot_summary = reboot_payload.get('summary') or {}
    recovery_summary = recovery_payload.get('summary') or {}
    summary = {
        'ok': False,
        'welcome_first_ok': bool(welcome_summary.get('ok') is True and welcome_summary.get('expected_path') == EXPECTED_PRIMARY_PATH),
        'installed_reboot_ok': bool(reboot_summary.get('ok') is True and reboot_summary.get('expected_installed_path') == EXPECTED_INSTALLED_PATH),
        'recovery_reentry_ok': bool(recovery_summary.get('ok') is True and recovery_summary.get('expected_return_path') == EXPECTED_RECOVERY_PATH),
        'expected_primary_path': EXPECTED_PRIMARY_PATH,
        'expected_installed_path': EXPECTED_INSTALLED_PATH,
        'expected_recovery_path': EXPECTED_RECOVERY_PATH,
        'reference_count': len(copied_references),
    }
    summary['ok'] = summary['welcome_first_ok'] and summary['installed_reboot_ok'] and summary['recovery_reentry_ok']

    markdown = run_dir / 'appliance-boot-signoff-pack.md'
    manifest = run_dir / 'appliance-boot-signoff-pack.json'
    latest = root / 'latest-appliance-boot-signoff-pack.json'
    payload = {
        'schema_version': SCHEMA_VERSION,
        'generated_at_utc': _utc_now(),
        'run_label': snapshot_label or 'current',
        'run_root': str(root),
        'run_dir': str(run_dir),
        'references': copied_references,
        'artifacts': {
            'appliance_boot_signoff_pack_markdown': str(markdown),
            'appliance_boot_signoff_pack_json': str(manifest),
            'latest_appliance_boot_signoff_pack_json': str(latest),
            'welcome_first_vm_proof_pack_json': str(welcome_first_vm_proof_pack),
            'installed_reboot_slot_proof_json': str(installed_reboot_slot_proof),
            'recovery_reentry_after_slot_switch_json': str(recovery_reentry_after_slot_switch),
        },
        'components': {
            'welcome_first_vm_proof_pack': welcome_payload,
            'installed_reboot_slot_proof': reboot_payload,
            'recovery_reentry_after_slot_switch': recovery_payload,
        },
        'summary': summary,
    }
    markdown.write_text(build_markdown(label=snapshot_label or 'current', manifest=payload, copied_references=copied_references), encoding='utf-8')
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    latest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    return payload


def validate_appliance_boot_signoff_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    summary = payload.get('summary') or {}
    for key in ('welcome_first_ok', 'installed_reboot_ok', 'recovery_reentry_ok', 'ok'):
        if summary.get(key) is not True:
            errors.append(f'summary.{key} must be true')
    if summary.get('expected_primary_path') != EXPECTED_PRIMARY_PATH:
        errors.append(f'summary.expected_primary_path must be {EXPECTED_PRIMARY_PATH}')
    if summary.get('expected_installed_path') != EXPECTED_INSTALLED_PATH:
        errors.append(f'summary.expected_installed_path must be {EXPECTED_INSTALLED_PATH}')
    if summary.get('expected_recovery_path') != EXPECTED_RECOVERY_PATH:
        errors.append(f'summary.expected_recovery_path must be {EXPECTED_RECOVERY_PATH}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Export AgentOS appliance boot signoff pack')
    parser.add_argument('--report-dir', default='./workspaces/default/artifacts')
    parser.add_argument('--snapshot-label', default='current')
    parser.add_argument('--welcome-first-vm-proof-pack', default='')
    parser.add_argument('--installed-reboot-slot-proof', default='')
    parser.add_argument('--recovery-reentry-after-slot-switch', default='')
    parser.add_argument('--output', default='')
    parser.add_argument('--validate', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        errors = validate_appliance_boot_signoff_pack(payload)
        result = {'ok': not errors, 'errors': errors, 'schema_version': payload.get('schema_version', '')}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print('PASS' if result['ok'] else 'FAIL')
            for error in errors:
                print(f'- {error}')
        return 0 if result['ok'] else 1

    payload = build_appliance_boot_signoff_pack(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        welcome_first_vm_proof_pack=args.welcome_first_vm_proof_pack,
        installed_reboot_slot_proof=args.installed_reboot_slot_proof,
        recovery_reentry_after_slot_switch=args.recovery_reentry_after_slot_switch,
    )
    errors = validate_appliance_boot_signoff_pack(payload)
    payload['summary']['ok'] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Signoff pack: {payload['artifacts']['appliance_boot_signoff_pack_markdown']}")
        print(f"Manifest: {payload['artifacts']['appliance_boot_signoff_pack_json']}")
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
