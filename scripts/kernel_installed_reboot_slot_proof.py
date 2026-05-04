#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "agentos-installed-reboot-slot-proof.v1"
LAYOUT_DIRNAME = "installed-reboot-slot-proofs"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "next-boot-target-integration-v1.md",
    ROOT_DIR / "docs" / "reference" / "installed-slot-switch-evidence-v1.md",
    ROOT_DIR / "docs" / "reference" / "installed-appliance-boot-identity-v1.md",
]
EXPECTED_INSTALLED_PATH = "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>"


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
        "# AgentOS Installed Reboot Slot Proof",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Artifact chain",
        "",
        f"1. Next-boot target integration: `{artifacts['next_boot_target_json']}`",
        f"2. Installed slot switch evidence: `{artifacts['installed_slot_switch_evidence_json']}`",
        "",
        "## Proof summary",
        "",
        f"- Planned slot matches observed slot: `{summary['planned_matches_observed']}`",
        f"- Reboot proof ready: `{summary['reboot_proof_ready']}`",
        f"- Installed path ok: `{summary['installed_path_ok']}`",
        f"- Switch confirmed: `{summary['switch_confirmed']}`",
        f"- Expected installed path: `{summary['expected_installed_path']}`",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_installed_reboot_slot_proof(*, report_dir: str, snapshot_label: str, next_boot_target: str, installed_slot_switch_evidence: str) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"installed-reboot-slot-proof-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    next_boot_payload = _load_json(next_boot_target)
    switch_payload = _load_json(installed_slot_switch_evidence)

    references_dir = run_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            dest = references_dir / ref.name
            shutil.copyfile(ref, dest)
            copied_references.append(str(dest))

    planned_slot = next_boot_payload.get("target_slot") or (next_boot_payload.get("summary") or {}).get("target_slot", "")
    observed_slot = switch_payload.get("observed_slot") or (switch_payload.get("summary") or {}).get("observed_slot", "")
    installed_path = switch_payload.get("identity_path") or (switch_payload.get("summary") or {}).get("identity_path", "")
    switch_confirmed = bool(switch_payload.get("switch_confirmed") or (switch_payload.get("summary") or {}).get("switch_confirmed", False))
    summary = {
        "ok": False,
        "planned_slot": planned_slot,
        "observed_slot": observed_slot,
        "planned_matches_observed": bool(planned_slot and observed_slot and planned_slot == observed_slot),
        "reboot_proof_ready": next_boot_payload.get("schema_version") == "agentos-next-boot-target-integration.v1",
        "installed_path_ok": installed_path == EXPECTED_INSTALLED_PATH,
        "switch_confirmed": switch_confirmed,
        "expected_installed_path": EXPECTED_INSTALLED_PATH,
        "reference_count": len(copied_references),
    }
    summary["ok"] = all(
        [
            summary["planned_matches_observed"],
            summary["reboot_proof_ready"],
            summary["installed_path_ok"],
            summary["switch_confirmed"],
        ]
    )

    markdown = run_dir / "installed-reboot-slot-proof.md"
    manifest = run_dir / "installed-reboot-slot-proof.json"
    latest = root / "latest-installed-reboot-slot-proof.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": snapshot_label or "current",
        "run_root": str(root),
        "run_dir": str(run_dir),
        "references": copied_references,
        "artifacts": {
            "installed_reboot_slot_proof_markdown": str(markdown),
            "installed_reboot_slot_proof_json": str(manifest),
            "latest_installed_reboot_slot_proof_json": str(latest),
            "next_boot_target_json": str(next_boot_target),
            "installed_slot_switch_evidence_json": str(installed_slot_switch_evidence),
        },
        "components": {
            "next_boot_target": next_boot_payload,
            "installed_slot_switch_evidence": switch_payload,
        },
        "summary": summary,
    }
    markdown.write_text(build_markdown(label=snapshot_label or "current", manifest=payload, copied_references=copied_references), encoding="utf-8")
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_installed_reboot_slot_proof(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary") or {}
    for key in ("planned_matches_observed", "reboot_proof_ready", "installed_path_ok", "switch_confirmed", "ok"):
        if summary.get(key) is not True:
            errors.append(f"summary.{key} must be true")
    if summary.get("expected_installed_path") != EXPECTED_INSTALLED_PATH:
        errors.append(f"summary.expected_installed_path must be {EXPECTED_INSTALLED_PATH}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS installed reboot slot proof")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--next-boot-target", default="")
    parser.add_argument("--installed-slot-switch-evidence", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_installed_reboot_slot_proof(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_installed_reboot_slot_proof(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        next_boot_target=args.next_boot_target,
        installed_slot_switch_evidence=args.installed_slot_switch_evidence,
    )
    errors = validate_installed_reboot_slot_proof(payload)
    payload["summary"]["ok"] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Proof: {payload['artifacts']['installed_reboot_slot_proof_markdown']}")
        print(f"Manifest: {payload['artifacts']['installed_reboot_slot_proof_json']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
