#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.event_fabric.session_contract import session_start_contract
from kernel.runtime_entry import build_runtime_entry_contract

SCHEMA_VERSION = "agentos-direct-boot-messaging-consistency.v1"
LAYOUT_DIRNAME = "direct-boot-messaging-consistency"
CANONICAL_IDENTITY_PATH = ["AgentOS Setup", "AgentOS Managed Session", "ai>"]
CANONICAL_RECOVERY_SUMMARY_PATH = ["AgentOS Recovery", "Return to AgentOS", "ai>"]
CANONICAL_RECOVERY_PATH = ["AgentOS Recovery", "AgentOS Setup", "AgentOS Managed Session", "ai>"]
CANONICAL_INSTALL_LATER_MEANING = "make this appliance persistent"
DOC_RULES = {
    "readme": {
        "path": "README.md",
        "patterns": [
            "AgentOS Setup -> AgentOS Managed Session -> ai>",
            "AgentOS Recovery",
            "AgentOS Recovery -> Return to AgentOS -> ai>",
            "brew install --cask utm",
        ],
    },
    "vm_install_quickstart": {
        "path": "docs/runbooks/vm-install-quickstart.md",
        "patterns": [
            "Continue to AgentOS",
            "Install AgentOS",
            "make this appliance persistent",
            "AgentOS Recovery",
            "AgentOS Recovery -> Return to AgentOS -> ai>",
            "AgentOS Setup -> AgentOS Managed Session -> ai>",
        ],
    },
    "vm_install_guide": {
        "path": "docs/runbooks/vm-install-guide.md",
        "patterns": [
            "Continue to AgentOS",
            "Install AgentOS",
            "make this appliance persistent",
            "AgentOS Recovery",
            "AgentOS Recovery -> Return to AgentOS -> ai>",
            "AgentOS Setup -> AgentOS Managed Session -> ai>",
        ],
    },
    "operations_runbook": {
        "path": "docs/runbooks/agentos-operations-runbook.md",
        "patterns": [
            "Continue to AgentOS",
            "make this appliance persistent",
            "AgentOS Recovery",
            "AgentOS Recovery -> Return to AgentOS -> ai>",
            "boot AgentOS -> tiny setup -> ai>",
        ],
    },
    "packaging_runbook": {
        "path": "docs/runbooks/distribution-packaging-runbook.md",
        "patterns": [
            "AgentOS Setup -> AgentOS Managed Session -> ai>",
            "AgentOS Recovery",
            "advanced/fallback reference",
        ],
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _check_doc(path: Path, patterns: list[str]) -> dict:
    exists = path.exists()
    text = path.read_text(encoding="utf-8") if exists else ""
    missing = [pattern for pattern in patterns if pattern not in text]
    if not exists:
        status = "blocked"
    elif missing:
        status = "watch"
    else:
        status = "ready"
    return {
        "path": str(path),
        "exists": exists,
        "required_patterns": patterns,
        "missing_patterns": missing,
        "status": status,
    }


def build_direct_boot_messaging_consistency(*, workspace: str, report_dir: str, docs_root: str = "", snapshot_label: str = "current") -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"direct-boot-messaging-consistency-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    docs_base = Path(docs_root).resolve() if docs_root else ROOT_DIR
    session_contract = session_start_contract()
    runtime_entry_live = build_runtime_entry_contract(
        session_origin={"category": "live_appliance_boot"},
        setup_state={"status": "pending", "next_managed_entry": "setup_session"},
    )
    runtime_entry_installed = build_runtime_entry_contract(
        session_origin={"category": "installed_appliance_boot"},
        setup_state={"status": "configured", "next_managed_entry": "ai_shell"},
    )

    install_later = session_contract.get("install_later_contract", {})
    installed_appliance = session_contract.get("installed_appliance_contract", {})
    recovery_contract = session_contract.get("recovery_contract", {})

    runtime_checks = {
        "preferred_origin_live": runtime_entry_live.get("preferred_origin") == "live_appliance_boot",
        "preferred_origin_installed": runtime_entry_live.get("preferred_installed_origin") == "installed_appliance_boot",
        "install_action_label": install_later.get("install_action_label") == "Install AgentOS",
        "install_action_meaning": install_later.get("persistence_goal") == "make_this_appliance_persistent",
        "post_install_identity_path": install_later.get("post_install_identity_path") == CANONICAL_IDENTITY_PATH,
        "installed_identity_path": installed_appliance.get("identity_path") == CANONICAL_IDENTITY_PATH,
        "recovery_label": recovery_contract.get("label") == "AgentOS Recovery",
        "recovery_summary_path": recovery_contract.get("recovery_summary_path") == CANONICAL_RECOVERY_SUMMARY_PATH,
        "recovery_identity_path": recovery_contract.get("recovery_identity_path") == CANONICAL_RECOVERY_PATH,
        "runtime_entry_recovery_label": runtime_entry_live.get("recovery_label") == "AgentOS Recovery",
        "installed_effective_target": runtime_entry_installed.get("effective_target") == "ai_shell",
    }
    failed_runtime_checks = [name for name, ok in runtime_checks.items() if not ok]

    docs = {
        name: _check_doc(docs_base / rule["path"], rule["patterns"])
        for name, rule in DOC_RULES.items()
    }
    missing_doc_patterns = {
        name: payload["missing_patterns"]
        for name, payload in docs.items()
        if payload["missing_patterns"]
    }

    targets = {
        "boot_messaging": {
            "status": "blocked" if not runtime_checks["preferred_origin_live"] else ("watch" if docs["vm_install_quickstart"]["missing_patterns"] or docs["vm_install_guide"]["missing_patterns"] else "ready"),
            "sources": ["vm_install_quickstart", "vm_install_guide", "operations_runbook"],
        },
        "setup_messaging": {
            "status": "blocked" if not runtime_checks["post_install_identity_path"] else ("watch" if docs["readme"]["missing_patterns"] else "ready"),
            "sources": ["readme", "vm_install_quickstart", "vm_install_guide"],
        },
        "install_later_messaging": {
            "status": "blocked" if not (runtime_checks["install_action_label"] and runtime_checks["install_action_meaning"]) else ("watch" if docs["vm_install_quickstart"]["missing_patterns"] or docs["vm_install_guide"]["missing_patterns"] else "ready"),
            "sources": ["vm_install_quickstart", "vm_install_guide", "packaging_runbook"],
        },
        "recovery_messaging": {
            "status": "blocked" if not (runtime_checks["recovery_label"] and runtime_checks["recovery_identity_path"] and runtime_checks["runtime_entry_recovery_label"]) else ("watch" if docs["operations_runbook"]["missing_patterns"] else "ready"),
            "sources": ["operations_runbook", "vm_install_quickstart", "vm_install_guide"],
        },
    }

    blocked_targets = [name for name, payload in targets.items() if payload["status"] == "blocked"]
    watch_targets = [name for name, payload in targets.items() if payload["status"] == "watch"]
    ready_targets = [name for name, payload in targets.items() if payload["status"] == "ready"]
    if blocked_targets:
        overall_state = "blocked"
    elif watch_targets:
        overall_state = "watch"
    else:
        overall_state = "ready"

    summary = {
        "ok": True,
        "overall_state": overall_state,
        "canonical_identity_path": CANONICAL_IDENTITY_PATH,
        "canonical_recovery_summary_path": CANONICAL_RECOVERY_SUMMARY_PATH,
        "canonical_recovery_path": CANONICAL_RECOVERY_PATH,
        "canonical_install_later_meaning": CANONICAL_INSTALL_LATER_MEANING,
        "failed_runtime_checks": failed_runtime_checks,
        "missing_doc_patterns": missing_doc_patterns,
        "blocked_targets": blocked_targets,
        "watch_targets": watch_targets,
        "ready_targets": ready_targets,
        "boot_messaging": targets["boot_messaging"]["status"],
        "setup_messaging": targets["setup_messaging"]["status"],
        "install_later_messaging": targets["install_later_messaging"]["status"],
        "recovery_messaging": targets["recovery_messaging"]["status"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "consistency_root": str(root),
        "consistency_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "canonical_language": {
            "boot_action_label": "Continue to AgentOS",
            "install_action_label": "Install AgentOS",
            "install_action_meaning": CANONICAL_INSTALL_LATER_MEANING,
            "setup_label": "AgentOS Setup",
            "managed_session_label": "AgentOS Managed Session",
            "recovery_label": "AgentOS Recovery",
            "recovery_summary_path": CANONICAL_RECOVERY_SUMMARY_PATH,
            "identity_path": CANONICAL_IDENTITY_PATH,
            "recovery_identity_path": CANONICAL_RECOVERY_PATH,
        },
        "runtime_contracts": {
            "session_start_contract": session_contract,
            "runtime_entry_live": runtime_entry_live,
            "runtime_entry_installed": runtime_entry_installed,
            "checks": runtime_checks,
        },
        "docs": docs,
        "targets": targets,
        "summary": summary,
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Direct-Boot Messaging Consistency",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Overall state",
        "",
        f"- Overall state: `{overall_state}`",
        f"- Boot messaging: `{summary['boot_messaging']}`",
        f"- Setup messaging: `{summary['setup_messaging']}`",
        f"- Install-later messaging: `{summary['install_later_messaging']}`",
        f"- Recovery messaging: `{summary['recovery_messaging']}`",
        "",
        "## Canonical language",
        "",
        f"- Boot action: `{payload['canonical_language']['boot_action_label']}`",
        f"- Install action: `{payload['canonical_language']['install_action_label']}`",
        f"- Install meaning: `{payload['canonical_language']['install_action_meaning']}`",
        f"- Setup path: `{' -> '.join(CANONICAL_IDENTITY_PATH)}`",
        f"- Recovery summary: `{' -> '.join(CANONICAL_RECOVERY_SUMMARY_PATH)}`",
        f"- Recovery path: `{' -> '.join(CANONICAL_RECOVERY_PATH)}`",
        "",
        "## Runtime contract checks",
        "",
    ]
    for name, ok in runtime_checks.items():
        markdown.append(f"- `{name}`: `{'pass' if ok else 'fail'}`")
    markdown.extend(["", "## Documentation checks", ""])
    for name, details in docs.items():
        markdown.append(f"### {name}")
        markdown.append(f"- status: `{details['status']}`")
        markdown.append(f"- path: `{details['path']}`")
        if details["missing_patterns"]:
            markdown.extend(f"- missing: `{item}`" for item in details["missing_patterns"])
        else:
            markdown.append("- missing: none")
        markdown.append("")

    markdown_path = run_dir / "direct-boot-messaging-consistency.md"
    manifest_path = run_dir / "direct-boot-messaging-consistency.json"
    latest_manifest_path = root / "latest-direct-boot-messaging-consistency.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "direct_boot_messaging_consistency_markdown": str(markdown_path),
        "direct_boot_messaging_consistency_manifest_json": str(manifest_path),
        "latest_direct_boot_messaging_consistency_manifest_json": str(latest_manifest_path),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_direct_boot_messaging_consistency(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "consistency_root",
        "consistency_dir",
        "snapshot_label",
        "canonical_language",
        "runtime_contracts",
        "docs",
        "targets",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    if summary.get("overall_state") not in {"blocked", "watch", "ready"}:
        errors.append("summary.overall_state must be blocked, watch, or ready")
    for key in ("boot_messaging", "setup_messaging", "install_later_messaging", "recovery_messaging"):
        if summary.get(key) not in {"blocked", "watch", "ready"}:
            errors.append(f"summary.{key} must be blocked, watch, or ready")
    runtime_checks = payload.get("runtime_contracts", {}).get("checks", {})
    if not isinstance(runtime_checks, dict) or not runtime_checks:
        errors.append("runtime_contracts.checks must be present")
    docs = payload.get("docs", {})
    for name in DOC_RULES:
        if name not in docs:
            errors.append(f"docs.{name} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS direct-boot messaging consistency report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--docs-root", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_direct_boot_messaging_consistency(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_direct_boot_messaging_consistency(
        workspace=args.workspace,
        report_dir=args.report_dir,
        docs_root=args.docs_root,
        snapshot_label=args.snapshot_label,
    )
    errors = validate_direct_boot_messaging_consistency(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
