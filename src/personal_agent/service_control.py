"""Deterministic macOS launchd lifecycle control for Personal AgentOS.

Command execution is injectable so tests can inspect the complete lifecycle
without changing the host's launchd state. The existing ``agentos start``
foreground command remains the process entry point used by launchd.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Mapping, Sequence
from urllib.request import urlopen


LABEL = "com.personal-agentos"
DEFAULT_DATA_RELATIVE = Path(".local/share/agentos")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ServiceControlError(RuntimeError):
    """A bounded service failure with an owner-actionable recovery step."""

    def __init__(self, message: str, next_action: str):
        super().__init__(message)
        self.next_action = next_action

    def as_dict(self) -> dict[str, object]:
        return {"ok": False, "background_available": False, "error": str(self), "next_action": self.next_action}


Runner = Callable[[Sequence[str]], CommandResult]
Which = Callable[[str], str | None]
HealthProbe = Callable[..., bool]
ListenerOwner = Callable[[int], bool]


def _run(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _clean_error(result: CommandResult) -> str:
    return " ".join((result.stderr or result.stdout).strip().split())[:300]


def _probe_healthz(timeout: float = 2) -> bool:
    try:
        with urlopen("http://127.0.0.1:8787/healthz", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def resolve_cli_path(
    explicit: str | Path | None = None,
    *,
    which: Which = shutil.which,
    runner: Runner = _run,
) -> Path:
    """Resolve the installed CLI without assuming Intel or Apple Silicon paths."""
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return Path(os.path.abspath(candidate))
        raise ServiceControlError(
            "The selected AgentOS executable is missing or is not executable.",
            "Reinstall Personal AgentOS, then retry with the executable reported by `command -v agentos`.",
        )
    found = which("agentos")
    if found:
        candidate = Path(found).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return Path(os.path.abspath(candidate))
    # Non-interactive launch contexts can have a smaller PATH. Ask Homebrew for
    # its real prefix instead of assuming /opt/homebrew or /usr/local.
    brew = which("brew")
    if brew:
        try:
            prefix = runner([brew, "--prefix"])
        except OSError:
            prefix = CommandResult(127)
        if prefix.returncode == 0 and prefix.stdout.strip():
            candidate = Path(prefix.stdout.strip()) / "bin" / "agentos"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return Path(os.path.abspath(candidate))
    raise ServiceControlError(
        "The installed AgentOS executable could not be resolved.",
        "Run `brew reinstall personal-agentos`, confirm `command -v agentos`, and retry service setup.",
    )


def render_plist(cli_path: Path, data_dir: Path) -> bytes:
    """Return a launchd definition pinned to loopback and the durable data path."""
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(cli_path), "start", "--no-browser", "--host", "127.0.0.1", "--data", str(data_dir)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)


class ServiceController:
    """Manage one owner's launchd service with explicit, inspectable effects."""

    def __init__(
        self,
        *,
        home: str | Path | None = None,
        data_dir: str | Path | None = None,
        cli_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        runner: Runner = _run,
        which: Which = shutil.which,
        uid: int | None = None,
        health_probe: HealthProbe | None = None,
        listener_owner: ListenerOwner | None = None,
    ):
        env = os.environ if environ is None else environ
        self.home = Path(home if home is not None else Path.home()).expanduser().resolve()
        self.plist_path = self.home / "Library/LaunchAgents" / f"{LABEL}.plist"
        configured_data = data_dir if data_dir is not None else env.get("AGENTOS_DATA")
        recovered_data = None
        if configured_data is None and self.plist_path.is_file():
            try:
                installed = plistlib.loads(self.plist_path.read_bytes())
                arguments = installed.get("ProgramArguments") if isinstance(installed, dict) else None
                positions = [index for index, value in enumerate(arguments or ()) if value == "--data"]
                if (
                    isinstance(arguments, list)
                    and len(positions) == 1
                    and positions[0] + 1 < len(arguments)
                    and isinstance(arguments[positions[0] + 1], str)
                    and arguments[positions[0] + 1]
                ):
                    recovered_data = arguments[positions[0] + 1]
            except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
                recovered_data = None
        self.data_dir = Path(configured_data or recovered_data or self.home / DEFAULT_DATA_RELATIVE).expanduser().resolve()
        self._recovered_data_dir = Path(recovered_data).expanduser().resolve() if recovered_data else None
        # Resolution is intentionally lazy: status/stop/uninstall must remain
        # usable after a package manager has already removed the executable.
        self._cli_path = cli_path
        self._which = which
        self.runner = runner
        # An injected command runner is a test boundary and must inject its own
        # negative health behavior when needed. The real launchctl path always
        # confirms the loopback application endpoint before claiming success.
        self.health_probe = health_probe or (_probe_healthz if runner is _run else lambda: True)
        self._production_health_probe = health_probe is None and runner is _run
        self.health_wait = time.sleep if health_probe is None and runner is _run else lambda _seconds: None
        self.monotonic = time.monotonic
        self.listener_owner = listener_owner or (
            self._listener_owned_by_pid if self._production_health_probe else lambda _pid: True
        )
        self.uid = os.getuid() if uid is None else uid
        self.domain = f"gui/{self.uid}"
        self.service_target = f"{self.domain}/{LABEL}"

    def _reported_data_dir(self) -> Path:
        """Return the path owned by the installed definition for read/remove actions."""
        if self.plist_path.is_file():
            try:
                installed = plistlib.loads(self.plist_path.read_bytes())
                arguments = installed.get("ProgramArguments") if isinstance(installed, dict) else None
                positions = [index for index, value in enumerate(arguments or ()) if value == "--data"]
                if (
                    isinstance(arguments, list)
                    and len(positions) == 1
                    and positions[0] + 1 < len(arguments)
                    and isinstance(arguments[positions[0] + 1], str)
                    and arguments[positions[0] + 1]
                ):
                    return Path(arguments[positions[0] + 1]).expanduser().resolve()
            except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
                pass
        return self._recovered_data_dir or self.data_dir

    def _launchctl(self, *arguments: str) -> CommandResult:
        try:
            return self.runner(["launchctl", *arguments])
        except OSError as exc:
            return CommandResult(127, stderr=f"{type(exc).__name__}: launchctl is unavailable")

    def _observed_status(self) -> dict[str, object]:
        definition_exists = self.plist_path.exists()
        reported_data = self._reported_data_dir()
        result = self._launchctl("print", self.service_target)
        if result.returncode != 0:
            not_loaded = result.returncode == 113 or "could not find service" in _clean_error(result).lower()
            if not_loaded and not definition_exists:
                return {"ok": True, "status": "not_installed", "installed": False, "background_available": False,
                        "data_dir": str(reported_data), "data_preserved": reported_data.exists()}
            return {"ok": not_loaded, "status": "stopped" if not_loaded else "unknown", "installed": definition_exists,
                    "background_available": False, "data_dir": str(reported_data),
                    "next_action": ("Run the service start action; if it fails, reinstall the service definition."
                                    if not_loaded else "launchd status could not be read; retry before assuming the service is available.")}
        match = re.search(r"^\s*state\s*=\s*([^\s]+)", result.stdout, re.MULTILINE)
        pid_match = re.search(r"^\s*pid\s*=\s*(\d+)", result.stdout, re.MULTILINE)
        state = match.group(1).lower() if match else "loaded"
        running = state == "running"
        return {"ok": True, "status": "running" if running else "loaded_not_running", "launchd_state": state,
                "installed": definition_exists, "background_available": running, "data_dir": str(reported_data),
                **({"process_id": int(pid_match.group(1))} if pid_match else {}),
                **({} if running and definition_exists else {"next_action": (
                    "Run service uninstall to disable the orphaned registered job, then reinstall."
                    if not definition_exists
                    else "Run the service restart action, then inspect status again."
                )})}

    def _listener_owned_by_pid(self, pid: int) -> bool:
        lsof = self._which("lsof")
        if not lsof:
            fallback = Path("/usr/sbin/lsof")
            lsof = str(fallback) if fallback.is_file() and os.access(fallback, os.X_OK) else None
        if not lsof:
            return False
        result = self.runner([lsof, "-nP", "-a", "-p", str(pid), "-iTCP:8787", "-sTCP:LISTEN", "-t"])
        return result.returncode == 0 and str(pid) in result.stdout.split()

    def _application_healthy(self, observed: Mapping[str, object], timeout: float = 2.0) -> bool:
        if self._production_health_probe:
            pid = observed.get("process_id")
            try:
                owned = isinstance(pid, int) and self.listener_owner(pid)
            except Exception:
                owned = False
            if not owned:
                return False
        try:
            healthy = (
                self.health_probe(timeout)
                if self._production_health_probe
                else self.health_probe()
            ) is True
        except Exception:
            return False
        if healthy and self._production_health_probe:
            try:
                return self.listener_owner(pid)
            except Exception:
                return False
        return healthy

    def status(self) -> dict[str, object]:
        observed = self._observed_status()
        if observed.get("background_available"):
            healthy = self._application_healthy(observed)
            if not healthy:
                installed = bool(observed.get("installed"))
                return {
                    **observed,
                    "status": "running_unhealthy",
                    "process_running": True,
                    "background_available": False,
                    "next_action": (
                        "Run service restart; use foreground `agentos start` to inspect application health."
                        if installed else
                        "Run service uninstall to remove the orphaned job, then reinstall the service definition."
                    ),
                }
        return observed

    def _require(self, result: CommandResult, message: str, next_action: str) -> None:
        if result.returncode:
            detail = _clean_error(result)
            raise ServiceControlError(f"{message}: {detail}" if detail else message, next_action)

    def _stage_plist(self, contents: bytes) -> Path:
        parent = self.plist_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{LABEL}.", suffix=".plist", dir=parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            return Path(temporary)
        except BaseException:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    def _write_plist(self, contents: bytes) -> None:
        temporary = self._stage_plist(contents)
        try:
            os.replace(temporary, self.plist_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _confirm_running(self, next_action: str) -> dict[str, object]:
        observed = self._observed_status()
        if observed["status"] == "loaded_not_running":
            kicked = self._launchctl("kickstart", "-k", self.service_target)
            self._require(kicked, "The loaded AgentOS service could not be started", next_action)
            observed = self._observed_status()
        if not observed["background_available"]:
            raise ServiceControlError("A running AgentOS background process was not observed.", next_action)
        healthy = False
        deadline = self.monotonic() + 4.0
        for attempt in range(20):
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                break
            healthy = self._application_healthy(observed, min(1.0, remaining))
            if healthy:
                break
            if attempt < 19:
                self.health_wait(min(0.2, max(0.0, deadline - self.monotonic())))
        if not healthy:
            raise ServiceControlError(
                "The AgentOS process was running but its application health check did not pass.",
                next_action,
            )
        return observed

    def install(self, *, upgrade: bool = False) -> dict[str, object]:
        """Install and start the service; upgrades preserve owner data and roll back."""
        cli_path = resolve_cli_path(self._cli_path, which=self._which, runner=self.runner)
        desired = render_plist(cli_path, self.data_dir)
        previous = self.plist_path.read_bytes() if self.plist_path.exists() else None
        if previous is None:
            orphan = self._observed_status()
            if orphan["status"] != "not_installed":
                raise ServiceControlError(
                    "A registered AgentOS service exists without its installed definition.",
                    "Run service uninstall to remove the orphaned job, then retry install; owner data is retained.",
                )
        if previous is not None and previous != desired and not upgrade:
            raise ServiceControlError(
                "A different AgentOS service definition is already installed.",
                "Run the explicit service upgrade action to replace it without deleting owner data.",
            )
        prior_status = self._observed_status() if previous is not None else None
        was_loaded = prior_status is not None and prior_status["status"] != "stopped"
        if previous == desired:
            if upgrade:
                if not was_loaded:
                    return {**prior_status, "operation": "upgrade", "changed": False, "data_preserved": True}
                restarted = self.restart()
                return {**restarted, "operation": "upgrade", "data_preserved": True}
            return self.start()
        # Stage and fsync the replacement while the prior service is still
        # running. Permission/capacity failures therefore cannot stop a known-
        # good service before a replacement is ready to commit.
        staged = self._stage_plist(desired)
        replacement_committed = False
        try:
            if was_loaded:
                stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
                self._require(stopped, "The existing service could not be stopped for upgrade",
                              "Run service stop and retry upgrade; the existing definition and owner data were retained.")
            os.replace(staged, self.plist_path)
            replacement_committed = True
            if previous is not None and not was_loaded:
                observed = self._observed_status()
                return {**observed, "operation": "upgrade", "changed": True, "data_preserved": True}
            enabled = self._launchctl("enable", self.service_target)
            self._require(
                enabled,
                "The service definition could not be enabled",
                "Run service status, then retry install; owner data was retained.",
            )
            started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
            self._require(
                started,
                "The service definition was not activated",
                "Run the service status action, then retry install; foreground `agentos start` remains available.",
            )
            observed = self._confirm_running(
                "Run the service restart action; use foreground `agentos start` to view a startup error."
            )
        except (ServiceControlError, OSError) as failure:
            # Bootstrap may succeed while the new executable exits immediately.
            # Remove that definition before restoring the last known one.
            removed = self._launchctl("bootout", self.domain, str(self.plist_path))
            try:
                if removed.returncode:
                    remaining = self._observed_status()
                    if remaining["status"] not in {"stopped", "not_installed"}:
                        detail = _clean_error(removed)
                        raise ServiceControlError(
                            "The failed replacement service could not be stopped"
                            + (f": {detail}" if detail else ""),
                            "Run service status and stop the registered job before reinstalling; owner data was retained.",
                        )
                if previous is None:
                    self.plist_path.unlink(missing_ok=True)
                else:
                    if replacement_committed:
                        self._write_plist(previous)
                    if was_loaded:
                        restored_enabled = self._launchctl("enable", self.service_target)
                        self._require(
                            restored_enabled,
                            "The previous service definition could not be re-enabled",
                            "Reinstall the service definition, inspect service status, and use foreground `agentos start`; owner data was retained.",
                        )
                        restored = self._launchctl("bootstrap", self.domain, str(self.plist_path))
                        self._require(
                            restored,
                            "The previous service definition could not be restored",
                            "Reinstall the service definition, inspect service status, and use foreground `agentos start`; owner data was retained.",
                        )
                        self._confirm_running(
                            "The previous service was restored on disk but not observed running; inspect service status and use foreground `agentos start`."
                        )
            except (ServiceControlError, OSError) as rollback_failure:
                raise ServiceControlError(
                    f"The service upgrade failed and rollback could not be verified: {rollback_failure}",
                    "Reinstall the service definition, inspect service status, and use foreground `agentos start`; owner data was retained.",
                ) from failure
            raise ServiceControlError(
                f"The service upgrade did not become healthy and was rolled back: {failure}",
                "Inspect service status and use foreground `agentos start` before retrying; owner data was retained.",
            ) from failure
        finally:
            staged.unlink(missing_ok=True)
        return {**observed, "operation": "upgrade" if previous is not None else "install", "data_preserved": True}

    def upgrade(self) -> dict[str, object]:
        return self.install(upgrade=True)

    def start(self) -> dict[str, object]:
        if not self.plist_path.exists():
            raise ServiceControlError("The AgentOS background service is not installed.",
                                      "Run the service install action, or use foreground `agentos start`.")
        current = self.status()
        if current["status"] == "running":
            return {**current, "operation": "start", "changed": False}
        if current["status"] == "running_unhealthy":
            raise ServiceControlError(
                "The AgentOS process is running but its application health check did not pass.",
                "Run service restart; use foreground `agentos start` to inspect application health.",
            )
        enabled = self._launchctl("enable", self.service_target)
        self._require(
            enabled,
            "The AgentOS background service could not be enabled",
            "Run service status, then retry start; no owner data was deleted.",
        )
        if current["status"] == "loaded_not_running":
            started = self._launchctl("kickstart", "-k", self.service_target)
        else:
            started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._require(started, "The AgentOS background service could not start",
                      "Run service status; use foreground `agentos start` to view a startup error.")
        try:
            observed = self._confirm_running(
                "Use foreground `agentos start` to inspect the startup failure, then retry service start."
            )
        except ServiceControlError as failure:
            removed = self._launchctl("bootout", self.domain, str(self.plist_path))
            if removed.returncode and self._observed_status()["status"] not in {"stopped", "not_installed"}:
                raise ServiceControlError(
                    f"The service did not become healthy and cleanup could not be verified: {failure}",
                    "Run service status and stop before retrying; use foreground `agentos start` to inspect startup.",
                ) from failure
            raise ServiceControlError(
                f"The service did not become healthy and was stopped: {failure}",
                "Use foreground `agentos start` to inspect the startup failure, then retry service start.",
            ) from failure
        return {**observed, "operation": "start", "changed": True}

    def stop(self) -> dict[str, object]:
        current = self._observed_status()
        if current["status"] == "not_installed":
            return {**current, "operation": "stop", "changed": False}
        disabled = self._launchctl("disable", self.service_target)
        self._require(
            disabled,
            "The AgentOS background service could not be persistently disabled",
            "Run service status and retry stop; no owner data was deleted.",
        )
        if current["status"] == "stopped":
            return {**current, "operation": "stop", "changed": True, "persistently_disabled": True}
        stopped = (
            self._launchctl("bootout", self.domain, str(self.plist_path))
            if self.plist_path.exists()
            else self._launchctl("bootout", self.service_target)
        )
        self._require(stopped, "The AgentOS background service could not stop",
                      "Run service status and retry stop; no owner data was deleted.")
        installed = self.plist_path.exists()
        return {"ok": True, "operation": "stop", "changed": True,
                "status": "stopped" if installed else "not_installed", "installed": installed,
                "background_available": False, "data_dir": str(self._reported_data_dir()), "data_preserved": True,
                "persistently_disabled": True,
                **({} if installed else {"next_action": "Run service install before starting the background service."})}

    def restart(self) -> dict[str, object]:
        if not self.plist_path.exists():
            raise ServiceControlError("The AgentOS background service is not installed.",
                                      "Run the service install action, or use foreground `agentos start`.")
        current = self._observed_status()
        if current["status"] != "stopped":
            stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
            self._require(stopped, "The existing AgentOS service could not be stopped for restart",
                          "Run service status; no owner data was deleted.")
        enabled = self._launchctl("enable", self.service_target)
        self._require(
            enabled,
            "The AgentOS background service could not be enabled for restart",
            "Run service status, then retry restart; no owner data was deleted.",
        )
        started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._require(started, "The AgentOS background service could not restart",
                      "Use foreground `agentos start` to inspect the startup failure, then retry service restart.")
        try:
            observed = self._confirm_running("Use foreground `agentos start` to inspect the startup failure.")
        except ServiceControlError as failure:
            removed = self._launchctl("bootout", self.domain, str(self.plist_path))
            if removed.returncode and self._observed_status()["status"] not in {"stopped", "not_installed"}:
                raise ServiceControlError(
                    f"The service did not become healthy and cleanup could not be verified: {failure}",
                    "Run service status and stop before retrying; use foreground `agentos start` to inspect startup.",
                ) from failure
            raise ServiceControlError(
                f"The service did not become healthy and was stopped: {failure}",
                "Use foreground `agentos start` to inspect the startup failure, then retry service restart.",
            ) from failure
        return {**observed, "operation": "restart", "changed": True, "data_preserved": True}

    def uninstall(self) -> dict[str, object]:
        """Remove only service registration; durable owner data is always retained."""
        current = self._observed_status()
        reported_data = self._reported_data_dir()
        job_registered = current["status"] not in {"stopped", "not_installed"}
        definition_exists = self.plist_path.exists()
        if job_registered:
            disabled = self._launchctl("disable", self.service_target)
            self._require(disabled, "The service could not be persistently disabled",
                          "Run service stop and retry uninstall; no owner data was deleted.")
            stopped = (
                self._launchctl("bootout", self.domain, str(self.plist_path))
                if definition_exists
                else self._launchctl("bootout", self.service_target)
            )
            self._require(stopped, "The service could not be disabled, so uninstall was not completed",
                          "Run service stop and retry uninstall; no owner data was deleted.")
        if definition_exists:
            self.plist_path.unlink()
        changed = job_registered or definition_exists
        return {"ok": True, "operation": "uninstall", "changed": changed, "status": "not_installed",
                "installed": False, "background_available": False, "data_dir": str(reported_data),
                "data_preserved": True,
                "next_action": "Owner data was retained. Remove the reported data directory separately only if you intend to erase it."}


def service_action(action: str, **controller_options: object) -> dict[str, object]:
    """Small integration seam for the central CLI owned by PA1 integration."""
    controller = ServiceController(**controller_options)
    operations = {"install": controller.install, "upgrade": controller.upgrade, "start": controller.start,
                  "stop": controller.stop, "status": controller.status, "restart": controller.restart,
                  "uninstall": controller.uninstall}
    if action not in operations:
        raise ValueError(f"Unsupported service action: {action}")

    def failure_receipt(error: ServiceControlError) -> dict[str, object]:
        try:
            observed = controller.status()
            availability: object = (
                "unknown" if observed.get("status") == "unknown"
                else bool(observed.get("background_available"))
            )
            observed_status = observed.get("status", "unknown")
        except Exception:
            availability = "unknown"
            observed_status = "unknown"
        return {
            **error.as_dict(),
            "background_available": availability,
            "observed_status": observed_status,
            "operation": action,
            "data_dir": str(controller._reported_data_dir()),
            "data_preserved": True,
        }
    try:
        return operations[action]()
    except ServiceControlError as exc:
        return failure_receipt(exc)
    except OSError as exc:
        bounded = ServiceControlError(
            f"The service files could not be updated: {type(exc).__name__}",
            "Check the owner LaunchAgents and AgentOS data-directory permissions and free disk space, then retry; owner data was not deleted.",
        )
        return failure_receipt(bounded)
