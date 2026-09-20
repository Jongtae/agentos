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
from typing import Callable, Mapping, Sequence


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


def _run(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _clean_error(result: CommandResult) -> str:
    return " ".join((result.stderr or result.stdout).strip().split())[:300]


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
    ):
        env = os.environ if environ is None else environ
        self.home = Path(home if home is not None else Path.home()).expanduser().resolve()
        configured_data = data_dir if data_dir is not None else env.get("AGENTOS_DATA")
        self.data_dir = Path(configured_data or self.home / DEFAULT_DATA_RELATIVE).expanduser().resolve()
        # Resolution is intentionally lazy: status/stop/uninstall must remain
        # usable after a package manager has already removed the executable.
        self._cli_path = cli_path
        self._which = which
        self.runner = runner
        self.uid = os.getuid() if uid is None else uid
        self.domain = f"gui/{self.uid}"
        self.service_target = f"{self.domain}/{LABEL}"
        self.plist_path = self.home / "Library/LaunchAgents" / f"{LABEL}.plist"

    def _launchctl(self, *arguments: str) -> CommandResult:
        try:
            return self.runner(["launchctl", *arguments])
        except OSError as exc:
            return CommandResult(127, stderr=f"{type(exc).__name__}: launchctl is unavailable")

    def _observed_status(self) -> dict[str, object]:
        if not self.plist_path.exists():
            return {"ok": True, "status": "not_installed", "installed": False, "background_available": False,
                    "data_dir": str(self.data_dir), "data_preserved": self.data_dir.exists()}
        result = self._launchctl("print", self.service_target)
        if result.returncode != 0:
            not_loaded = result.returncode == 113 or "could not find service" in _clean_error(result).lower()
            return {"ok": not_loaded, "status": "stopped" if not_loaded else "unknown", "installed": True,
                    "background_available": False, "data_dir": str(self.data_dir),
                    "next_action": ("Run the service start action; if it fails, reinstall the service definition."
                                    if not_loaded else "launchd status could not be read; retry before assuming the service is available.")}
        match = re.search(r"^\s*state\s*=\s*([^\s]+)", result.stdout, re.MULTILINE)
        state = match.group(1).lower() if match else "loaded"
        running = state == "running"
        return {"ok": True, "status": "running" if running else "loaded_not_running", "launchd_state": state,
                "installed": True, "background_available": running, "data_dir": str(self.data_dir),
                **({} if running else {"next_action": "Run the service restart action, then inspect status again."})}

    def status(self) -> dict[str, object]:
        return self._observed_status()

    def _require(self, result: CommandResult, message: str, next_action: str) -> None:
        if result.returncode:
            detail = _clean_error(result)
            raise ServiceControlError(f"{message}: {detail}" if detail else message, next_action)

    def _write_plist(self, contents: bytes) -> None:
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
            os.replace(temporary, self.plist_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _confirm_running(self, next_action: str) -> dict[str, object]:
        observed = self._observed_status()
        if observed["status"] == "loaded_not_running":
            kicked = self._launchctl("kickstart", "-k", self.service_target)
            self._require(kicked, "The loaded AgentOS service could not be started", next_action)
            observed = self._observed_status()
        if not observed["background_available"]:
            raise ServiceControlError("A running AgentOS background process was not observed.", next_action)
        return observed

    def install(self, *, upgrade: bool = False) -> dict[str, object]:
        """Install and start the service; upgrades preserve owner data and roll back."""
        cli_path = resolve_cli_path(self._cli_path, which=self._which, runner=self.runner)
        desired = render_plist(cli_path, self.data_dir)
        previous = self.plist_path.read_bytes() if self.plist_path.exists() else None
        if previous is not None and previous != desired and not upgrade:
            raise ServiceControlError(
                "A different AgentOS service definition is already installed.",
                "Run the explicit service upgrade action to replace it without deleting owner data.",
            )
        if previous == desired:
            if upgrade:
                restarted = self.restart()
                return {**restarted, "operation": "upgrade", "data_preserved": True}
            return self.start()
        was_loaded = previous is not None and self._observed_status()["status"] != "stopped"
        if was_loaded:
            stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
            self._require(stopped, "The existing service could not be stopped for upgrade",
                          "Run service stop and retry upgrade; the existing definition and owner data were retained.")
        self._write_plist(desired)
        try:
            started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
            self._require(
                started,
                "The service definition was not activated",
                "Run the service status action, then retry install; foreground `agentos start` remains available.",
            )
            observed = self._confirm_running(
                "Run the service restart action; use foreground `agentos start` to view a startup error."
            )
        except ServiceControlError as failure:
            # Bootstrap may succeed while the new executable exits immediately.
            # Remove that definition before restoring the last known one.
            self._launchctl("bootout", self.domain, str(self.plist_path))
            if previous is None:
                self.plist_path.unlink(missing_ok=True)
            else:
                self._write_plist(previous)
                if was_loaded:
                    self._launchctl("bootstrap", self.domain, str(self.plist_path))
            raise ServiceControlError(
                f"The service upgrade did not become healthy and was rolled back: {failure}",
                "Inspect service status and use foreground `agentos start` before retrying; owner data was retained.",
            ) from failure
        return {**observed, "operation": "upgrade" if previous is not None else "install", "data_preserved": True}

    def upgrade(self) -> dict[str, object]:
        return self.install(upgrade=True)

    def start(self) -> dict[str, object]:
        if not self.plist_path.exists():
            raise ServiceControlError("The AgentOS background service is not installed.",
                                      "Run the service install action, or use foreground `agentos start`.")
        current = self._observed_status()
        if current["status"] == "running":
            return {**current, "operation": "start", "changed": False}
        if current["status"] == "loaded_not_running":
            started = self._launchctl("kickstart", "-k", self.service_target)
        else:
            started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._require(started, "The AgentOS background service could not start",
                      "Run service status; use foreground `agentos start` to view a startup error.")
        observed = self._confirm_running(
            "Use foreground `agentos start` to inspect the startup failure, then retry service start."
        )
        return {**observed, "operation": "start", "changed": True}

    def stop(self) -> dict[str, object]:
        if not self.plist_path.exists():
            return {**self._observed_status(), "operation": "stop", "changed": False}
        current = self._observed_status()
        if current["status"] == "stopped":
            return {**current, "operation": "stop", "changed": False}
        stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
        self._require(stopped, "The AgentOS background service could not stop",
                      "Run service status and retry stop; no owner data was deleted.")
        return {"ok": True, "operation": "stop", "changed": True, "status": "stopped", "installed": True,
                "background_available": False, "data_dir": str(self.data_dir), "data_preserved": True}

    def restart(self) -> dict[str, object]:
        if not self.plist_path.exists():
            raise ServiceControlError("The AgentOS background service is not installed.",
                                      "Run the service install action, or use foreground `agentos start`.")
        current = self._observed_status()
        if current["status"] != "stopped":
            stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
            self._require(stopped, "The existing AgentOS service could not be stopped for restart",
                          "Run service status; no owner data was deleted.")
        started = self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._require(started, "The AgentOS background service could not restart",
                      "Use foreground `agentos start` to inspect the startup failure, then retry service restart.")
        observed = self._confirm_running("Use foreground `agentos start` to inspect the startup failure.")
        return {**observed, "operation": "restart", "changed": True, "data_preserved": True}

    def uninstall(self) -> dict[str, object]:
        """Remove only service registration; durable owner data is always retained."""
        if self.plist_path.exists():
            current = self._observed_status()
            if current["status"] != "stopped":
                stopped = self._launchctl("bootout", self.domain, str(self.plist_path))
                self._require(stopped, "The service could not be disabled, so uninstall was not completed",
                              "Run service stop and retry uninstall; no owner data was deleted.")
            self.plist_path.unlink()
            changed = True
        else:
            changed = False
        return {"ok": True, "operation": "uninstall", "changed": changed, "status": "not_installed",
                "installed": False, "background_available": False, "data_dir": str(self.data_dir),
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
    try:
        return operations[action]()
    except ServiceControlError as exc:
        return {**exc.as_dict(), "operation": action, "data_dir": str(controller.data_dir), "data_preserved": True}
    except OSError as exc:
        bounded = ServiceControlError(
            f"The service files could not be updated: {type(exc).__name__}",
            "Check the owner LaunchAgents and AgentOS data-directory permissions and free disk space, then retry; owner data was not deleted.",
        )
        return {**bounded.as_dict(), "operation": action, "data_dir": str(controller.data_dir), "data_preserved": True}
