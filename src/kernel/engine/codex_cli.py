from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from kernel.engine.base import EngineRunResult, HealthCheckResult
from io_utils import scrub_sensitive_text


class CodexCliEngine:
    """KernelEngine implementation backed by `codex exec` (non-interactive)."""

    def __init__(
        self,
        workspace_dir: Path,
        command: str = "codex",
        timeout_sec: int = 90,
        model: str = "",
    ):
        self._workspace_dir = Path(workspace_dir).resolve()
        self._command = command
        self._timeout_sec = max(1, int(timeout_sec))
        self._model = model

    @property
    def name(self) -> str:
        return "codex"

    def health_check(self) -> HealthCheckResult:
        binary = shutil.which(self._command)
        if not binary:
            return HealthCheckResult(
                ok=False,
                reason="binary_not_found",
                detail=f"`{self._command}` is not installed or not in PATH.",
            )

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return HealthCheckResult(
                ok=False,
                reason="missing_api_key",
                detail="OPENAI_API_KEY is not set.",
            )

        probe = self.run_intent("Reply with exactly: HEALTH_OK")
        if not probe.ok:
            return HealthCheckResult(
                ok=False,
                reason=probe.error_type or "health_exec_failed",
                detail=probe.error_message or "Codex health probe failed.",
            )

        if "HEALTH_OK" not in probe.content:
            return HealthCheckResult(
                ok=False,
                reason="unexpected_probe_output",
                detail="Codex health probe did not return expected marker.",
            )

        return HealthCheckResult(ok=True, reason="ok", detail="Codex engine is healthy.")

    def run_intent(self, intent: str, context: str = "") -> EngineRunResult:
        binary = shutil.which(self._command)
        if not binary:
            return EngineRunResult(
                ok=False,
                error_type="binary_not_found",
                error_message=f"`{self._command}` is not installed or not in PATH.",
            )

        if not os.environ.get("OPENAI_API_KEY", "").strip():
            return EngineRunResult(
                ok=False,
                error_type="missing_api_key",
                error_message="OPENAI_API_KEY is not set.",
            )

        full_prompt = intent.strip()
        if context.strip():
            full_prompt = f"Context:\n{context.strip()}\n\nTask:\n{intent.strip()}"

        with tempfile.NamedTemporaryFile(prefix="codex-last-", suffix=".txt", delete=False) as tmp:
            out_path = tmp.name

        cmd = [
            binary,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-last-message",
            out_path,
            "--cd",
            str(self._workspace_dir),
        ]

        if self._model:
            cmd.extend(["--model", self._model])

        cmd.append(full_prompt)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._workspace_dir),
                capture_output=True,
                text=True,
                timeout=self._timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return EngineRunResult(
                ok=False,
                error_type="timeout",
                error_message=f"Codex execution timed out after {self._timeout_sec}s.",
            )
        except Exception as e:
            return EngineRunResult(
                ok=False,
                error_type="execution_error",
                error_message=f"Codex execution failed: {e}",
            )

        content = ""
        try:
            content = Path(out_path).read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            pass
        finally:
            try:
                Path(out_path).unlink(missing_ok=True)
            except Exception:
                pass

        if not content:
            content = (proc.stdout or "").strip()

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = scrub_sensitive_text(stderr or stdout or "Codex CLI returned non-zero exit code")
            return EngineRunResult(
                ok=False,
                error_type="non_zero_exit",
                error_message=detail,
                exit_code=proc.returncode,
                metadata={
                    "stdout": scrub_sensitive_text(stdout[:2000]),
                    "stderr": scrub_sensitive_text(stderr[:2000]),
                },
            )

        return EngineRunResult(ok=True, content=content, exit_code=proc.returncode)

    def invoke(self, messages: list[Any]) -> Any:
        """LangChain-like adapter so Planner can call .invoke(messages)."""
        parts: list[str] = []
        for msg in messages:
            role = getattr(msg, "type", msg.__class__.__name__).upper()
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                text_chunks = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_chunks.append(item.get("text", ""))
                    else:
                        text_chunks.append(str(item))
                content = "\n".join(text_chunks)
            parts.append(f"[{role}]\n{content}")

        run = self.run_intent(
            intent=(
                "You are the planning engine for AgentOS. "
                "Respond exactly according to the provided system/user messages.\n\n"
                + "\n\n".join(parts)
            )
        )

        if not run.ok:
            raise RuntimeError(f"codex planner invoke failed: {run.error_type}: {run.error_message}")

        return SimpleNamespace(content=run.content)
