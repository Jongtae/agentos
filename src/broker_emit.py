from __future__ import annotations

import argparse
import json

from kernel.broker import append_broker_transition


def _parse_pairs(items: list[str]) -> dict:
    payload: dict[str, object] = {}
    for item in items:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            continue
        payload[key] = value
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit broker request/decision transitions into the OS event fabric")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--component", default="agentos-broker-hook")
    parser.add_argument("--path", default="")
    parser.add_argument("--actor-field", action="append", default=[])
    parser.add_argument("--object-field", action="append", default=[])
    parser.add_argument("--metadata-field", action="append", default=[])
    parser.add_argument("--correlation-field", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    actor = {"component": args.component}
    if args.path:
        actor["path"] = args.path
    actor.update(_parse_pairs(args.actor_field))
    object_payload = _parse_pairs(args.object_field)
    metadata = _parse_pairs(args.metadata_field)
    correlation = _parse_pairs(args.correlation_field)

    written = append_broker_transition(
        args.workspace,
        kind=args.kind,
        action=args.action,
        state=args.state,
        reason=args.reason,
        actor=actor,
        object=object_payload,
        correlation=correlation,
        metadata=metadata,
    )
    payload = {"ok": True, "written": written, "workspace": args.workspace, "kind": args.kind, "state": args.state}
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(f"broker transition emitted: kind={args.kind} state={args.state} written={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
