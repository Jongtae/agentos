#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.provenance_graph import SCHEMA_VERSION, build_provenance_graph


REQUIRED_KEYS = {"schema_version", "workspace", "summary", "nodes", "edges", "causal_chains"}


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_KEYS - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(payload.get("nodes"), list) or not payload.get("nodes"):
        errors.append("nodes must be a non-empty list")
    if not isinstance(payload.get("edges"), list):
        errors.append("edges must be a list")
    if not isinstance(payload.get("causal_chains"), list):
        errors.append("causal_chains must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS provenance graph / causal chain view")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("ok" if not errors else "invalid")
            for error in errors:
                print(f"- {error}")
        return 0 if not errors else 1

    payload = build_provenance_graph(workspace=args.workspace, session_id=args.session_id, limit=args.limit)
    errors = validate_payload(payload)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        else:
            for error in errors:
                print(error)
        return 1

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Provenance Graph")
        print("========================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Nodes: {payload['summary']['node_count']}")
        print(f"Edges: {payload['summary']['edge_count']}")
        print(f"Chains: {payload['summary']['chain_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
