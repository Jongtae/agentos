import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("agentos_doctor", ROOT / "scripts" / "agentos_doctor.py")
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


class Runner:
    def __init__(self, values):
        self.calls = []
        self.values = values

    def __call__(self, command, root, env=None):
        command = tuple(command)
        self.calls.append((command, env))
        if command in self.values:
            return SimpleNamespace(returncode=0, stdout=self.values[command], stderr="")
        if (
            command[:2] == ("docker", "compose")
            and command[-2:] == ("config", "--quiet")
        ):
            return SimpleNamespace(returncode=0, stdout=self.values.get("compose_config", ""), stderr="")
        return None


def disk(free=10 * 1024 * 1024 * 1024):
    return SimpleNamespace(free=free)


def ready_preflight(_root):
    return {"state": "ready", "recovery_actions": []}


def test_doctor_reports_ready_without_external_configuration(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", ready_preflight)
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: True)
    monkeypatch.setattr(DOCTOR, "_candidate_from_plan", lambda _root: "a" * 40)
    runner = Runner({
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "status", "--porcelain"): "",
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.0\n",
        ("docker", "compose", "version"): "Docker Compose v2\n",
    })
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=runner, disk_usage=lambda _: disk())
    assert report["state"] == "ready"
    assert not report["safe_next_commands"]
    _, env = next((call for call in runner.calls if call[0] == ("docker", "version", "--format", "{{.Server.Version}}"))
    )
    assert "DOCKER_HOST" not in env
    assert "DOCKER_CONTEXT" not in env
    assert "COMPOSE_PROFILES" not in env
    assert "COMPOSE_FILE" not in env


def test_doctor_reports_diagnostic_failures_without_remediation(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", lambda _: {"state": "not-ready", "recovery_actions": ["missing-local-health-check"]})
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: False)
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=Runner({}), disk_usage=lambda _: disk(1))
    assert report["state"] == "blocked"
    assert {
        "candidate-checkout-mismatch",
        "docker-daemon-unavailable",
        "docker-compose-plugin-unavailable",
        "loopback-port-in-use",
        "insufficient-disk-space",
        "missing-local-health-check",
    } <= set(report["blocked"])
    assert all("docker compose up" not in command for command in report["safe_next_commands"])


def test_candidate_is_loaded_from_current_top_completion_claim():
    candidate = DOCTOR._candidate_from_plan(ROOT)
    assert len(candidate) == 40
    assert all(character in "0123456789abcdef" for character in candidate)


def test_doctor_defaults_port_from_agentos_port(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", ready_preflight)
    monkeypatch.setenv("AGENTOS_PORT", "9911")
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: True)
    monkeypatch.setattr(DOCTOR, "_candidate_from_plan", lambda _root: "a" * 40)
    runner = Runner({
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "status", "--porcelain"): "",
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.0\n",
        ("docker", "compose", "version"): "Docker Compose v2\n",
    })
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=runner, disk_usage=lambda _: disk())
    assert report["state"] == "ready"
    assert report["port"] == 9911


def test_doctor_recommends_safe_candidate_checkout_when_mismatched(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", ready_preflight)
    monkeypatch.setattr(DOCTOR, "_candidate_from_plan", lambda _root: "a" * 40)
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: True)
    runner = Runner({
        ("git", "rev-parse", "HEAD"): "b" * 40 + "\n",
        ("git", "status", "--porcelain"): "",
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.0\n",
        ("docker", "compose", "version"): "Docker Compose v2\n",
    })
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=runner, disk_usage=lambda _: disk())
    assert report["state"] == "blocked"
    assert report["checks"]["candidate_checkout"] is False
    assert any("git worktree add --detach" in cmd for cmd in report["safe_next_commands"])


def test_candidate_request_rejects_non_plan_immutable_candidate(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", ready_preflight)
    monkeypatch.setattr(DOCTOR, "_candidate_from_plan", lambda _root: "c" * 40)
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: True)
    runner = Runner({
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "status", "--porcelain"): "",
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.0\n",
        ("docker", "compose", "version"): "Docker Compose v2\n",
    })
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=runner, disk_usage=lambda _: disk())
    assert report["state"] == "blocked"
    assert "candidate-not-top-supported" in report["blocked"]
    assert report["checks"]["candidate_supported"] is False


def test_supported_candidate_is_accepted_when_matching_plan(monkeypatch):
    monkeypatch.setattr(DOCTOR.operating_preflight, "inspect", ready_preflight)
    monkeypatch.setattr(DOCTOR, "_candidate_from_plan", lambda _root: "a" * 40)
    monkeypatch.setattr(DOCTOR, "_port_available", lambda _: True)
    runner = Runner({
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "status", "--porcelain"): "",
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.0\n",
        ("docker", "compose", "version"): "Docker Compose v2\n",
    })
    report = DOCTOR.inspect(ROOT, "a" * 40, runner=runner, disk_usage=lambda _: disk())
    assert report["state"] == "ready"
    assert report["checks"]["candidate_supported"] is True


# -- installation / route diagnostics (AX-11, #603) ---------------------------
# Model-free: the only processes started are the inspected build's own
# one-shot stdio bridges against a disposable data folder.

import json
import shutil
import sys


def no_process(command, root, env=None):
    """Runner for git/lsof/ps: git answers, nothing is listening."""
    if tuple(command[:2]) == ("git", "rev-parse"):
        return SimpleNamespace(returncode=0, stdout="f" * 40 + "\n", stderr="")
    if tuple(command[:2]) == ("git", "status"):
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return SimpleNamespace(returncode=1, stdout="", stderr="")


def fake_install(tmp_path, suffix=""):
    """A copy of this checkout's package, optionally edited, on its own path."""
    site = tmp_path / "site"
    shutil.copytree(ROOT / "src" / "personal_agent", site / "personal_agent",
                    ignore=shutil.ignore_patterns("__pycache__"))
    if suffix:
        target = site / "personal_agent" / "bounded_execution.py"
        target.write_text(target.read_text(encoding="utf-8") + suffix, encoding="utf-8")
    return site


def installation(site, **options):
    return DOCTOR.inspect_installation(ROOT, interpreter=sys.executable, runner=options.pop("runner", no_process),
                                       extra_env={"PYTHONPATH": str(site)}, **options)


def test_matching_installation_is_current_and_reports_every_route(tmp_path):
    report = installation(fake_install(tmp_path))
    assert report["installed"]["package_digest"] == report["source"]["package_digest"] != "unknown"
    assert "installed-package-differs-from-source" not in report["findings"]
    routes = report["routes"]
    assert routes["exposure_of"] == "installed"
    assert "weather" in routes["direct-api-declared"]
    assert routes["isolated-cli-mcp"] == ["list_notes"]
    assert "running-process" in report["unknown"]
    assert report["state"] == "unknown", "no listener observed stays unknown, not current"


def test_wheel_shaped_install_without_checkout_only_files_matches_source(tmp_path):
    """A wheel ships modules and web/*.html|css|js only (pyproject package-data)."""
    site = fake_install(tmp_path)
    (site / "personal_agent" / "web" / "AGENTS.md").unlink()
    report = installation(site)
    assert "installed-package-differs-from-source" not in report["findings"]
    assert report["installed"]["package_digest"] == report["source"]["package_digest"]


def test_deliberately_stale_build_is_identified_without_a_model(tmp_path):
    report = installation(fake_install(tmp_path, "\n# an older build\n"))
    assert report["state"] == "stale"
    assert "installed-package-differs-from-source" in report["findings"]
    assert report["installed"]["origin"] == "other"


def test_deliberately_missing_binding_is_identified(tmp_path):
    drop = "\nMCP_TOOLS = tuple(tool for tool in MCP_TOOLS if tool['name'] != 'web_search')\n"
    report = installation(fake_install(tmp_path, drop))
    assert "web_search" not in report["routes"]["bounded-cli-mcp"]
    missing = next(item for item in report["findings"]
                   if isinstance(item, dict) and item.get("missing-public-read-binding") == "bounded-cli-mcp")
    assert "web_search" in missing["actions"]


def test_wire_check_rejects_python_style_schema_and_accepts_mcp_form():
    good = {"name": "t", "description": "d", "inputSchema": {"type": "object", "properties": {}}}
    bad = {"name": "u", "input_schema": {"type": "object", "properties": {}}}
    assert DOCTOR.mcp_wire_problems([good]) == []
    assert {problem["problem"] for problem in DOCTOR.mcp_wire_problems([bad])} == {"non-wire-fields", "missing-inputSchema"}


def listening_since(epoch):
    import time as _time

    def runner(command, root, env=None):
        if command[0] == "lsof":
            return SimpleNamespace(returncode=0, stdout="4242\n", stderr="")
        if command[0] == "ps":
            return SimpleNamespace(returncode=0, stdout=_time.strftime("%a %b %d %H:%M:%S %Y", _time.localtime(epoch)) + "\n", stderr="")
        return no_process(command, root, env)
    return runner


def test_running_process_older_than_the_code_is_stale(tmp_path):
    report = installation(fake_install(tmp_path), runner=listening_since(946684800))  # 2000-01-01
    assert report["running_process"] == {"observed": True, "started_before_newest_package_file": True}
    assert "running-process-predates-package-files" in report["findings"]
    assert report["state"] == "stale"


def test_running_process_newer_than_the_code_is_not_stale(tmp_path):
    report = installation(fake_install(tmp_path), runner=listening_since(4102444800))  # 2100-01-01
    assert "running-process-predates-package-files" not in report["findings"]
    assert report["state"] == "current"


def test_recorded_turns_are_read_only_and_unknown_builds_stay_unknown(tmp_path):
    from personal_agent.quickstart_store import QuickStore
    store = QuickStore(tmp_path / "data")
    store.put_turn_provenance("old", {"route": "subscription", "engine": "codex", "mode": "bounded-agentos-mcp"})
    database = tmp_path / "data" / "private" / "quickstart.db"
    before = database.read_bytes()
    report = installation(fake_install(tmp_path), data=str(tmp_path / "data"))
    assert database.read_bytes() == before, "the owner database is opened read-only"
    assert report["recorded_turns"][0]["build_digest"] == "unknown"
    assert report["recorded_turns"][0]["exposed_tools"] == "unknown"
    assert "last-recorded-turn-ran-a-different-build" not in report["findings"]
    store.put_turn_provenance("new", {"route": "subscription", "exposed_tools": ["list_notes"],
                                      "build": {"package_digest": "0" * 64, "origin": "source-checkout"}})
    report = installation(fake_install(tmp_path / "second"), data=str(tmp_path / "data"))
    assert "last-recorded-turn-ran-a-different-build" in report["findings"]
    assert report["state"] == "stale"


def test_installation_report_exports_no_paths(tmp_path):
    site = fake_install(tmp_path, "\n# stale\n")
    report = json.dumps(installation(site, data=str(tmp_path)))
    for private in (str(tmp_path), str(ROOT), str(Path.home())):
        assert private not in report
