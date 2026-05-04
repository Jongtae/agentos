from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from kernel.engine.base import HealthCheckResult
from kernel.engine.codex_cli import CodexCliEngine
from kernel.engine.ollama_cli import OllamaEngine


@dataclass
class EngineBootstrapResult:
    ok: bool
    provider: str
    selected_model: str = ""
    bootstrap_attempted: bool = False
    bootstrap_performed: bool = False
    install_strategy: str = ""
    reason: str = ""
    detail: str = ""
    health: HealthCheckResult | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def _root_prefix() -> str:
    if os.geteuid() == 0:
        return ""
    if shutil.which("sudo"):
        return "sudo -n "
    return ""


def _run_shell(command: str, *, cwd: Path, timeout_sec: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-lc", command],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=max(1, timeout_sec),
    )


def _ensure_bootstrap_tool(package_name: str, *, cwd: Path, timeout_sec: int) -> str:
    binary = shutil.which(package_name)
    if binary:
        return binary
    if not shutil.which("apt-get"):
        return ""
    root_prefix = _root_prefix()
    install_cmd = f"{root_prefix}apt-get update && {root_prefix}apt-get install -y {shlex.quote(package_name)}"
    proc = _run_shell(install_cmd, cwd=cwd, timeout_sec=timeout_sec)
    if proc.returncode != 0:
        return ""
    return shutil.which(package_name) or ""


def _boolish(value: object, default: bool = True) -> bool:
    raw = str(value).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _default_ollama_start_cmd(wm, engine: OllamaEngine, ollama_log: Path) -> str:
    root_prefix = _root_prefix()
    systemd_unit = os.environ.get("AGENTOS_OLLAMA_SYSTEMD_UNIT", "agentos-ollama.service")
    legacy_systemd_unit = os.environ.get("AGENTOS_OLLAMA_LEGACY_SYSTEMD_UNIT", "ollama.service")
    service_name = os.environ.get("AGENTOS_OLLAMA_SERVICE_NAME", "agentos-ollama")
    legacy_service_name = os.environ.get("AGENTOS_OLLAMA_LEGACY_SERVICE_NAME", "ollama")
    return (
        f"{root_prefix}systemctl start {shlex.quote(systemd_unit)} "
        f"|| {root_prefix}systemctl start {shlex.quote(legacy_systemd_unit)} "
        f"|| {root_prefix}service {shlex.quote(service_name)} start "
        f"|| {root_prefix}service {shlex.quote(legacy_service_name)} start "
        f"|| (nohup env OLLAMA_MODELS={shlex.quote(str(engine.models_dir()))} "
        f"{shlex.quote(wm.ollama_command)} serve >> {shlex.quote(str(ollama_log))} 2>&1 &)"
    )


def _wait_for_ollama_health(engine: OllamaEngine, *, timeout_sec: int = 60, poll_interval_sec: int = 5) -> HealthCheckResult:
    deadline = time.time() + max(1, timeout_sec)
    last = engine.health_check()
    while time.time() < deadline:
        if last.ok:
            return last
        time.sleep(max(1, poll_interval_sec))
        last = engine.health_check()
    return last


def ensure_provider_ready(wm, provider: str, *, allow_bootstrap: bool = True) -> EngineBootstrapResult:
    provider = str(provider).strip().lower()
    if provider == "ollama":
        return _ensure_ollama_ready(wm, allow_bootstrap=allow_bootstrap)
    if provider == "codex":
        return _ensure_codex_ready(wm, allow_bootstrap=allow_bootstrap)
    return EngineBootstrapResult(
        ok=(provider == "none"),
        provider=provider,
        reason="guide_mode" if provider == "none" else "unsupported_provider",
        detail="Guide mode selected." if provider == "none" else f"No bootstrap strategy for provider '{provider}'.",
    )


def _ensure_ollama_ready(wm, *, allow_bootstrap: bool = True) -> EngineBootstrapResult:
    engine = OllamaEngine(
        workspace_dir=wm.workspace_dir,
        command=wm.ollama_command,
        timeout_sec=wm.ollama_timeout_sec,
        model=wm.ollama_model,
    )
    initial = engine.health_check()
    if initial.ok:
        return EngineBootstrapResult(
            ok=True,
            provider="ollama",
            selected_model=wm.ollama_model,
            install_strategy="already_available",
            reason=initial.reason,
            detail=initial.detail,
            health=initial,
        )

    log_dir = wm.workspace_dir / "artifacts" / "kernel-engine"
    log_dir.mkdir(parents=True, exist_ok=True)
    ollama_log = log_dir / "ollama-serve.log"
    start_cmd = os.environ.get(
        "AGENTOS_OLLAMA_START_CMD",
        _default_ollama_start_cmd(wm, engine, ollama_log),
    )

    bundled_local_candidate = bool(engine._binary_path() and engine._local_model_store_ready())
    if bundled_local_candidate:
        start_run = _run_shell(start_cmd, cwd=wm.workspace_dir, timeout_sec=60)
        if start_run.returncode == 0:
            final = _wait_for_ollama_health(engine, timeout_sec=60)
            if final.ok:
                return EngineBootstrapResult(
                    ok=True,
                    provider="ollama",
                    selected_model=wm.ollama_model,
                    bootstrap_attempted=False,
                    bootstrap_performed=False,
                    install_strategy="bundled_local",
                    reason=final.reason,
                    detail=final.detail,
                    health=final,
                    metadata={"serve_log": str(ollama_log), "models_dir": str(engine.models_dir())},
                )
        if not allow_bootstrap:
            return EngineBootstrapResult(
                ok=False,
                provider="ollama",
                selected_model=wm.ollama_model,
                bootstrap_attempted=False,
                install_strategy="bundled_local",
                reason="bundled_local_start_failed",
                detail=(start_run.stderr or start_run.stdout or initial.detail or "bundled local Ollama could not start").strip(),
                health=initial,
                metadata={"serve_log": str(ollama_log), "models_dir": str(engine.models_dir())},
            )

    auto_bootstrap = _boolish(
        wm.spec.get("kernel_engine", {}).get("ollama", {}).get("auto_bootstrap", True)
    )
    if not allow_bootstrap or not auto_bootstrap or initial.reason not in {"binary_not_found", "model_not_found"}:
        return EngineBootstrapResult(
            ok=False,
            provider="ollama",
            selected_model=wm.ollama_model,
            bootstrap_attempted=False,
            install_strategy="disabled",
            reason=initial.reason,
            detail=initial.detail,
            health=initial,
        )

    if not _ensure_bootstrap_tool("zstd", cwd=wm.workspace_dir, timeout_sec=180):
        return EngineBootstrapResult(
            ok=False,
            provider="ollama",
            selected_model=wm.ollama_model,
            bootstrap_attempted=True,
            install_strategy="official_install_script",
            reason="missing_bootstrap_tool",
            detail="zstd is required for the official Ollama install path.",
            health=initial,
        )

    root_prefix = _root_prefix()
    install_cmd = os.environ.get(
        "AGENTOS_OLLAMA_INSTALL_CMD",
        f"{root_prefix}curl -fsSL https://ollama.com/install.sh | sh",
    )
    pull_cmd = os.environ.get(
        "AGENTOS_OLLAMA_PULL_CMD",
        f"{shlex.quote(wm.ollama_command)} pull {shlex.quote(wm.ollama_model)}",
    )

    attempted = False
    if initial.reason == "binary_not_found":
        attempted = True
        install_run = _run_shell(install_cmd, cwd=wm.workspace_dir, timeout_sec=max(wm.ollama_timeout_sec, 300))
        if install_run.returncode != 0:
            return EngineBootstrapResult(
                ok=False,
                provider="ollama",
                selected_model=wm.ollama_model,
                bootstrap_attempted=True,
                install_strategy="official_install_script",
                reason="bootstrap_install_failed",
                detail=(install_run.stderr or install_run.stdout or "ollama install command failed").strip(),
                health=initial,
            )

    start_run = _run_shell(start_cmd, cwd=wm.workspace_dir, timeout_sec=60)
    if start_run.returncode != 0:
        return EngineBootstrapResult(
            ok=False,
            provider="ollama",
            selected_model=wm.ollama_model,
            bootstrap_attempted=True,
            install_strategy="official_install_script",
            reason="bootstrap_start_failed",
            detail=(start_run.stderr or start_run.stdout or "ollama start command failed").strip(),
            health=initial,
        )

    attempted = True
    pull_run = _run_shell(pull_cmd, cwd=wm.workspace_dir, timeout_sec=max(wm.ollama_timeout_sec, 600))
    if pull_run.returncode != 0:
        return EngineBootstrapResult(
            ok=False,
            provider="ollama",
            selected_model=wm.ollama_model,
            bootstrap_attempted=True,
            install_strategy="official_install_script",
            reason="bootstrap_model_pull_failed",
            detail=(pull_run.stderr or pull_run.stdout or "ollama pull failed").strip(),
            health=initial,
        )

    final = _wait_for_ollama_health(engine, timeout_sec=60)
    return EngineBootstrapResult(
        ok=bool(final.ok),
        provider="ollama",
        selected_model=wm.ollama_model,
        bootstrap_attempted=attempted,
        bootstrap_performed=attempted,
        install_strategy="official_install_script",
        reason=final.reason,
        detail=final.detail,
        health=final,
        metadata={"serve_log": str(ollama_log)},
    )


def _ensure_codex_ready(wm, *, allow_bootstrap: bool = True) -> EngineBootstrapResult:
    engine = CodexCliEngine(
        workspace_dir=wm.workspace_dir,
        command=wm.codex_command,
        timeout_sec=wm.codex_timeout_sec,
        model=wm.codex_model,
    )
    initial = engine.health_check()
    if initial.ok:
        return EngineBootstrapResult(
            ok=True,
            provider="codex",
            bootstrap_attempted=False,
            install_strategy="already_available",
            reason=initial.reason,
            detail=initial.detail,
            health=initial,
        )

    auto_bootstrap = _boolish(
        wm.spec.get("kernel_engine", {}).get("codex", {}).get("auto_bootstrap", True)
    )
    if not allow_bootstrap or not auto_bootstrap or initial.reason != "binary_not_found":
        return EngineBootstrapResult(
            ok=False,
            provider="codex",
            bootstrap_attempted=False,
            install_strategy="disabled",
            reason=initial.reason,
            detail=initial.detail,
            health=initial,
        )

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return EngineBootstrapResult(
            ok=False,
            provider="codex",
            bootstrap_attempted=False,
            install_strategy="npm_global_install",
            reason="missing_api_key",
            detail="OPENAI_API_KEY is required before Codex bootstrap can proceed.",
            health=initial,
        )

    npm = _ensure_bootstrap_tool("npm", cwd=wm.workspace_dir, timeout_sec=240)
    if not npm:
        return EngineBootstrapResult(
            ok=False,
            provider="codex",
            bootstrap_attempted=False,
            install_strategy="npm_global_install",
            reason="missing_bootstrap_tool",
            detail="npm is not installed or not on PATH.",
            health=initial,
        )

    install_cmd = os.environ.get(
        "AGENTOS_CODEX_INSTALL_CMD",
        f"{shlex.quote(npm)} install -g @openai/codex",
    )
    install_run = _run_shell(install_cmd, cwd=wm.workspace_dir, timeout_sec=max(wm.codex_timeout_sec, 300))
    if install_run.returncode != 0:
        return EngineBootstrapResult(
            ok=False,
            provider="codex",
            bootstrap_attempted=True,
            bootstrap_performed=False,
            install_strategy="npm_global_install",
            reason="bootstrap_install_failed",
            detail=(install_run.stderr or install_run.stdout or "codex install failed").strip(),
            health=initial,
        )

    final = engine.health_check()
    return EngineBootstrapResult(
        ok=bool(final.ok),
        provider="codex",
        bootstrap_attempted=True,
        bootstrap_performed=True,
        install_strategy="npm_global_install",
        reason=final.reason,
        detail=final.detail,
        health=final,
    )
