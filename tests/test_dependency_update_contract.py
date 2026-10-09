from __future__ import annotations

from pathlib import Path
from importlib.metadata import requires, version
import tomllib

import yaml
from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = "0.11.33"
SETUP_UV_REF = "c18668ad3cf93ea998bef934396af7bb5c839dc7"
MCP_VERSION = "2.3.0"


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
    assert updates["uv"]["exclude-paths"] == ["evals/**"]
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

    contract = (ROOT / "docs/dependency-update-contract.en.md").read_text(
        encoding="utf-8"
    )
    assert "explicitly excludes `evals/**`" in contract
    assert "evaluation requirements remain on" in contract


def test_validation_uses_the_pinned_resolver_with_read_only_permissions() -> None:
    for relative_path in (
        ".github/workflows/validate.yml",
        ".github/workflows/full-validate.yml",
    ):
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert f"astral-sh/setup-uv@{SETUP_UV_REF}" in workflow
        assert f"version: '{UV_VERSION}'" in workflow
        # Required CI syncs only what its focused tests import (#1132); the
        # nightly suite syncs every extra. Both stay locked to the pinned resolver.
        assert "uv sync --locked" in workflow and "--group dev" in workflow
        if relative_path.endswith("full-validate.yml"):
            assert "uv sync --locked --extra mcp-host --extra schema-validation --group dev" in workflow
        assert "permissions:\n  contents: read" in workflow
        assert "pull_request_target" not in workflow
        assert "contents: write" not in workflow


def _dependency_closure(packages: dict, roots: list[dict]) -> set[str]:
    """Follow the locked required edges, without opting into another extra."""
    closure: set[str] = set()
    pending = [edge["name"] for edge in roots]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        pending.extend(edge["name"] for edge in packages[name].get("dependencies", []))
    return closure


def test_mcp_sdk_is_exact_and_host_only_in_the_resolved_package_graph() -> None:
    project = _toml("pyproject.toml")["project"]
    assert project["optional-dependencies"]["mcp-host"] == [f"mcp=={MCP_VERSION}"]
    assert f"mcp-types=={MCP_VERSION}" in project["dependencies"]
    assert not any(dependency.split("=")[0] == "mcp" for dependency in project["dependencies"])

    packages = {package["name"]: package for package in _toml("uv.lock")["package"]}
    root = packages["personal-agentos"]
    assert root["optional-dependencies"]["mcp-host"] == [{"name": "mcp"}]
    assert {"name": "mcp", "marker": "extra == 'mcp-host'", "specifier": "==2.3.0"} in root["metadata"]["requires-dist"]
    base = _dependency_closure(packages, root["dependencies"])
    host = _dependency_closure(packages, root["optional-dependencies"]["mcp-host"])
    sdk_only = {
        "mcp", "anyio", "click", "h11", "httpcore2", "httpx2",
        "opentelemetry-api", "pyjwt", "python-multipart", "sse-starlette",
        "starlette", "truststore", "uvicorn",
    }
    assert sdk_only <= host
    assert not sdk_only & base
    assert "mcp-types" in base & host
    for name in ("mcp", "mcp-types"):
        assert packages[name]["version"] == MCP_VERSION
        assert packages[name]["source"] == {"registry": "https://pypi.org/simple"}
    assert packages["mcp"]["wheels"][0]["hash"] == "sha256:dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377"
    assert packages["mcp"]["sdist"]["hash"] == "sha256:8b147a50441cf059dc88c684e0aeed3687f0aa0f39c6cde7b90330effd2b34d8"


def test_host_profile_executes_the_pinned_public_sdk_apis() -> None:
    from mcp.server.stdio import stdio_server
    from mcp.shared.jsonrpc_dispatcher import JSONRPCDispatcher

    assert version("mcp") == MCP_VERSION
    assert version("mcp-types") == MCP_VERSION
    assert callable(stdio_server)
    assert callable(JSONRPCDispatcher)

    # Exercise setuptools' installed metadata, not only the source manifest.
    sdk = next(
        Requirement(item) for item in requires("personal-agentos") or []
        if Requirement(item).name == "mcp"
    )
    assert str(sdk.specifier) == f"=={MCP_VERSION}"
    assert sdk.marker is not None
    assert sdk.marker.evaluate({"extra": "mcp-host"})
    assert not sdk.marker.evaluate({"extra": ""})
