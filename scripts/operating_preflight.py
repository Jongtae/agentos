"""Exercise credential-free product paths and fail closed on unsafe deployment gaps."""
import argparse
import json
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

REQUIRED_SCRIPTS = ("compose-backup.sh", "compose-restore.sh", "compose-update.sh")


def _wait_for_http_handler(url: str, timeout: float = 2.0) -> None:
    """Wait until a bound local server is actually dispatching HTTP requests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urlopen(url, timeout=0.2).read()
            return
        except HTTPError:
            # The probe's service is intentionally not started yet, so its
            # health endpoint returns 503. That still proves handler readiness.
            return
        except OSError:
            time.sleep(0.02)
    raise RuntimeError("local AgentOS HTTP handler did not become ready")


def _product_probe():
    """Run the real isolated gateway/sidecar/MCP, health, and restore path."""
    from personal_agent.isolated_engine_gateway import IsolatedEngineGateway
    from personal_agent.isolated_engine_sidecar import IsolatedEngineSidecar
    from personal_agent.isolated_engine_sidecar import make_handler as make_engine_handler
    from personal_agent.portable_state import export_owner_state, restore_owner_state
    from personal_agent.quickstart import ISOLATED_MCP_PATH
    from personal_agent.quickstart import make_handler as make_agentos_handler
    from personal_agent.quickstart_service import AgentService
    from personal_agent.quickstart_store import QuickStore

    # #1187: a background thread may still write into the scratch folder while it is
    # removed (seen on macOS); leftovers in the temp directory are harmless.
    with tempfile.TemporaryDirectory(prefix="agentos-preflight-", ignore_cleanup_errors=True) as folder:
        root = Path(folder)
        source = QuickStore(root / "source")
        first_claim = not source.claimed() and source.bootstrap.is_file()
        with source.db() as db:
            db.execute("INSERT INTO notes VALUES (?,?,?)", ("fixture-note", "approved fixture note", 1))
        engine = root / "codex"
        engine.write_text(f"""#!{sys.executable}
import json, os, subprocess, sys
assert sys.argv[1:6] == ['exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check']
assert os.listdir('.') == []
settings = {{}}
index = 6
while index < len(sys.argv) - 1:
    assert sys.argv[index] == '-c'
    name, raw = sys.argv[index + 1].split('=', 1)
    settings[name] = json.loads(raw)
    index += 2
p = subprocess.Popen(
    [settings['mcp_servers.agentos.command'], *settings['mcp_servers.agentos.args']],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
)
def rpc(value):
    p.stdin.write(json.dumps(value) + '\\n'); p.stdin.flush()
    return json.loads(p.stdout.readline())
tools = rpc({{'jsonrpc':'2.0','id':1,'method':'tools/list','params':{{}}}})
assert [item['name'] for item in tools['result']['tools']] == ['list_notes']
denied = rpc({{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{{'name':'save_note','arguments':{{'content':'no'}}}}}})
assert denied['error']['code'] == -32601
reply = rpc({{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{{'name':'list_notes','arguments':{{}}}}}})
p.stdin.close(); p.wait(timeout=3)
text = 'fixture engine received ' + reply['result']['content'][0]['text']
print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':text}}}}))
""", encoding="utf-8")
        engine.chmod(engine.stat().st_mode | stat.S_IXUSR)
        sidecar = IsolatedEngineSidecar(
            "http://127.0.0.1:1" + ISOLATED_MCP_PATH,
            codex_binary=str(engine), timeout=5,
        )
        engine_server = ThreadingHTTPServer(("127.0.0.1", 0), make_engine_handler(sidecar))
        engine_thread = threading.Thread(target=engine_server.serve_forever, daemon=True)
        engine_thread.start()
        gateway = IsolatedEngineGateway(
            f"http://127.0.0.1:{engine_server.server_port}/execute", timeout=8,
        )
        service = AgentService(
            source,
            isolated_engine_adapter=gateway,
        )
        agentos_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_agentos_handler(service),
        )
        agentos_thread = threading.Thread(target=agentos_server.serve_forever, daemon=True)
        agentos_thread.start()
        try:
            _wait_for_http_handler(f"http://127.0.0.1:{agentos_server.server_port}/healthz")
            sidecar.callback_url = (
                f"http://127.0.0.1:{agentos_server.server_port}" + ISOLATED_MCP_PATH
            )
            source.put("subscription_engine", {
                "id": "codex",
                "connected_at": 0,
                "authentication": "fixture-only-no-login",
            })
            completed = source.enqueue("/summarize", "fixture-completed")
            executed = service.run_one()
            result = source.job(completed)
            engine_round_trip = (
                executed
                and result["status"] == "succeeded"
                and "approved fixture note" in result["response"]
            )
        finally:
            agentos_server.shutdown()
            agentos_server.server_close()
            agentos_thread.join(timeout=2)
            engine_server.shutdown()
            engine_server.server_close()
            engine_thread.join(timeout=2)

        health_service = AgentService(source)
        health_service.start()
        local_health = health_service.healthy()
        health_service.stop.set()
        for thread in health_service.threads:
            thread.join(timeout=2)
        stopped = not health_service.healthy()

        queued = source.enqueue("queued before backup", "fixture-queued")
        running = source.enqueue("running before backup", "fixture-running")
        with source.db() as db:
            db.execute("UPDATE jobs SET status='running', delivery='sending' WHERE id=?", (running,))
        archive = export_owner_state(source.root, root / "owner.tar.gz")
        restored_path = restore_owner_state(archive, root / "restored")
        restored = QuickStore(restored_path)
        quarantined = all(restored.job(ident)["status"] == "interrupted" for ident in (queued, running))
        duplicate_safe = restored.enqueue("queued before backup", "fixture-queued") == queued
        replay_safe = not AgentService(restored).run_one()
        profile_excluded = not (restored_path / "engine-profile").exists() and restored.config("subscription_engine") is None

    return {
        "first_claim": first_claim,
        "local_health": local_health,
        "clean_stop": stopped,
        "isolated_engine_gateway_sidecar_mcp_round_trip": engine_round_trip,
        "restore_quarantines_incomplete_work": quarantined,
        "restored_request_is_duplicate_safe": duplicate_safe and replay_safe,
        "engine_profile_excluded_from_restore": profile_excluded,
    }


def inspect(root, product_probe=None):
    """Return a secret-free readiness report without Docker or credentials."""
    root = Path(root).resolve()
    failures = []
    pyproject, compose, dockerfile = root / "pyproject.toml", root / "compose.yaml", root / "Dockerfile"
    version = None
    if pyproject.exists():
        matched = re.search(r'^version\s*=\s*"([^"]+)"\s*$', pyproject.read_text(encoding="utf-8"), re.M)
        version = matched.group(1) if matched else None
    if not version:
        failures.append("missing-project-version")
    compose_text = compose.read_text(encoding="utf-8") if compose.exists() else ""
    docker_text = dockerfile.read_text(encoding="utf-8") if dockerfile.exists() else ""
    egress_dockerfile = root / "Dockerfile.egress"
    egress_docker_text = egress_dockerfile.read_text(encoding="utf-8") if egress_dockerfile.exists() else ""
    proxy_source = root / "src" / "personal_agent" / "limited_egress_proxy.py"
    proxy_text = proxy_source.read_text(encoding="utf-8") if proxy_source.exists() else ""

    def service_section(name):
        matched = re.search(
            rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_.-]+:\n|^[A-Za-z])",
            compose_text,
        )
        return matched.group("body") if matched else ""

    def service_list(section, name):
        matched = re.search(
            rf"(?m)^    {re.escape(name)}:\n(?P<items>(?:      - .*\n)+)",
            section,
        )
        if not matched:
            return []
        return [
            line.removeprefix("      - ").strip().strip('"')
            for line in matched.group("items").splitlines()
        ]

    agentos_section = service_section("agentos")
    engine_section = service_section("engine")
    egress_section = service_section("egress-proxy")
    network_text = compose_text.partition("\nnetworks:\n")[2].partition("\nvolumes:\n")[0]
    engine_network_internal = re.search(
        r"(?ms)^  engine-internal:\s*\n(?:(?:    .*)\n)*?    internal:\s*true\s*$",
        network_text,
    )
    provider_network = re.search(r"(?m)^  provider-egress:\s*$", network_text)
    provider_network_internal = re.search(
        r"(?ms)^  provider-egress:\s*\n(?:(?:    .*)\n)*?    internal:\s*true\s*$",
        network_text,
    )
    isolated_engine = all((
        re.search(r"(?m)^  engine:\s*$", compose_text) is not None,
        "AGENTOS_ISOLATED_ENGINE_URL: http://engine:8766/execute" in compose_text,
        "personal_agent.isolated_engine_sidecar" in engine_section,
        "http://agentos:8787/internal/isolated-engine/mcp" in engine_section,
        len(re.findall(r"(?m)^    volumes:\s*$", engine_section)) == 1,
        service_list(engine_section, "volumes") == ["agentos-engine-profile:/engine-profile"],
        re.search(r"(?m)^    (?:ports|expose|network_mode):", engine_section) is None,
        "read_only: true" in engine_section,
        service_list(engine_section, "networks") == ["engine-internal"],
        engine_network_internal is not None,
    ))
    egress_policy = all((
        bool(egress_section),
        "HTTPS_PROXY: http://egress-proxy:3128" in engine_section,
        "HTTP_PROXY: http://egress-proxy:3128" in engine_section,
        "NO_PROXY: agentos,localhost,127.0.0.1" in engine_section,
        service_list(egress_section, "networks") == ["engine-internal", "provider-egress"],
        "provider-egress" not in agentos_section,
        re.search(r"(?m)^    (?:ports|expose|volumes|network_mode):", egress_section) is None,
        "AGENTOS_PROVIDER_EGRESS_ALLOWLIST: ${AGENTOS_PROVIDER_EGRESS_ALLOWLIST:-}" in egress_section,
        provider_network is not None,
        provider_network is not None and provider_network_internal is None,
        "dockerfile: Dockerfile.egress" in egress_section,
        "personal_agent.limited_egress_proxy" in egress_docker_text,
        "parse_allowlist" in proxy_text and "hostname not in self.server.allowed_hosts" in proxy_text,
    ))
    required_structural = {
        "loopback_binding": '127.0.0.1:${AGENTOS_PORT:-8787}:8787' in compose_text,
        "separate_owner_volume": "agentos-data:/state" in compose_text and "agentos-data:" in compose_text,
        "separate_engine_profile_volume": "agentos-engine-profile:/engine-profile" in compose_text and "agentos-engine-profile:" in compose_text,
        "nonroot_runtime": "USER agentos" in docker_text,
        "local_health_check": "healthcheck:" in compose_text and "/healthz" in compose_text,
        "recovery_scripts": all((root / "scripts" / script).is_file() for script in REQUIRED_SCRIPTS),
        "subscription_engine_isolated": isolated_engine,
        "isolated_engine_external_egress_policy": egress_policy,
    }
    raw_allowlist = os.environ.get("AGENTOS_PROVIDER_EGRESS_ALLOWLIST", "")
    invalid_allowlist = False
    try:
        from personal_agent.limited_egress_proxy import parse_allowlist
        allowlist_configured = bool(parse_allowlist(raw_allowlist))
    except (ImportError, ValueError):
        invalid_allowlist = True
        allowlist_configured = False
    observations = {
        "provider_egress_allowlist_configured": allowlist_configured,
        # Static architecture and owner configuration are not live provider evidence.
        "provider_egress_reachable": False,
    }
    failure_names = {
        "loopback_binding": "unsafe-or-missing-loopback-binding",
        "separate_owner_volume": "missing-named-owner-volume",
        "separate_engine_profile_volume": "missing-separated-engine-profile-volume",
        "nonroot_runtime": "missing-nonroot-runtime-user",
        "local_health_check": "missing-local-health-check",
        "recovery_scripts": "missing-recovery-scripts",
        "subscription_engine_isolated": "subscription-engine-isolation-design-required",
        "isolated_engine_external_egress_policy": "isolated-engine-egress-policy-required",
    }
    failures.extend(failure_names[name] for name, passed in required_structural.items() if not passed)
    if invalid_allowlist:
        failures.append("invalid-provider-egress-allowlist")
    try:
        product = (product_probe or _product_probe)()
    except Exception as exc:
        product = {"probe_completed": False, "error_class": type(exc).__name__}
    for name, passed in product.items():
        if name != "error_class" and passed is not True:
            failures.append("product-check-failed-" + name.replace("_", "-"))
    return {
        "state": "ready" if not failures else "not-ready",
        "supported_version": version,
        "execution_path": (
            "isolated-subscription-engine-policy-proxy-owner-configured"
            if allowlist_configured else
            "isolated-subscription-engine-policy-proxy-owner-configuration-deferred"
        ),
        "checks": {**required_structural, **observations, **product},
        "recovery_actions": failures,
        "deferred_owner_gates": ([
            "owner provider egress allowlist operating configuration",
        ] if not allowlist_configured else []) + [
            "explicit operating-deployment approval",
            "local runtime claim",
            "owner-approved engine image build and official login after egress acceptance",
            "optional Telegram token entry and owner pairing",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    report = inspect(args.root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["state"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
