#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_VERSION = 'agentos-remastered-boot-flow-proof.v1'


def build_proof(*, iso_root: Path, live_root: Path, boot_patch_report: Path) -> dict:
    report = json.loads(boot_patch_report.read_text(encoding='utf-8')) if boot_patch_report.exists() else {}
    autostart = live_root / 'etc' / 'xdg' / 'autostart' / 'agentos-welcome.desktop'
    bin_root = live_root / 'usr' / 'local' / 'bin'
    proof_path = iso_root / 'agentos' / 'boot-flow-proof.json'
    boot_assets_dir = iso_root / 'agentos' / 'boot-assets'
    ubuntu_installer_disable_report = iso_root / 'agentos' / 'ubuntu-installer-disable-report.json'
    installer_payload: dict = {}
    if ubuntu_installer_disable_report.exists():
        try:
            installer_payload = json.loads(ubuntu_installer_disable_report.read_text(encoding='utf-8'))
        except Exception:
            installer_payload = {}
    payload = {
        'schema_version': SCHEMA_VERSION,
        'iso_root': str(iso_root),
        'live_root': str(live_root),
        'boot_patch_report': str(boot_patch_report),
        'continue_entry_present': bool(report.get('continue_present')),
        'install_entry_present': bool(report.get('install_present')),
        'install_path_available': bool(report.get('install_path_available')),
        'recovery_entry_present': bool(report.get('recovery_present')),
        'installer_hidden_default_path': bool(report.get('installer_hidden_default_path')),
        'default_boot_target_label': report.get('default_boot_target_label', ''),
        'default_boot_target_entry_index': report.get('default_boot_target_entry_index'),
        'default_boot_target_configured': bool(report.get('default_boot_target_configured')),
        'welcome_autostart_included': autostart.exists(),
        'welcome_shell_included': (bin_root / 'agentos-welcome-shell').exists(),
        'recovery_shell_included': (bin_root / 'agentos-recovery-shell').exists(),
        'handoff_helper_included': (bin_root / 'agentos-handoff').exists(),
        'install_helper_included': (bin_root / 'agentos-install-appliance').exists(),
        'state_root_init_included': (bin_root / 'agentos-state-root-init').exists(),
        'installed_boot_helper_included': (bin_root / 'agentos-installed-boot').exists(),
        'slot_metadata_init_included': (bin_root / 'agentos-slot-metadata-init').exists(),
        'boot_assets_included': boot_assets_dir.exists(),
        'ubuntu_installer_masked': bool(installer_payload.get('installer_masked')),
        'agentos_welcome_owns_first_screen': bool(
            installer_payload.get('agentos_welcome_owns_first_screen')
        ),
        'proof_status': 'ready',
        'proof_path': str(proof_path),
    }
    required_flags = [
        'continue_entry_present',
        'install_path_available',
        'recovery_entry_present',
        'installer_hidden_default_path',
        'default_boot_target_configured',
        'welcome_autostart_included',
        'welcome_shell_included',
        'recovery_shell_included',
        'handoff_helper_included',
        'install_helper_included',
        'state_root_init_included',
        'installed_boot_helper_included',
        'slot_metadata_init_included',
        'boot_assets_included',
    ]
    if not all(payload.get(flag) for flag in required_flags):
        payload['proof_status'] = 'incomplete'
    return payload


def validate_proof(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    if payload.get('default_boot_target_label') != 'Continue to AgentOS':
        errors.append('default_boot_target_label must be Continue to AgentOS')
    if payload.get('default_boot_target_entry_index') != 0:
        errors.append('default_boot_target_entry_index must be 0')
    required_true = [
        'continue_entry_present',
        'install_path_available',
        'recovery_entry_present',
        'installer_hidden_default_path',
        'default_boot_target_configured',
        'welcome_autostart_included',
        'welcome_shell_included',
        'recovery_shell_included',
        'handoff_helper_included',
        'install_helper_included',
        'state_root_init_included',
        'installed_boot_helper_included',
        'slot_metadata_init_included',
        'boot_assets_included',
    ]
    for key in required_true:
        if payload.get(key) is not True:
            errors.append(f'{key} must be true')
    if payload.get('proof_status') != 'ready':
        errors.append('proof_status must be ready')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate or validate remastered AgentOS boot flow proof')
    parser.add_argument('--iso-root', default='')
    parser.add_argument('--live-root', default='')
    parser.add_argument('--boot-patch-report', default='')
    parser.add_argument('--output', default='')
    parser.add_argument('--validate', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        errors = validate_proof(payload)
        result = {'ok': not errors, 'errors': errors, 'schema_version': payload.get('schema_version', '')}
        print(json.dumps(result, ensure_ascii=True) if args.json else ('PASS' if result['ok'] else 'FAIL'))
        if not args.json and errors:
            for error in errors:
                print(f'- {error}')
        return 0 if result['ok'] else 1
    payload = build_proof(
        iso_root=Path(args.iso_root).resolve(),
        live_root=Path(args.live_root).resolve(),
        boot_patch_report=Path(args.boot_patch_report).resolve(),
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
