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

from kernel_milestone_bundle import build_milestone_bundle

SCHEMA_VERSION = "agentos-preview-evaluation-kit.v1"
KIT_LAYOUT_DIRNAME = "preview-evaluation-kits"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "public-milestone-candidate-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-release-candidate-checklist-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-release-note-template-v1.md",
    ROOT_DIR / "docs" / "reference" / "release-artifact-manifest-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "platform-validation-matrix-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_kit_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == KIT_LAYOUT_DIRNAME:
        return report_root
    return report_root / KIT_LAYOUT_DIRNAME


def build_evaluator_guide(*, label: str, milestone_manifest: dict, reference_paths: Iterable[Path]) -> str:
    lines = [
        "# AgentOS Preview Evaluation Kit",
        "",
        f"Kit label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Intended use",
        "",
        "This kit is the evaluator-facing package for the current AgentOS preview baseline.",
        "The baseline should be judged as an appliance-first product, not as an Ubuntu-first install workflow.",
        "Use it when we want to hand a reviewer or internal evaluator one bounded package that explains:",
        "- what AgentOS currently is",
        "- how the current preview should be reviewed",
        "- which artifact bundle represents the milestone baseline",
        "",
        "## Included package",
        "",
        f"- Milestone label: `{milestone_manifest.get('milestone_label', 'current')}`",
        f"- Milestone bundle: `{milestone_manifest.get('milestone_dir', '')}`",
        f"- Product identity: `{(milestone_manifest.get('positioning', {}) or {}).get('product_identity', 'unknown')}`",
        f"- Platform baseline: `{(milestone_manifest.get('positioning', {}) or {}).get('platform_baseline', 'unknown')}`",
        "",
        "## Recommended evaluator flow",
        "",
        "1. Boot AgentOS through the default appliance path and aim for `AgentOS Setup -> AgentOS Managed Session -> ai>`.",
        "2. Read `evaluator-guide.md` and `preview-kit-manifest.json`.",
        "3. Read the copied preview references in `references/`.",
        "4. Inspect `public-milestone/` for the current milestone bundle and operator evidence payload.",
        "5. Use the preview checklist to structure feedback around direct-boot quality, setup clarity, and recovery clarity.",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{path.name}`" for path in reference_paths)
    lines.extend(
        [
            "",
            "## Current baseline statement",
            "",
            "AgentOS currently presents an appliance-first, Ubuntu-downstream operating environment with live appliance entry, install-later persistence, managed session entry, mediated control surfaces, operator-grade evidence workflows, preview release discipline, and an explicit x86_64 validation baseline.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_preview_evaluation_kit(
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
    kit_root = resolve_kit_root(report_dir)
    kit_dir = kit_root / f"preview-evaluation-kit-{snapshot_label or 'current'}"
    kit_dir.mkdir(parents=True, exist_ok=True)

    milestone_report_dir = kit_dir / "public-milestone"
    milestone_manifest = build_milestone_bundle(
        workspace=workspace,
        report_dir=str(milestone_report_dir),
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = kit_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    guide_path = kit_dir / "evaluator-guide.md"
    manifest_path = kit_dir / "preview-kit-manifest.json"
    latest_manifest_path = kit_root / "latest-preview-kit-manifest.json"

    guide_path.write_text(
        build_evaluator_guide(
            label=snapshot_label or "current",
            milestone_manifest=milestone_manifest,
            reference_paths=[Path(p) for p in copied_references],
        ),
        encoding="utf-8",
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "kit_label": snapshot_label or "current",
        "workspace": str(Path(workspace).resolve()),
        "kit_root": str(kit_root),
        "kit_dir": str(kit_dir),
        "artifacts": {
            "evaluator_guide_markdown": str(guide_path),
            "preview_kit_manifest_json": str(manifest_path),
            "latest_preview_kit_manifest_json": str(latest_manifest_path),
            "milestone_bundle_dir": milestone_manifest["milestone_dir"],
            "milestone_bundle_manifest_json": milestone_manifest["artifacts"]["milestone_manifest_json"],
        },
        "references": copied_references,
        "milestone_manifest": milestone_manifest,
        "summary": {
            "ok": True,
            "reference_count": len(copied_references),
            "includes_milestone_bundle": True,
            "includes_preview_checklist": any(Path(p).name == "preview-release-candidate-checklist-v1.md" for p in copied_references),
            "includes_platform_validation": any(Path(p).name == "platform-validation-matrix-v1.md" for p in copied_references),
        },
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS preview evaluation kit")
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

    payload = build_preview_evaluation_kit(
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

    print("AgentOS Preview Evaluation Kit")
    print("==============================")
    print(f"Kit dir: {payload['kit_dir']}")
    print(f"Evaluator guide: {payload['artifacts']['evaluator_guide_markdown']}")
    print(f"Milestone bundle: {payload['artifacts']['milestone_bundle_dir']}")
    print(f"Manifest: {payload['artifacts']['preview_kit_manifest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
