#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_installed_slot_switch_evidence import build_switch_evidence
from kernel_next_boot_target_integration import SCHEMA_VERSION as NEXT_BOOT_SCHEMA
from kernel_next_boot_target_integration import validate_payload as validate_next_boot_payload
from verify_boot_target_activation import BOOT_TARGET_CONTRACT
from verify_vm_first_screen_evidence import EVIDENCE_CONTRACT as FIRST_SCREEN_CONTRACT

SCHEMA_VERSION = "agentos-remastered-vm-boot-checklist.v1"
LAYOUT_DIRNAME = "vm-boot-checklists"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "remastered-boot-flow-proof-v1.md",
    ROOT_DIR / "docs" / "reference" / "boot-target-activation-wiring-v1.md",
    ROOT_DIR / "docs" / "reference" / "vm-first-screen-evidence-export-v1.md",
    ROOT_DIR / "docs" / "reference" / "next-boot-target-integration-v1.md",
    ROOT_DIR / "docs" / "reference" / "installed-slot-switch-evidence-v1.md",
]


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


def build_checklist_markdown(*, label: str, manifest: dict, copied_references: list[str]) -> str:
    summary = manifest["summary"]
    artifacts = manifest["artifacts"]
    lines = [
        "# AgentOS Remastered VM Boot Checklist",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Artifact chain",
        "",
        f"1. Boot flow proof: `{artifacts['boot_flow_proof_json']}`",
        f"2. Boot target activation: `{artifacts['boot_target_activation_json']}`",
        f"3. VM first-screen evidence: `{artifacts['vm_first_screen_evidence_json']}`",
        f"4. Next-boot target integration: `{artifacts['next_boot_target_json']}`",
        f"5. Installed slot switch evidence: `{artifacts['installed_slot_switch_evidence_json']}`",
        "",
        "## Checklist",
        "",
        f"- Boot flow proof ready: `{summary['boot_flow_ready']}`",
        f"- Boot target activation ready: `{summary['boot_target_ready']}`",
        f"- VM first-screen evidence ready: `{summary['first_screen_ready']}`",
        f"- Next-boot target ready: `{summary['next_boot_ready']}`",
        f"- Installed slot switch evidence ready: `{summary['installed_switch_ready']}`",
        "",
        "## Expected product path",
        "",
        "- `Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>`",
        "- `Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>`",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_remastered_vm_boot_checklist(*, report_dir: str, snapshot_label: str, boot_flow_proof: str, boot_target_activation: str, vm_first_screen_evidence: str) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"vm-boot-checklist-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    flow_payload = _load_json(boot_flow_proof)
    target_payload = _load_json(boot_target_activation)
    first_screen_payload = _load_json(vm_first_screen_evidence)
    next_boot_payload = {"schema_version": NEXT_BOOT_SCHEMA, **__import__('kernel.appliance_platform', fromlist=['build_next_boot_target_summary']).build_next_boot_target_summary()}
    installed_switch_payload = build_switch_evidence()

    references_dir = run_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    checklist_path = run_dir / "remastered-vm-boot-checklist.md"
    manifest_path = run_dir / "remastered-vm-boot-checklist.json"
    latest_manifest_path = root / "latest-remastered-vm-boot-checklist.json"

    summary = {
        "ok": False,
        "boot_flow_ready": flow_payload.get("proof_status") == "ready",
        "boot_target_ready": target_payload.get("activation_status") == "ready" and target_payload.get("boot_target_contract") == BOOT_TARGET_CONTRACT,
        "first_screen_ready": first_screen_payload.get("evidence_status") == "ready" and first_screen_payload.get("evidence_contract") == FIRST_SCREEN_CONTRACT,
        "next_boot_ready": not validate_next_boot_payload(next_boot_payload),
        "installed_switch_ready": installed_switch_payload.get("evidence_status") == "ready" and installed_switch_payload.get("switch_confirmed") is True,
        "reference_count": len(copied_references),
    }
    summary["ok"] = all(
        summary[key]
        for key in (
            "boot_flow_ready",
            "boot_target_ready",
            "first_screen_ready",
            "next_boot_ready",
            "installed_switch_ready",
        )
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": snapshot_label or "current",
        "run_root": str(root),
        "run_dir": str(run_dir),
        "references": copied_references,
        "artifacts": {
            "remastered_vm_boot_checklist_markdown": str(checklist_path),
            "remastered_vm_boot_checklist_json": str(manifest_path),
            "latest_remastered_vm_boot_checklist_json": str(latest_manifest_path),
            "boot_flow_proof_json": str(boot_flow_proof),
            "boot_target_activation_json": str(boot_target_activation),
            "vm_first_screen_evidence_json": str(vm_first_screen_evidence),
            "next_boot_target_json": str(run_dir / "next-boot-target.json"),
            "installed_slot_switch_evidence_json": str(run_dir / "installed-slot-switch-evidence.json"),
        },
        "components": {
            "boot_flow_proof": flow_payload,
            "boot_target_activation": target_payload,
            "vm_first_screen_evidence": first_screen_payload,
            "next_boot_target": next_boot_payload,
            "installed_slot_switch_evidence": installed_switch_payload,
        },
        "summary": summary,
    }

    Path(payload["artifacts"]["next_boot_target_json"]).write_text(json.dumps(next_boot_payload, ensure_ascii=True) + "\n", encoding="utf-8")
    Path(payload["artifacts"]["installed_slot_switch_evidence_json"]).write_text(json.dumps(installed_switch_payload, ensure_ascii=True) + "\n", encoding="utf-8")
    checklist_path.write_text(build_checklist_markdown(label=snapshot_label or "current", manifest=payload, copied_references=copied_references), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_remastered_vm_boot_checklist(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary") or {}
    for key in ("boot_flow_ready", "boot_target_ready", "first_screen_ready", "next_boot_ready", "installed_switch_ready"):
        if summary.get(key) is not True:
            errors.append(f"summary.{key} must be true")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    artifacts = payload.get("artifacts") or {}
    for key in (
        "remastered_vm_boot_checklist_markdown",
        "remastered_vm_boot_checklist_json",
        "boot_flow_proof_json",
        "boot_target_activation_json",
        "vm_first_screen_evidence_json",
        "next_boot_target_json",
        "installed_slot_switch_evidence_json",
    ):
        if not artifacts.get(key):
            errors.append(f"artifacts.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS remastered VM boot checklist")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--boot-flow-proof", default="")
    parser.add_argument("--boot-target-activation", default="")
    parser.add_argument("--vm-first-screen-evidence", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_remastered_vm_boot_checklist(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_remastered_vm_boot_checklist(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        boot_flow_proof=args.boot_flow_proof,
        boot_target_activation=args.boot_target_activation,
        vm_first_screen_evidence=args.vm_first_screen_evidence,
    )
    errors = validate_remastered_vm_boot_checklist(payload)
    payload["summary"]["ok"] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Checklist: {payload['artifacts']['remastered_vm_boot_checklist_markdown']}")
        print(f"Manifest: {payload['artifacts']['remastered_vm_boot_checklist_json']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
