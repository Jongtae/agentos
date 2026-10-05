from __future__ import annotations

from pathlib import Path
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = "0.11.33"
SETUP_UV_REF = "c18668ad3cf93ea998bef934396af7bb5c839dc7"


def _toml(path: str) -> dict:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))


def test_uv_lock_covers_the_claimed_profiles_and_real_boundary() -> None:
    project = _toml("pyproject.toml")
    uv = project["tool"]["uv"]

    assert uv["required-version"] == ">=0.11.33,<0.13"
    assert set(uv["environments"]) == {
        "sys_platform == 'darwin'",
        "sys_platform == 'linux'",
    }
    assert uv["build-constraint-dependencies"] == ["setuptools==84.0.0"]

    lock = _toml("uv.lock")
    assert set(lock["supported-markers"]) == set(uv["environments"])
    assert lock["manifest"]["build-constraints"] == [
        {"name": "setuptools", "specifier": "==84.0.0"}
    ]

    packages = {package["name"]: package for package in lock["package"]}
    suffix_data = packages["publicsuffixlist"]
    assert suffix_data["source"] == {"registry": "https://pypi.org/simple"}
    assert suffix_data["sdist"]["hash"].startswith("sha256:")
    assert suffix_data["wheels"]
    assert all(wheel["hash"].startswith("sha256:") for wheel in suffix_data["wheels"])
    assert "pyobjc-framework-webkit" in packages


def test_dependabot_is_one_bounded_discovery_path_without_auto_merge() -> None:
    config = yaml.safe_load(
        (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    )
    updates = {entry["package-ecosystem"]: entry for entry in config["updates"]}

    assert set(updates) == {"uv", "github-actions"}
    assert updates["uv"]["directory"] == "/"
    assert updates["uv"]["open-pull-requests-limit"] == 2
    assert updates["uv"]["versioning-strategy"] == "increase-if-necessary"
    assert updates["uv"]["allow"] == [
        {
            "dependency-type": "direct",
            "update-types": [
                "version-update:semver-minor",
                "version-update:semver-patch",
            ],
        }
    ]
    assert updates["github-actions"]["open-pull-requests-limit"] == 1
    assert "groups" not in config
    assert "registries" not in config


def test_validation_uses_the_pinned_resolver_with_read_only_permissions() -> None:
    for relative_path in (
        ".github/workflows/validate.yml",
        ".github/workflows/full-validate.yml",
    ):
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert f"astral-sh/setup-uv@{SETUP_UV_REF}" in workflow
        assert f"version: '{UV_VERSION}'" in workflow
        assert "uv sync --locked --extra schema-validation --group dev" in workflow
        assert "permissions:\n  contents: read" in workflow
        assert "pull_request_target" not in workflow
        assert "contents: write" not in workflow
