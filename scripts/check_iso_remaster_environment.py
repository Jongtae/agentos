#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys

REQUIRED_TOOLS = ["xorriso", "unsquashfs", "mksquashfs", "bsdtar"]
SCHEMA_VERSION = "agentos-iso-remaster-environment.v1"
SUPPORTED_ENVIRONMENT = "linux-remaster-toolchain"


def build_report() -> dict:
    tools = {}
    missing = []
    for tool in REQUIRED_TOOLS:
        resolved = shutil.which(tool)
        tools[tool] = {"found": bool(resolved), "path": resolved or ""}
        if not resolved:
            missing.append(tool)
    return {
        "schema_version": SCHEMA_VERSION,
        "supported_environment": SUPPORTED_ENVIRONMENT,
        "ok": not missing,
        "required_tools": REQUIRED_TOOLS,
        "missing_tools": missing,
        "tools": tools,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the host provides the supported AgentOS ISO remaster toolchain")
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print('AgentOS ISO Remaster Environment Check')
        print('=====================================')
        print(f"Supported environment: {report['supported_environment']}")
        print(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
        for tool in REQUIRED_TOOLS:
            tool_info = report['tools'][tool]
            state = 'found' if tool_info['found'] else 'missing'
            extra = f" ({tool_info['path']})" if tool_info['path'] else ''
            print(f"- {tool}: {state}{extra}")
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
