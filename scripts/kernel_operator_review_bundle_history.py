#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "agentos-operator-review-bundle-history.v1"
EXPECTED_ARTIFACTS = ("bundle-manifest.json", "review-pack.json", "review-packet.md")
BUNDLE_LAYOUT_DIRNAME = "review-bundles"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _load_bundle_manifest(bundle_dir: Path) -> dict[str, Any] | None:
    manifest_path = bundle_dir / "bundle-manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("schema_version") != "agentos-operator-review-bundle.v1":
        return None
    return payload


def _artifact_status(bundle_dir: Path) -> dict[str, bool]:
    return {name: (bundle_dir / name).exists() for name in EXPECTED_ARTIFACTS}


def _resolve_history_root(history_dir: str) -> Path:
    root = Path(history_dir).resolve()
    if root.name == BUNDLE_LAYOUT_DIRNAME:
        return root
    nested = root / BUNDLE_LAYOUT_DIRNAME
    if nested.exists():
        return nested
    return root


def build_review_bundle_history(*, history_dir: str, limit: int = 20) -> dict[str, Any]:
    root = _resolve_history_root(history_dir)
    entries: list[dict[str, Any]] = []
    if root.exists():
        for bundle_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("review-bundle-")):
            manifest = _load_bundle_manifest(bundle_dir)
            if not manifest:
                continue
            entries.append(
                {
                    "bundle_dir": str(bundle_dir),
                    "generated_at_utc": str(manifest.get("generated_at_utc", "")),
                    "snapshot_label": str(manifest.get("snapshot_label", "")),
                    "summary": manifest.get("summary", {}) if isinstance(manifest.get("summary"), dict) else {},
                    "artifact_status": _artifact_status(bundle_dir),
                }
            )

    entries.sort(key=lambda item: item.get("generated_at_utc", ""))
    selected = entries[-max(1, int(limit)) :]
    changed_fields: set[str] = set()
    bundles: list[dict[str, Any]] = []
    prev_summary: dict[str, Any] | None = None
    prev_artifacts: dict[str, bool] | None = None
    prev_snapshot_label: str | None = None

    for item in selected:
        summary = item["summary"]
        artifact_status = item["artifact_status"]
        drift: list[str] = []
        if prev_summary is not None:
            for key in sorted(set(prev_summary.keys()) | set(summary.keys())):
                if _normalize(prev_summary.get(key)) != _normalize(summary.get(key)):
                    drift.append(key)
                    changed_fields.add(key)
            for key in EXPECTED_ARTIFACTS:
                if prev_artifacts and prev_artifacts.get(key) != artifact_status.get(key):
                    field = f"artifact_status.{key}"
                    drift.append(field)
                    changed_fields.add(field)
            if prev_snapshot_label != item["snapshot_label"]:
                drift.append("snapshot_label")
                changed_fields.add("snapshot_label")

        bundles.append(
            {
                "generated_at_utc": item["generated_at_utc"],
                "bundle_dir": item["bundle_dir"],
                "snapshot_label": item["snapshot_label"],
                "summary": summary,
                "artifact_status": artifact_status,
                "drift_fields": drift,
            }
        )
        prev_summary = summary
        prev_artifacts = artifact_status
        prev_snapshot_label = item["snapshot_label"]

    latest_summary = selected[-1]["summary"] if selected else {}
    latest_label = selected[-1]["snapshot_label"] if selected else ""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "history_dir": str(root),
        "summary": {
            "review_bundle_count": len(selected),
            "stable": len(changed_fields) == 0,
            "changed_fields": sorted(changed_fields),
            "latest_snapshot_label": latest_label,
            "latest_session_phase": str(latest_summary.get("session_phase", "")),
            "latest_approval_forensic_status": str(latest_summary.get("approval_forensic_status", "")),
            "latest_validation_stable": bool(latest_summary.get("validation_stable", False)) if latest_summary else False,
        },
        "bundles": bundles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS operator review-bundle history report")
    parser.add_argument("--history-dir", default="./artifacts")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_review_bundle_history(history_dir=args.history_dir, limit=args.limit)
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    summary = payload["summary"]
    print("AgentOS Review Bundle History")
    print("=============================")
    print(f"Review bundles: {summary['review_bundle_count']}")
    print(f"Stable: {summary['stable']}")
    print("Changed fields: " + (", ".join(summary["changed_fields"]) if summary["changed_fields"] else "(none)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
