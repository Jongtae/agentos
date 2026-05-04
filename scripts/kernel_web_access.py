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

from kernel.capability_substrate import build_web_access_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS native web access evidence")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--requires-authentication", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--compatibility-required", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_web_access_report(
        args.workspace,
        args.url,
        domain_allowlist=args.allow_domain,
        requires_authentication=args.requires_authentication,
        interactive=args.interactive,
        compatibility_required=args.compatibility_required,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Web Access")
        print("==================")
        print(f"Workspace: {payload['workspace']}")
        print(f"URL: {payload['url']}")
        print(f"Native handled: {payload['native_handled']}")
        print(f"Escalated handled: {payload['escalated_handled']}")
        print(f"Escalation reason: {payload['escalation_reason'] or '(none)'}")
        print(f"Unsupported/deferred: {payload['unsupported_or_deferred']}")
        print(f"Mediation cost: {payload['mediation_cost']}")
    proof_ok = payload.get("proof", {}).get("ok", False)
    return 0 if proof_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
