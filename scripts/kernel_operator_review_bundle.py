#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_operator_review_pack import build_review_pack
from kernel_operator_review_packet import build_review_packet_markdown

SCHEMA_VERSION = "agentos-operator-review-bundle.v1"
BUNDLE_LAYOUT_DIRNAME = "review-bundles"


def resolve_bundle_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == BUNDLE_LAYOUT_DIRNAME:
        return report_root
    return report_root / BUNDLE_LAYOUT_DIRNAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_review_bundle(
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
    payload = build_review_pack(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )

    bundle_root = resolve_bundle_root(report_dir)
    bundle_dir = bundle_root / f"review-bundle-{snapshot_label or 'current'}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    review_pack_path = bundle_dir / "review-pack.json"
    review_packet_path = bundle_dir / "review-packet.md"
    bundle_manifest_path = bundle_dir / "bundle-manifest.json"

    review_pack_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    review_packet_path.write_text(build_review_packet_markdown(payload), encoding="utf-8")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "snapshot_label": snapshot_label or "current",
        "bundle_root": str(bundle_root),
        "bundle_dir": str(bundle_dir),
        "default_handoff_artifact": True,
        "product_story": "appliance_first_demo_and_review",
        "expected_identity_path": ["AgentOS Setup", "AgentOS Managed Session", "ai>"],
        "export_conventions": {
            "artifact_family": "review_bundle",
            "layout_schema": "agentos-review-bundle-layout.v1",
            "bundle_dir_pattern": "review-bundles/review-bundle-<snapshot_label>",
            "latest_manifest_json": str(bundle_root / "latest-bundle-manifest.json"),
        },
        "artifacts": {
            "review_pack_json": str(review_pack_path),
            "review_packet_markdown": str(review_packet_path),
            "bundle_manifest_json": str(bundle_manifest_path),
        },
        "summary": payload.get("summary", {}),
    }
    bundle_manifest_path.write_text(json.dumps(manifest, ensure_ascii=True) + "\n", encoding="utf-8")
    (bundle_root / "latest-bundle-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS operator review bundle")
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

    payload = build_review_bundle(
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

    print("AgentOS Review Bundle")
    print("=====================")
    print(f"Bundle dir: {payload['bundle_dir']}")
    print(f"Review pack: {payload['artifacts']['review_pack_json']}")
    print(f"Review packet: {payload['artifacts']['review_packet_markdown']}")
    print(f"Manifest: {payload['artifacts']['bundle_manifest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
