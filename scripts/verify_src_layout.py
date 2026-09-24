#!/usr/bin/env python3
"""Verify the repository's src-layout package boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "personal_agent"


def _require(condition, message, failures):
    if not condition:
        failures.append(message)


def main():
    failures = []
    _require(PACKAGE.is_dir(), "missing src/personal_agent package", failures)
    _require(not (ROOT / "personal_agent").exists(), "legacy root personal_agent exists", failures)

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    _require('where = ["src"]' in pyproject, "setuptools src discovery is not configured", failures)
    _require('personal_agent = ["web/*.html", "web/*.css", "web/*.js"]' in pyproject,
             "personal_agent web package data is not configured", failures)
    for retired in ("delivery.py", "handoff.py", "delivery-plan.yaml"):
        _require(not (PACKAGE / retired).exists(),
                 f"repository-only {retired} is still shipped in personal_agent", failures)
    _require((ROOT / "scripts" / "dev" / "delivery.py").is_file(),
             "repository delivery controller is missing from scripts/dev", failures)
    _require((ROOT / "scripts" / "dev" / "handoff.py").is_file(),
             "repository handoff loop is missing from scripts/dev", failures)

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    engine_dockerfile = (ROOT / "Dockerfile.engine").read_text(encoding="utf-8")
    egress_dockerfile = (ROOT / "Dockerfile.egress").read_text(encoding="utf-8")
    _require("COPY src/personal_agent /app/src/personal_agent" in dockerfile,
             "Dockerfile does not preserve the src layout", failures)
    _require("COPY src/personal_agent /app/src/personal_agent" in engine_dockerfile,
             "Dockerfile.engine does not preserve the src layout", failures)
    _require("COPY src/personal_agent/limited_egress_proxy.py" in egress_dockerfile,
             "Dockerfile.egress does not copy the source package", failures)

    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    _require("!src/personal_agent/" in dockerignore and "!src/personal_agent/**" in dockerignore,
             ".dockerignore does not include the source package", failures)

    package_scripts = (
        "agentos-backup.py",
        "agentos-restore.py",
        "operating_preflight.py",
        "verify_continuity_acceptance.py",
        "verify_document_acceptance.py",
        "verify_document_boundary.py",
        "verify_general_agent.py",
        "verify_telegram_task_card_acceptance.py",
        "verify_weather_acceptance.py",
    )
    for name in package_scripts:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        _require("/src" in text or " / 'src'" in text or ' / "src"' in text,
                 f"{name} does not bootstrap the src package root", failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("src layout verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
