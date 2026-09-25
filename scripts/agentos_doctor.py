#!/usr/bin/env python3
"""Report whether this checkout is safe for an owner to begin local setup.

The doctor is diagnostic only: it never starts Compose, changes Docker state,
reads credentials, or contacts a provider.

``--installation`` (#603) instead compares this checkout's source, the
installed ``personal_agent`` package and the process listening on the loopback
port, and lists the tools each route actually exposes.  ``--data`` adds the
redacted route/build facts of recently recorded turns, opened read-only.
"""
import argparse
from contextlib import closing
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import operating_preflight

MIN_FREE_BYTES = 5 * 1024 * 1024 * 1024


def _run(command, root, env=None):
    try:
        return subprocess.run(
            command, cwd=root, text=True, capture_output=True, timeout=10, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _candidate_from_plan(root):
    plan = json.loads((root / "delivery-plan.yaml").read_text(encoding="utf-8"))
    return plan["completion_claims"]["TOP"]["deployment_candidate"]["commit"]


def _git_head(runner, root, env):
    head = runner(["git", "rev-parse", "HEAD"], root, env=env)
    return head.stdout.strip() if head and head.returncode == 0 else None


def _compose_loopback_port(root):
    compose = root / "compose.yaml"
    if not compose.is_file():
        return None
    text = compose.read_text(encoding="utf-8")
    match = re.search(r'(?m)^    ports:\n(?:      - .*?\n)+', text)
    if not match:
        return None
    block = match.group(0)
    bound = re.search(r'(?m)^      - "127\.0\.0\.1:([^:"]+):8787"\s*$', block)
    if bound:
        raw = bound.group(1).strip()
    else:
        return None
    if raw.startswith("${AGENTOS_PORT:-") and raw.endswith("}"):
        return int(os.environ.get("AGENTOS_PORT", raw.split(":-", 1)[1][:-1]))
    try:
        return int(raw)
    except ValueError:
        return None


def _diagnostic_environment(temporary):
    environment = os.environ.copy()
    environment.pop("HOME", None)
    environment.pop("DOCKER_HOST", None)
    environment.pop("DOCKER_CONTEXT", None)
    environment.pop("COMPOSE_PROFILES", None)
    environment.pop("COMPOSE_FILE", None)
    environment["HOME"] = str(temporary / "home")
    Path(environment["HOME"]).mkdir(parents=True, exist_ok=True)
    docker_config = temporary / "docker-config"
    docker_config.mkdir()
    (docker_config / "config.json").write_text("{}", encoding="utf-8")
    environment["DOCKER_CONFIG"] = str(docker_config)
    return environment


def inspect(root, candidate=None, port=None, runner=_run, disk_usage=shutil.disk_usage):
    root = Path(root).resolve()
    plan_candidate = _candidate_from_plan(root)
    configured_candidate = plan_candidate if candidate is None else candidate
    candidate_requested = candidate is not None
    checks, blocked, actions = {}, [], []

    with tempfile.TemporaryDirectory(prefix="agentos-doctor-") as temporary:
        temporary = Path(temporary)
        environment = _diagnostic_environment(temporary)
        env_file = temporary / "agentos-empty.env"
        env_file.write_text("", encoding="utf-8")

        head = _git_head(runner, root, env=environment)
        checks["candidate_checkout"] = bool(head and head == configured_candidate)
        checks["candidate_supported"] = True if not candidate_requested else candidate == plan_candidate
        if candidate_requested and not checks["candidate_supported"]:
            blocked.append("candidate-not-top-supported")
            actions.append(
                f"Only the immutable TOP deployment candidate is supported: {plan_candidate}; "
                "remove --candidate to use the default supported target"
            )
        if not checks["candidate_checkout"]:
            blocked.append("candidate-checkout-mismatch")
            safe_candidate = plan_candidate if candidate_requested and not checks["candidate_supported"] else configured_candidate
            actions.append(
                "git worktree add --detach /tmp/agentos-doctor-checkout "
                f"{safe_candidate} && cp scripts/agentos_doctor.py /tmp/agentos-doctor-checkout/scripts/agentos_doctor.py && "
                f"python3 /tmp/agentos-doctor-checkout/scripts/agentos_doctor.py --root /tmp/agentos-doctor-checkout --candidate {safe_candidate}"
            )

        dirty = runner(["git", "status", "--porcelain"], root, env=environment)
        checks["clean_checkout"] = bool(
            dirty and dirty.returncode == 0 and not dirty.stdout.strip()
        )
        if not checks["clean_checkout"]:
            blocked.append("checkout-has-uncommitted-changes")
            actions.append("commit, stash, or discard only your own checkout changes before setup")

        docker = runner(
            ["docker", "version", "--format", "{{.Server.Version}}"], root, environment
        )
        checks["docker_daemon"] = bool(docker and docker.returncode == 0 and docker.stdout.strip())
        if not checks["docker_daemon"]:
            blocked.append("docker-daemon-unavailable")
            actions.append("start Docker Desktop, then rerun agentos_doctor.py")

        compose = runner(["docker", "compose", "version"], root, environment)
        checks["compose_plugin"] = bool(compose and compose.returncode == 0)
        if not checks["compose_plugin"]:
            blocked.append("docker-compose-plugin-unavailable")
            actions.append("install or enable the Docker Compose plugin")

        if checks["docker_daemon"] and checks["compose_plugin"]:
            config = runner(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env_file),
                    "-f",
                    "compose.yaml",
                    "config",
                    "--quiet",
                ],
                root,
                environment,
            )
            checks["compose_config"] = bool(config and config.returncode == 0)
            if not checks["compose_config"]:
                blocked.append("compose-config-invalid")
                actions.append("inspect compose.yaml and rerun doctor; do not start the stack")
        else:
            checks["compose_config"] = False

    if port is None:
        port = int(os.environ.get("AGENTOS_PORT", 8787))
    checks["loopback_port_available"] = _port_available(port)
    if not checks["loopback_port_available"]:
        blocked.append("loopback-port-in-use")
        actions.append(f"choose an unused local AGENTOS_PORT instead of {port}")

    compose_port = _compose_loopback_port(root)
    checks["compose_loopback_port_match"] = True if compose_port is None else compose_port == port
    if compose_port is not None and compose_port != port:
        blocked.append("compose-loopback-port-mismatch")
        actions.append(
            f"set --port {compose_port} (or AGENTOS_PORT={compose_port}) to match compose binding"
        )

    free = disk_usage(root).free
    checks["sufficient_disk_space"] = free >= MIN_FREE_BYTES
    if not checks["sufficient_disk_space"]:
        blocked.append("insufficient-disk-space")
        actions.append("free at least 5 GiB before building local images")

    checks["plan_candidate"] = plan_candidate
    checks["configured_candidate"] = configured_candidate
    checks["candidate_requested"] = candidate_requested

    preflight = operating_preflight.inspect(root)
    checks["agentos_preflight"] = preflight["state"] == "ready"
    if not checks["agentos_preflight"]:
        blocked.extend(preflight["recovery_actions"])
        actions.append("run python3 scripts/operating_preflight.py --root . for structural recovery details")

    return {
        "state": "ready" if not blocked else "blocked",
        "candidate": configured_candidate,
        "port": port,
        "checks": checks,
        "blocked": blocked,
        "safe_next_commands": actions,
        "deferred_owner_actions": [
            "explicit operating-deployment approval",
            "set approved exact provider DNS allowlist",
            "run docker compose up -d --build after explicit approval",
            "claim the local runtime",
            "complete official engine login",
            "optionally enter Telegram token and OAuth settings",
            "observe health and one live task",
        ],
        "security_note": "No credential, Docker credential helper, owner-home file, provider, Telegram, OAuth, DNS, or TLS endpoint was read or contacted.",
    }


# -- installation / route diagnostics (AX-11, #603) ---------------------------
#
# Read-only and model-free.  It never restarts or reinstalls AgentOS, never
# writes owner data or configuration, never reads a credential and never makes
# a provider or model request.  The only processes it starts are one-shot
# stdio MCP bridges of the inspected build answering ``tools/list`` against a
# disposable data folder; they bind no port and exit at end of input.  Paths
# are never reported: only digests, origin classes and tool names.

#: The public-read group the target full profile requires on every qualified
#: route (docs/assistant-execution-contract.en.md, "Capability profiles").
PUBLIC_READ_ACTIONS = ("weather", "web_search", "public_page_read")

_INSTALL_PROBE = r'''
import importlib.util, json, sys
spec = importlib.util.find_spec("personal_agent")
locations = list(spec.submodule_search_locations or ()) if spec else []
version = editable = None
try:
    from importlib.metadata import distribution
    dist = distribution("personal-agentos")
    version = dist.version
    raw = dist.read_text("direct_url.json")
    if raw:
        editable = bool(json.loads(raw).get("dir_info", {}).get("editable"))
except Exception:
    pass
print(json.dumps({"package_dir": locations[0] if locations else None, "version": version, "editable": editable}))
'''

_NATIVE_PROBE = (
    "import json; from personal_agent.agent_runtime import DEFINITIONS; "
    "print(json.dumps(sorted(d['function']['name'] for d in DEFINITIONS)))"
)


def _probe(argv, env, stdin_text=None, cwd=None):
    try:
        completed = subprocess.run(
            argv, input=stdin_text, text=True, capture_output=True, timeout=30, env=env, cwd=cwd
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _json_or_none(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def _tools_list(interpreter, module, args, env, cwd, probe):
    requests = "\n".join(json.dumps(item) for item in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )) + "\n"
    output = probe([interpreter, "-m", module, *args], env, requests, cwd)
    for line in (output or "").splitlines():
        reply = _json_or_none(line)
        if isinstance(reply, dict) and reply.get("id") == 2 and isinstance(reply.get("result"), dict):
            tools = reply["result"].get("tools")
            return tools if isinstance(tools, list) else None
    return None


def mcp_wire_problems(tools):
    """Name each advertised tool that is not a valid MCP ``Tool`` on the wire.

    Uses the already adopted ``mcp_types`` model (#426) by its wire aliases
    only: ``populate_by_name`` would accept a Python-style ``input_schema``
    that an MCP client reading ``inputSchema`` never sees.
    """
    try:
        from mcp_types import Tool
    except ImportError:
        return None
    aliases = {field.alias or name for name, field in Tool.model_fields.items()}
    problems = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(tool, dict):
            problems.append({"tool": None, "problem": "not-an-object"})
            continue
        unknown = sorted(set(tool) - aliases)
        schema = tool.get("inputSchema")
        if unknown:
            problems.append({"tool": name, "problem": "non-wire-fields", "fields": unknown})
        if not isinstance(schema, dict) or schema.get("type") != "object":
            problems.append({"tool": name, "problem": "missing-inputSchema"})
    return problems


def _listening_process_started(port, runner, env):
    """Start time (epoch) of the process listening on the loopback port, or None."""
    listed = runner(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], ROOT, env=env)
    pids = [line.strip() for line in (listed.stdout if listed and listed.returncode == 0 else "").splitlines() if line.strip().isdigit()]
    if not pids:
        return None
    started = runner(["ps", "-o", "lstart=", "-p", pids[0]], ROOT, env=env)
    if not started or started.returncode != 0 or not started.stdout.strip():
        return None
    try:
        return time.mktime(time.strptime(" ".join(started.stdout.split()), "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        return None


def _latest_mtime(directory, shipped):
    """Newest modification time among the files the digest covers."""
    root = Path(directory)
    try:
        return max(path.stat().st_mtime for path in root.rglob("*") if path.is_file() and shipped(root, path))
    except (OSError, ValueError):
        return None


def _recent_turns(data, limit=5):
    """Redacted route/build facts of the newest recorded turns, read-only."""
    database = Path(data) / "private" / "quickstart.db"
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT record FROM turn_provenance ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()
    except sqlite3.Error:
        return None
    turns = []
    for (raw,) in rows:
        record = _json_or_none(raw)
        if not isinstance(record, dict):
            continue
        build = record.get("build") if isinstance(record.get("build"), dict) else {}
        turns.append({
            "route": record.get("route"),
            "engine": record.get("engine"),
            "mode": record.get("mode"),
            "status": record.get("status"),
            "exposed_tools": record.get("exposed_tools") if isinstance(record.get("exposed_tools"), list) else "unknown",
            "build_digest": build.get("package_digest") or "unknown",
            "build_origin": build.get("origin") or "unknown",
        })
    return turns


def inspect_installation(root=ROOT, interpreter=None, data=None, port=None,
                         runner=_run, probe=_probe, extra_env=None):
    """Compare source, installed and running identity plus each route's tools."""
    source_path = str(Path(root).resolve() / "src")
    if source_path not in sys.path:
        sys.path.insert(0, source_path)
    from personal_agent.service_control import shipped_file, package_digest, package_origin

    root = Path(root).resolve()
    findings, unknown = [], []
    with tempfile.TemporaryDirectory(prefix="agentos-doctor-install-") as temporary:
        temporary = Path(temporary)
        # Only what path resolution needs: no inherited AgentOS/provider
        # variables (tokens, endpoints, PYTHONPATH) reach a probed process.
        # HOME stays real because a user-site installation resolves from it.
        env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": os.environ.get("HOME", str(temporary)), "LC_ALL": "C"}
        env.update(extra_env or {})

        head = _git_head(runner, root, env)
        dirty = runner(["git", "status", "--porcelain", "--", "src/personal_agent"], root, env=env)
        source_digest = package_digest(root / "src" / "personal_agent")
        source = {
            "revision": head or "unknown",
            "package_changed_since_revision": (bool(dirty.stdout.strip()) if dirty and dirty.returncode == 0 else "unknown"),
            "package_digest": source_digest or "unknown",
        }

        installed = {"interpreter": "given" if interpreter else "not-found"}
        package_dir = None
        if interpreter:
            reported = _json_or_none(probe([interpreter, "-c", _INSTALL_PROBE], env, None, str(temporary)))
            package_dir = reported.get("package_dir") if isinstance(reported, dict) else None
            installed.update({
                "origin": package_origin(package_dir) if package_dir else "unknown",
                "distribution_version": (reported or {}).get("version") or "unknown",
                "editable": (reported or {}).get("editable") if (reported or {}).get("editable") is not None else "unknown",
                "package_digest": (package_digest(package_dir) if package_dir else None) or "unknown",
            })
            if installed["package_digest"] == "unknown":
                unknown.append("installed-package")
            elif source_digest and installed["package_digest"] != source_digest:
                findings.append("installed-package-differs-from-source")
        else:
            unknown.append("installed-package")

        # Route exposure of the build that would actually run: the installed
        # one when found, otherwise this checkout's source.
        if package_dir:
            exposure_env, exposure_of = env, "installed"
        else:
            exposure_env, exposure_of = {**env, "PYTHONPATH": str(root / "src")}, "source"
        exposure_python = interpreter or sys.executable
        data_folder = temporary / "bridge-data"
        bridge = _tools_list(exposure_python, "personal_agent.mcp_bridge",
                             ["--data", str(data_folder), "--job", "doctor-exposure"], exposure_env, str(temporary), probe)
        isolated = _tools_list(exposure_python, "personal_agent.isolated_engine_mcp_bridge",
                               ["--callback", "http://127.0.0.1:9/doctor", "--token", "doctor", "--task-id", "doctor"],
                               exposure_env, str(temporary), probe)
        native = _json_or_none(probe([exposure_python, "-c", _NATIVE_PROBE], exposure_env, None, str(temporary)))

    def names(tools):
        return sorted(tool.get("name") for tool in tools if isinstance(tool, dict)) if isinstance(tools, list) else "unknown"

    routes = {
        "exposure_of": exposure_of,
        "direct-api-declared": native if isinstance(native, list) else "unknown",
        "bounded-cli-mcp": names(bridge),
        "isolated-cli-mcp": names(isolated),
    }
    for route in ("bounded-cli-mcp", "isolated-cli-mcp"):
        offered = routes[route]
        if offered == "unknown":
            unknown.append(route)
            continue
        missing = [action for action in PUBLIC_READ_ACTIONS if action not in offered]
        if missing:
            findings.append({"missing-public-read-binding": route, "actions": missing})
    wire = {}
    for route, tools in (("bounded-cli-mcp", bridge), ("isolated-cli-mcp", isolated)):
        if isinstance(tools, list):
            problems = mcp_wire_problems(tools)
            wire[route] = problems if problems is not None else "unknown"
            if problems:
                findings.append({"mcp-tool-list-not-wire-conformant": route, "tools": sorted({p["tool"] or "?" for p in problems})})
    routes["mcp_wire_problems"] = wire

    running = {"observed": False}
    started = _listening_process_started(port or int(os.environ.get("AGENTOS_PORT", 8787)), runner, env)
    code_dir = package_dir or (root / "src" / "personal_agent")
    newest = _latest_mtime(code_dir, shipped_file)
    if started is None:
        unknown.append("running-process")
    else:
        running = {"observed": True,
                   "started_before_newest_package_file": (started < newest) if newest else "unknown"}
        if newest and started < newest:
            findings.append("running-process-predates-package-files")

    turns = _recent_turns(data) if data else None
    if data and turns is None:
        unknown.append("recorded-turns")
    reference = installed.get("package_digest") if package_dir else source_digest
    for turn in turns or ():
        if turn["build_digest"] == "unknown":
            continue
        if reference and turn["build_digest"] != reference:
            findings.append("last-recorded-turn-ran-a-different-build")
            break

    stale = {"installed-package-differs-from-source", "running-process-predates-package-files",
             "last-recorded-turn-ran-a-different-build"}
    # `build_state` is about identity only; route bindings are `findings`.
    # `current` needs both the installed package and a listening process to
    # have been observed; either missing leaves the state unknown.
    if any(isinstance(item, str) and item in stale for item in findings):
        build_state = "stale"
    elif {"installed-package", "running-process"} & set(unknown):
        build_state = "unknown"
    else:
        build_state = "current"
    return {
        "state": build_state,
        "source": source,
        "installed": installed,
        "running_process": running,
        "routes": routes,
        "recorded_turns": turns if data else "not-requested",
        "findings": findings,
        "unknown": sorted(set(unknown)),
        "evidence": "model-free local diagnostic; no restart, reinstall, owner-config write, credential read or provider request",
    }


def _installed_interpreter():
    """Interpreter named by the installed ``agentos`` entry point, if any."""
    executable = shutil.which("agentos")
    if not executable:
        return None
    try:
        with open(executable, "rb") as stream:
            first = stream.readline(512).decode("utf-8", "replace").strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    if not parts:
        return None
    if Path(parts[0]).name == "env" and len(parts) > 1:
        return shutil.which(parts[1])
    return parts[0] if Path(parts[0]).name.startswith("python") else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--candidate", help="expected immutable deployment candidate SHA")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--installation", action="store_true",
                        help="report source/installed/running build identity and per-route tool exposure (#603)")
    parser.add_argument("--interpreter", help="python of the installation to inspect (default: the installed agentos entry point)")
    parser.add_argument("--data", help="AgentOS data folder whose recorded turn provenance to read, read-only")
    args = parser.parse_args(argv)
    if args.installation:
        report = inspect_installation(args.root, args.interpreter or _installed_interpreter(), args.data, args.port)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["state"] == "current" and not report["findings"] else 1
    report = inspect(args.root, args.candidate, args.port)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["state"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
