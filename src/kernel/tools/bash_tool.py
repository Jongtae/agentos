"""
BashTool — executes shell commands within the workspace directory.

Rules:
- shell=False always (use shlex.split)
- workspace root confinement via cwd
- command classification done BEFORE run() is called (by PolicyEngine)
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

_MAX_OUTPUT = 4_000  # characters
_TIMEOUT = 30        # seconds


class BashTool:
    name = "bash"

    def __init__(self, workspace_dir: Path):
        self._cwd = workspace_dir

    def run(self, args: dict) -> str:
        """
        Execute a shell command.

        args:
            command (str): the shell command to execute
        """
        command = args.get("command", "").strip()
        if not command:
            return "[error] empty command"

        try:
            tokens = shlex.split(command)
        except ValueError as e:
            return f"[error] failed to parse command: {e}"

        try:
            result = subprocess.run(
                tokens,
                shell=False,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                cwd=str(self._cwd),
            )
            output = (result.stdout + result.stderr).strip()
            if not output:
                return f"(command exited with code {result.returncode}, no output)"
            return output[:_MAX_OUTPUT]
        except subprocess.TimeoutExpired:
            return f"[error] command timed out after {_TIMEOUT}s"
        except FileNotFoundError as e:
            return f"[error] command not found: {e}"
        except Exception as e:
            return f"[error] execution failed: {e}"
