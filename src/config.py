"""
Config — loads environment variables and resolves workspace path.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env() -> None:
    """Load .env file if it exists (using python-dotenv if available)."""
    try:
        from dotenv import load_dotenv
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass  # python-dotenv not installed; rely on environment


def get_workspace_path() -> str:
    explicit = os.environ.get("AGENTOS_DEFAULT_WORKSPACE", "").strip()
    if explicit:
        return explicit

    legacy = os.environ.get("DEFAULT_WORKSPACE", "").strip()
    if legacy:
        return legacy

    runtime_root = Path(__file__).resolve().parents[1]
    home = os.environ.get("HOME", "").strip()
    if runtime_root == Path("/usr/lib/agentos") and home.startswith("/home/"):
        return str(Path(home) / "agentos-ws")

    return str(runtime_root / "workspaces" / "default")
