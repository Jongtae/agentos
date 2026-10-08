"""Validate the current Compose image and AgentOS data persistence in isolation."""
import json
import socket
import subprocess
import tempfile
import time
import os
import signal
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def kill_process_group(process, termination_signal):
    try:
        os.killpg(process.pid, termination_signal)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS refuses killpg with EPERM while the exited group leader is an
        # unreaped zombie (#1178). Reap it, then signal the rest of the group.
        process.poll()
        try:
            os.killpg(process.pid, termination_signal)
        except (ProcessLookupError, PermissionError):
            pass


def run(args, *, timeout=600, **kwargs):
    """Run one isolated Compose command and reap its whole process group."""
    process = subprocess.Popen(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        **kwargs,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        kill_process_group(process, signal.SIGTERM)
        # The leader may exit while a child that inherited its process group
        # ignores SIGTERM. Always send SIGKILL after the grace period rather
        # than making it conditional on communicate() timing out again.
        time.sleep(1)
        kill_process_group(process, signal.SIGKILL)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            kill_process_group(process, signal.SIGKILL)
            stdout, stderr = process.communicate()
        detail = ((stdout or "") + "\n" + (stderr or "")).strip()
        raise RuntimeError(
            f"command timed out after {timeout}s; process group was terminated: {' '.join(args)}\n{detail}"
        ) from exc
    if process.returncode:
        detail = ((stdout or "") + "\n" + (stderr or "")).strip()
        raise RuntimeError(detail or f"command failed: {' '.join(args)}")
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def main():
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        project = "agentosvalidation" + str(int(time.time()))
        # This development acceptance must not inherit a developer's provider
        # allowlist or credential-like Compose configuration. The empty policy
        # keeps engine egress default-deny while exercising local lifecycle only.
        # Docker Desktop may block indefinitely in its credential helper even for a
        # public image. Use a new unauthenticated config for this one test only:
        # it neither reads nor modifies the owner's Docker config, keychain, or
        # login. The explicit socket avoids inheriting an unrelated CLI context.
        docker_config = temporary / "docker-config"
        docker_config.mkdir()
        plugin_directory = Path.home() / ".docker" / "cli-plugins"
        config = {"auths": {}}
        if plugin_directory.is_dir():
            config["cliPluginsExtraDirs"] = [str(plugin_directory)]
        (docker_config / "config.json").write_text(json.dumps(config), encoding="utf-8")
        docker_sockets = (Path.home() / ".docker" / "run" / "docker.sock", Path("/var/run/docker.sock"))
        docker_socket = next((candidate for candidate in docker_sockets if candidate.exists()), None)
        if docker_socket is None:
            raise RuntimeError("No supported Docker socket is available for credential-free lifecycle acceptance.")
        environment = {**os.environ, "AGENTOS_PORT": str(port), "COMPOSE_PROJECT_NAME": project,
                       "AGENTOS_PROVIDER_EGRESS_ALLOWLIST": "", "DOCKER_CONFIG": str(docker_config),
                       "DOCKER_HOST": f"unix://{docker_socket}", "COMPOSE_FILE": str(ROOT / "compose.yaml")}
        environment.pop("DOCKER_CONTEXT", None)
        environment.pop("COMPOSE_PROFILES", None)
        compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]
        result = None
        failure = None
        try:
            run([*compose, "up", "--build", "-d"], env=environment)
            for _ in range(90):
                try:
                    if json.load(urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)).get("ok"):
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Compose health check did not become ready.")
            # This uses AgentOS's own persistent store, never the owner's local data.
            run([*compose, "exec", "-T", "agentos", "python", "-c", "import sqlite3,time; c=sqlite3.connect('/data/private/quickstart.db'); c.execute(\"INSERT INTO notes VALUES (?,?,?)\",('compose-persistence-proof','compose-persistence-proof',time.time())); c.commit()"], env=environment)
            run([*compose, "exec", "-T", "agentos", "python", "-c", "import sqlite3,json; c=sqlite3.connect('/data/private/quickstart.db'); c.execute(\"INSERT INTO config VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value\",('telegram',json.dumps({'enabled':True,'generation':'compose-proof','user_id':42}))); c.commit()"], env=environment)
            run([*compose, "down"], env=environment)
            run([*compose, "up", "-d"], env=environment)
            continuity = run([*compose, "exec", "-T", "agentos", "python", "-c", "import sqlite3,json; c=sqlite3.connect('/data/private/quickstart.db'); assert c.execute(\"SELECT 1 FROM notes WHERE content='compose-persistence-proof'\").fetchone(); assert json.loads(c.execute(\"SELECT value FROM config WHERE key='telegram'\").fetchone()[0])['user_id']==42"], env=environment)
            # A portable archive is intentionally secret-free: restore proves state
            # recovery, while the Telegram token/pairing must be re-established.
            temporary.chmod(0o777)
            archive = temporary / "owner-state.tar.gz"
            run([str(ROOT / "scripts" / "compose-backup.sh"), str(archive)], env=environment)
            run([*compose, "down", "--volumes"], env=environment)
            run([str(ROOT / "scripts" / "compose-restore.sh"), str(archive)], env=environment)
            run([*compose, "up", "-d"], env=environment)
            restored = run([*compose, "exec", "-T", "agentos", "python", "-c", "import sqlite3; c=sqlite3.connect('/data/private/quickstart.db'); assert c.execute(\"SELECT 1 FROM notes WHERE content='compose-persistence-proof'\").fetchone(); assert not c.execute(\"SELECT 1 FROM config WHERE key='telegram'\").fetchone()"], env=environment)
            result = {"compose_health": True, "recreated_container": True, "telegram_pairing_continues_on_recreate": continuity.returncode == 0, "portable_restore": restored.returncode == 0, "portable_restore_requires_telegram_reconnection": True, "cleanup": True}
        except BaseException as error:
            failure = error
            raise
        finally:
            try:
                run([*compose, "down", "--volumes", "--remove-orphans"], env=environment, timeout=120)
            except RuntimeError as cleanup_error:
                if failure is None:
                    raise
                print(f"Compose cleanup failed: {cleanup_error}", file=os.sys.stderr)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
