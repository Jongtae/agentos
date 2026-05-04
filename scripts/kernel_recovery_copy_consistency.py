#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = "agentos-recovery-copy-consistency.v1"
LAYOUT_DIRNAME = "recovery-copy-consistency"
SUMMARY = "AgentOS Recovery -> Return to AgentOS -> ai>"
DETAIL = "AgentOS Recovery -> AgentOS Setup -> AgentOS Managed Session -> ai>"

SURFACES = {
    "runtime_status": {
        "path": "src/status.py",
        "required": [
            "Use AgentOS Recovery when you need a safe shell. When you are ready, return to AgentOS and continue to ai>.",
            "recommended_rejoin_summary",
            "Return to AgentOS",
        ],
    },
    "kernelctl_status": {
        "path": "scripts/agentos-kernelctl",
        "required": [
            "Recovery path: AgentOS Recovery",
            SUMMARY,
            DETAIL,
        ],
    },
    "firstrun_failure": {
        "path": "scripts/agentos-firstrun",
        "required": [
            f"Recovery path: {SUMMARY}",
            f"Detailed rejoin path: {DETAIL}",
        ],
    },
    "install_output": {
        "path": "scripts/install_kernel_boot_integration.sh",
        "required": [
            f"- AgentOS Recovery:           {SUMMARY}",
            f"- detailed recovery rejoin:   {DETAIL}",
        ],
    },
    "readme": {
        "path": "README.md",
        "required": [SUMMARY],
    },
    "vm_quickstart": {
        "path": "docs/runbooks/vm-install-quickstart.md",
        "required": [SUMMARY, DETAIL],
    },
    "vm_install_guide": {
        "path": "docs/runbooks/vm-install-guide.md",
        "required": [SUMMARY, DETAIL],
    },
    "operations_runbook": {
        "path": "docs/runbooks/agentos-operations-runbook.md",
        "required": [SUMMARY, DETAIL],
    },
    "recovery_contract": {
        "path": "docs/reference/agentos-recovery-path-contract-v1.md",
        "required": [SUMMARY, DETAIL],
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _check_surface(path: Path, required: list[str]) -> dict:
    exists = path.exists()
    text = path.read_text(encoding="utf-8") if exists else ""
    missing = [pattern for pattern in required if pattern not in text]
    if not exists:
        status = "blocked"
    elif missing:
        status = "watch"
    else:
        status = "ready"
    return {
        "path": str(path),
        "exists": exists,
        "required_patterns": required,
        "missing_patterns": missing,
        "status": status,
    }


def build_recovery_copy_consistency(*, workspace: str, report_dir: str, snapshot_label: str = "current") -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"recovery-copy-consistency-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    surfaces = {
        name: _check_surface(ROOT_DIR / rule["path"], rule["required"])
        for name, rule in SURFACES.items()
    }
    blocked = [name for name, payload in surfaces.items() if payload["status"] == "blocked"]
    watch = [name for name, payload in surfaces.items() if payload["status"] == "watch"]
    ready = [name for name, payload in surfaces.items() if payload["status"] == "ready"]
    overall_state = "blocked" if blocked else ("watch" if watch else "ready")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "consistency_root": str(root),
        "consistency_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "canonical_recovery_summary": SUMMARY,
        "canonical_recovery_detail": DETAIL,
        "surfaces": surfaces,
        "summary": {
            "ok": True,
            "overall_state": overall_state,
            "blocked_surfaces": blocked,
            "watch_surfaces": watch,
            "ready_surfaces": ready,
        },
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Recovery Copy Consistency",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Canonical language",
        "",
        f"- Summary: `{SUMMARY}`",
        f"- Detailed path: `{DETAIL}`",
        "",
        "## Surface state",
        "",
        f"- Overall state: `{overall_state}`",
        f"- Blocked surfaces: `{len(blocked)}`",
        f"- Watch surfaces: `{len(watch)}`",
        f"- Ready surfaces: `{len(ready)}`",
        "",
    ]
    for name, surface in surfaces.items():
        markdown.append(f"### {name}")
        markdown.append(f"- status: `{surface['status']}`")
        markdown.append(f"- path: `{surface['path']}`")
        if surface["missing_patterns"]:
            markdown.extend(f"- missing: `{pattern}`" for pattern in surface["missing_patterns"])
        else:
            markdown.append("- missing: none")
        markdown.append("")

    markdown_path = run_dir / "recovery-copy-consistency.md"
    manifest_path = run_dir / "recovery-copy-consistency.json"
    latest_manifest_path = root / "latest-recovery-copy-consistency.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "recovery_copy_consistency_markdown": str(markdown_path),
        "recovery_copy_consistency_manifest_json": str(manifest_path),
        "latest_recovery_copy_consistency_manifest_json": str(latest_manifest_path),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_recovery_copy_consistency(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "consistency_root",
        "consistency_dir",
        "snapshot_label",
        "canonical_recovery_summary",
        "canonical_recovery_detail",
        "surfaces",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for name in SURFACES:
        surface = payload.get("surfaces", {}).get(name)
        if not isinstance(surface, dict):
            errors.append(f"surfaces.{name} must be present")
            continue
        if surface.get("status") not in {"blocked", "watch", "ready"}:
            errors.append(f"surfaces.{name}.status must be blocked, watch, or ready")
    if payload.get("summary", {}).get("overall_state") not in {"blocked", "watch", "ready"}:
        errors.append("summary.overall_state must be blocked, watch, or ready")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS recovery copy consistency report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_recovery_copy_consistency(payload)
        if errors:
            for item in errors:
                print(item, file=sys.stderr)
            return 1
        print("PASS")
        return 0

    payload = build_recovery_copy_consistency(
        workspace=args.workspace,
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(json.dumps(payload["summary"], ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
