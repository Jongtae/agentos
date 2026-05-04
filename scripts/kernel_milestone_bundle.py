#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_operator_review_bundle import build_review_bundle  # noqa: E402

SCHEMA_VERSION = "agentos-public-milestone-bundle.v1"
MILESTONE_LAYOUT_DIRNAME = "milestone-bundles"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "distribution-strategy-paper-v1.md",
    ROOT_DIR / "docs" / "reference" / "install-identity-native-session-ux-v1.md",
    ROOT_DIR / "docs" / "reference" / "release-engineering-v1.md",
    ROOT_DIR / "docs" / "reference" / "kernel-deepening-feasibility-v1.md",
    ROOT_DIR / "docs" / "reference" / "platform-strategy-v1.md",
    ROOT_DIR / "docs" / "reference" / "stage3-decision-pack-v1.md",
    ROOT_DIR / "docs" / "reference" / "stage3-closeout-memo.md",
    ROOT_DIR / "docs" / "reference" / "post-stage3-roadmap-window-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_milestone_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == MILESTONE_LAYOUT_DIRNAME:
        return report_root
    return report_root / MILESTONE_LAYOUT_DIRNAME


def build_milestone_note(*, milestone_label: str, review_bundle_manifest: dict, reference_paths: Iterable[Path]) -> str:
    summary = review_bundle_manifest.get("summary", {})
    lines = [
        "# AgentOS Public Milestone Bundle",
        "",
        f"Milestone label: `{milestone_label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Positioning",
        "",
        "This bundle captures the current externally reviewable AgentOS baseline:",
        "- Ubuntu-downstream AgentOS",
        "- AgentOS-first operating environment",
        "- managed session entry (`setup -> ai>`)",
        "- mediated control surfaces and operator-grade evidence/replay workflows",
        "- bounded kernel-assisted policy enforcement",
        "- coherent install-to-recovery contract",
        "",
        "## Review Bundle Summary",
        "",
        f"- Session phase: `{summary.get('session_phase', 'unknown')}`",
        f"- Session origin: `{summary.get('session_origin', 'unknown')}`",
        f"- Approval forensic status: `{summary.get('approval_forensic_status', 'unknown')}`",
        f"- Validation stable: `{summary.get('validation_stable', False)}`",
        "",
        "## Included References",
        "",
    ]
    lines.extend(f"- `{path.name}`" for path in reference_paths)
    lines.extend(
        [
            "",
            "## Recommended Review Order",
            "",
            "1. Read `milestone-manifest.json` for the package structure.",
            "2. Read `milestone-note.md` for the current milestone framing.",
            "3. Inspect `review-bundle/` for operator evidence and handoff artifacts.",
            "4. Read `references/` for Stage 3 decisions and Stage 4 roadmap intent.",
        ]
    )
    return "\n".join(lines) + "\n"



def build_milestone_bundle(
    *,
    workspace: str,
    report_dir: str,
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    milestone_root = resolve_milestone_root(report_dir)
    milestone_dir = milestone_root / f"milestone-bundle-{snapshot_label or 'current'}"
    milestone_dir.mkdir(parents=True, exist_ok=True)

    review_report_dir = milestone_dir / "operator-review"
    review_bundle_manifest = build_review_bundle(
        workspace=workspace,
        report_dir=str(review_report_dir),
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = milestone_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    milestone_note_path = milestone_dir / "milestone-note.md"
    milestone_manifest_path = milestone_dir / "milestone-manifest.json"
    latest_manifest_path = milestone_root / "latest-milestone-manifest.json"
    milestone_note_path.write_text(
        build_milestone_note(
            milestone_label=snapshot_label or "current",
            review_bundle_manifest=review_bundle_manifest,
            reference_paths=[Path(p) for p in copied_references],
        ),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "milestone_label": snapshot_label or "current",
        "workspace": str(Path(workspace).resolve()),
        "milestone_root": str(milestone_root),
        "milestone_dir": str(milestone_dir),
        "default_public_artifact": True,
        "positioning": {
            "product_identity": "ubuntu_downstream_agentos",
            "session_identity": "setup_first_managed_session",
            "kernel_path": "apparmor_primary_ebpf_secondary",
            "platform_baseline": "x86_64",
        },
        "artifacts": {
            "milestone_note_markdown": str(milestone_note_path),
            "milestone_manifest_json": str(milestone_manifest_path),
            "review_bundle_dir": review_bundle_manifest["bundle_dir"],
            "review_bundle_manifest_json": review_bundle_manifest["artifacts"]["bundle_manifest_json"],
            "latest_milestone_manifest_json": str(latest_manifest_path),
        },
        "references": copied_references,
        "review_bundle_summary": review_bundle_manifest.get("summary", {}),
        "review_bundle_manifest": review_bundle_manifest,
    }
    milestone_manifest_path.write_text(json.dumps(manifest, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(manifest, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest



def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS public milestone bundle")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--diagnostics-manifest", default="")
    parser.add_argument("--history-dir", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_milestone_bundle(
        workspace=args.workspace,
        report_dir=args.report_dir,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    print("AgentOS Public Milestone Bundle")
    print("===============================")
    print(f"Milestone dir: {payload['milestone_dir']}")
    print(f"Milestone note: {payload['artifacts']['milestone_note_markdown']}")
    print(f"Review bundle: {payload['artifacts']['review_bundle_dir']}")
    print(f"Manifest: {payload['artifacts']['milestone_manifest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
