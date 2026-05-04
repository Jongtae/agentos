#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = "agentos-codex-runtime-copy-lock.v1"


def build_payload() -> dict:
    welcome = (ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-welcome-shell").read_text(encoding="utf-8")
    install = (ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-install-appliance").read_text(encoding="utf-8")
    recovery = (ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-recovery-shell").read_text(encoding="utf-8")
    checks = {
        "welcome_continue_runtime": "launch the managed Codex CLI session" in welcome,
        "welcome_install_codex_appliance": "make this Codex appliance persistent" in welcome,
        "welcome_recovery_codex_path": "restore the Codex runtime path safely" in welcome,
        "install_codex_appliance": "make this Codex appliance persistent on disk" in install,
        "install_runtime_continuity": "Codex runtime continuity will be preserved" in install,
        "recovery_codex_runtime_path": "managed Codex runtime path" in recovery,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "checks": checks,
        "ok": all(checks.values()),
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    checks = payload.get("checks", {})
    for key in (
        "welcome_continue_runtime",
        "welcome_install_codex_appliance",
        "welcome_recovery_codex_path",
        "install_codex_appliance",
        "install_runtime_continuity",
        "recovery_codex_runtime_path",
    ):
        if checks.get(key) is not True:
            errors.append(f"checks.{key} must be true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate runtime-first welcome/install/recovery copy lock")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
