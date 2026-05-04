#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "agentos-welcome-first-vm-proof-pack.v1"
LAYOUT_DIRNAME = "welcome-first-vm-proof-packs"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "remastered-vm-boot-checklist-v1.md",
    ROOT_DIR / "docs" / "reference" / "vm-first-screen-evidence-export-v1.md",
    ROOT_DIR / "docs" / "reference" / "boot-target-activation-wiring-v1.md",
]
EXPECTED_PATH = "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    return json.loads(target.read_text(encoding="utf-8"))


def build_markdown(*, label: str, manifest: dict, copied_references: list[str]) -> str:
    summary = manifest["summary"]
    artifacts = manifest["artifacts"]
    lines = [
        "# AgentOS Welcome-First VM Proof Pack",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Artifact chain",
        "",
        f"1. Remastered VM boot checklist: `{artifacts['remastered_vm_boot_checklist_json']}`",
        f"2. VM first-screen evidence: `{artifacts['vm_first_screen_evidence_json']}`",
        f"3. Boot target activation: `{artifacts['boot_target_activation_json']}`",
        "",
        "## Proof summary",
        "",
        f"- Welcome-first proven: `{summary['welcome_first_proven']}`",
        f"- Default target label ok: `{summary['default_target_label_ok']}`",
        f"- Checklist ok: `{summary['checklist_ok']}`",
        f"- Expected path: `{summary['expected_path']}`",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_welcome_first_vm_proof_pack(*, report_dir: str, snapshot_label: str, checklist_manifest: str, vm_first_screen_evidence: str, boot_target_activation: str) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"welcome-first-vm-proof-pack-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    checklist_payload = _load_json(checklist_manifest)
    first_screen_payload = _load_json(vm_first_screen_evidence)
    target_payload = _load_json(boot_target_activation)

    references_dir = run_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            dest = references_dir / ref.name
            shutil.copyfile(ref, dest)
            copied_references.append(str(dest))

    summary = {
        "ok": False,
        "welcome_first_proven": first_screen_payload.get("evidence_status") == "ready" and first_screen_payload.get("expected_first_path") == EXPECTED_PATH,
        "default_target_label_ok": target_payload.get("default_boot_target_label") == "Continue to AgentOS" and target_payload.get("activation_status") == "ready",
        "checklist_ok": (checklist_payload.get("summary") or {}).get("ok") is True,
        "expected_path": EXPECTED_PATH,
        "reference_count": len(copied_references),
    }
    summary["ok"] = summary["welcome_first_proven"] and summary["default_target_label_ok"] and summary["checklist_ok"]

    markdown = run_dir / "welcome-first-vm-proof-pack.md"
    manifest = run_dir / "welcome-first-vm-proof-pack.json"
    latest = root / "latest-welcome-first-vm-proof-pack.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": snapshot_label or "current",
        "run_root": str(root),
        "run_dir": str(run_dir),
        "references": copied_references,
        "artifacts": {
            "welcome_first_vm_proof_pack_markdown": str(markdown),
            "welcome_first_vm_proof_pack_json": str(manifest),
            "latest_welcome_first_vm_proof_pack_json": str(latest),
            "remastered_vm_boot_checklist_json": str(checklist_manifest),
            "vm_first_screen_evidence_json": str(vm_first_screen_evidence),
            "boot_target_activation_json": str(boot_target_activation),
        },
        "components": {
            "remastered_vm_boot_checklist": checklist_payload,
            "vm_first_screen_evidence": first_screen_payload,
            "boot_target_activation": target_payload,
        },
        "summary": summary,
    }
    markdown.write_text(build_markdown(label=snapshot_label or 'current', manifest=payload, copied_references=copied_references), encoding='utf-8')
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    latest.write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    return payload


def validate_welcome_first_vm_proof_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    summary = payload.get('summary') or {}
    for key in ('welcome_first_proven', 'default_target_label_ok', 'checklist_ok', 'ok'):
        if summary.get(key) is not True:
            errors.append(f'summary.{key} must be true')
    if summary.get('expected_path') != EXPECTED_PATH:
        errors.append(f'summary.expected_path must be {EXPECTED_PATH}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Export an AgentOS welcome-first VM proof pack')
    parser.add_argument('--report-dir', default='./workspaces/default/artifacts')
    parser.add_argument('--snapshot-label', default='current')
    parser.add_argument('--checklist-manifest', default='')
    parser.add_argument('--vm-first-screen-evidence', default='')
    parser.add_argument('--boot-target-activation', default='')
    parser.add_argument('--output', default='')
    parser.add_argument('--validate', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        errors = validate_welcome_first_vm_proof_pack(payload)
        result = {'ok': not errors, 'errors': errors, 'schema_version': payload.get('schema_version', '')}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print('PASS' if result['ok'] else 'FAIL')
            for error in errors:
                print(f'- {error}')
        return 0 if result['ok'] else 1

    payload = build_welcome_first_vm_proof_pack(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        checklist_manifest=args.checklist_manifest,
        vm_first_screen_evidence=args.vm_first_screen_evidence,
        boot_target_activation=args.boot_target_activation,
    )
    errors = validate_welcome_first_vm_proof_pack(payload)
    payload['summary']['ok'] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + '\n', encoding='utf-8')
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Proof pack: {payload['artifacts']['welcome_first_vm_proof_pack_markdown']}")
        print(f"Manifest: {payload['artifacts']['welcome_first_vm_proof_pack_json']}")
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
