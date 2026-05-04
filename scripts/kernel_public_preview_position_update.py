#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_broader_preview_continuation_pack import build_broader_preview_continuation_pack

SCHEMA_VERSION = "agentos-public-preview-position-update.v1"
LAYOUT_DIRNAME = "public-preview-position-updates"
PUBLIC_STATEMENT = ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_position_update(
    *,
    workspace: str,
    report_dir: str,
    feedback_file: str = "",
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    root = resolve_root(report_dir)
    label = snapshot_label or "current"
    update_dir = root / f"public-preview-position-update-{label}"
    update_dir.mkdir(parents=True, exist_ok=True)

    continuation = build_broader_preview_continuation_pack(
        workspace=workspace,
        report_dir=str(root.parent / "cp"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    statement_text = PUBLIC_STATEMENT.read_text(encoding="utf-8") if PUBLIC_STATEMENT.exists() else ""
    summary = {
        "ok": True,
        "candidate_state": continuation["summary"]["candidate_state"],
        "audience_decision": continuation["summary"]["audience_decision"],
        "operating_health": continuation["summary"]["operating_health"],
        "operating_recommendation": continuation["summary"]["operating_recommendation"],
        "statement_mentions_broader_preview_candidate": "broader_preview_candidate" in statement_text,
        "statement_mentions_operating_evidence": "operating" in statement_text.lower() or "continuation pack" in statement_text.lower(),
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "update_label": label,
        "workspace": str(Path(workspace).resolve()),
        "update_root": str(root),
        "update_dir": str(update_dir),
        "broader_preview_continuation_pack": continuation,
        "public_statement_path": str(PUBLIC_STATEMENT),
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Position Update",
        "",
        f"Update label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Public position",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Statement mentions broader preview candidate: `{summary['statement_mentions_broader_preview_candidate']}`",
        f"- Statement mentions operating evidence: `{summary['statement_mentions_operating_evidence']}`",
    ]

    markdown_path = update_dir / "public-preview-position-update.md"
    manifest_path = update_dir / "public-preview-position-update.json"
    latest_manifest_path = root / "latest-public-preview-position-update.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_position_update_markdown": str(markdown_path),
        "public_preview_position_update_json": str(manifest_path),
        "latest_public_preview_position_update_json": str(latest_manifest_path),
        "broader_preview_continuation_pack_json": continuation["artifacts"]["broader_preview_continuation_pack_json"],
        "public_statement_path": str(PUBLIC_STATEMENT),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_position_update(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "update_label",
        "workspace",
        "update_root",
        "update_dir",
        "broader_preview_continuation_pack",
        "public_statement_path",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("broader_preview_continuation_pack", {}).get("schema_version") != "agentos-broader-preview-continuation-pack.v1":
        errors.append("broader_preview_continuation_pack must reference agentos-broader-preview-continuation-pack.v1")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview position update")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--feedback-file", default="")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--diagnostics-manifest", default="")
    parser.add_argument("--history-dir", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_public_preview_position_update(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_public_preview_position_update(
        workspace=args.workspace,
        report_dir=args.report_dir,
        feedback_file=args.feedback_file,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    errors = validate_public_preview_position_update(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
