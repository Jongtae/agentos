"""
Sandbox — enforces workspace root confinement for all file operations.
All file paths must pass through safe_path() before use.
"""
from __future__ import annotations

from pathlib import Path


def safe_path(workspace_root: Path, user_path: str) -> Path:
    """
    Resolve user_path relative to workspace_root and verify it stays within.

    Raises:
        ValueError: if the resolved path escapes the workspace root.
    """
    root = workspace_root.resolve()
    target = (root / user_path).resolve()

    if not str(target).startswith(str(root)):
        raise ValueError(
            f"Path '{user_path}' resolves outside workspace root '{root}'. "
            "Access denied."
        )
    return target


def is_safe_path(workspace_root: Path, user_path: str) -> bool:
    """Return True if the path is safe (within workspace root)."""
    try:
        safe_path(workspace_root, user_path)
        return True
    except ValueError:
        return False
