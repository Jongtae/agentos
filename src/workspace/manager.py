"""
WorkspaceManager — loads spec.yaml and manages workspace state.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import yaml


_DEFAULT_SPEC: dict = {
    "name": "default",
    "ai_model": {
        "provider": "openai",
        "model": "gpt-4o-mini",
    },
    "tools": {"bash": True, "file": True, "web": True, "browser": False},
    "network": {
        "web_allowlist": [
            "127.0.0.1",
            "localhost",
            "example.com",
            "openai.com",
            "github.com",
        ],
        "browser_allowlist": [
            "openai.com",
            "github.com",
        ],
    },
    "permissions": {"require_approval": True},
    "memory": {
        "checkpointer": "sqlite",
        "db_path": "./data/session.sqlite",
        "store_path": "./data/memory.sqlite",
    },
    "runtime": {
        "max_steps": 12,
        "max_message_window": 20,
        "workspace_root": "./",
    },
    "kernel_engine": {
        "provider": "",
        "mode": "single",
        "codex": {
            "command": "codex",
            "timeout_sec": 90,
            "model": "gpt-4o-mini",
            "auto_bootstrap": True,
            "supervision": {
                "enabled": True,
                "restart_policy": "on_failure",
                "max_attempts": 3,
                "cooldown_sec": 5,
            },
        },
        "ollama": {
            "command": "ollama",
            "timeout_sec": 90,
            "model": "smollm2:135m-instruct-q5_K_M",
            "auto_bootstrap": True,
        },
    },
    "telegram": {
        "polling": {
            "enabled": True,
            "interval_sec": 5,
        },
        "allowed_chat_ids": [],
        "bot_token": "",
    },
}

_ALLOWED_KERNEL_PROVIDERS = {"", "none", "codex", "ollama", "claude", "gemini"}
_ALLOWED_KERNEL_MODES = {"single"}


class WorkspaceManager:
    def __init__(self, workspace_path: str):
        self.workspace_dir = Path(workspace_path).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._spec_path = self.workspace_dir / "spec.yaml"

        self.spec = self._load_spec()
        self._session_file = self.workspace_dir / "data" / "session.json"
        self._session_file.parent.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # Spec
    # ──────────────────────────────────────────

    def _load_spec(self) -> dict:
        if not self._spec_path.exists():
            self._write_default_spec(self._spec_path)
        with open(self._spec_path) as f:
            loaded = yaml.safe_load(f) or {}
        merged = self._merge(loaded, _DEFAULT_SPEC)
        self._validate_spec(merged)
        return merged

    def _write_default_spec(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(_DEFAULT_SPEC, f, default_flow_style=False, sort_keys=False)

    def _validate_spec(self, spec: dict) -> None:
        engine_cfg = spec.get("kernel_engine", {})
        provider = str(engine_cfg.get("provider", "")).strip().lower()
        mode = str(engine_cfg.get("mode", "single")).strip().lower()

        if provider not in _ALLOWED_KERNEL_PROVIDERS:
            allowed = ", ".join(sorted(_ALLOWED_KERNEL_PROVIDERS - {""}))
            raise ValueError(
                f"Unknown kernel_engine.provider '{provider}'. "
                f"Allowed: {allowed} or empty for first-run setup."
            )

        if mode not in _ALLOWED_KERNEL_MODES:
            allowed = ", ".join(sorted(_ALLOWED_KERNEL_MODES))
            raise ValueError(
                f"Unknown kernel_engine.mode '{mode}'. Allowed: {allowed}."
            )

    @staticmethod
    def _merge(user: dict, defaults: dict) -> dict:
        """Deep merge: user values override defaults."""
        result = dict(defaults)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = WorkspaceManager._merge(v, result[k])
            else:
                result[k] = v
        return result

    # ──────────────────────────────────────────
    # Session ID
    # ──────────────────────────────────────────

    def get_or_create_session_id(self) -> str:
        if self._session_file.exists():
            try:
                data = json.loads(self._session_file.read_text())
                return data["session_id"]
            except (json.JSONDecodeError, KeyError):
                pass
        return self._new_session_id()

    def _new_session_id(self) -> str:
        sid = str(uuid.uuid4())
        self._session_file.write_text(json.dumps({"session_id": sid}, indent=2))
        return sid

    def save_spec(self) -> None:
        with open(self._spec_path, "w") as f:
            yaml.dump(self.spec, f, default_flow_style=False, sort_keys=False)

    # ──────────────────────────────────────────
    # Convenience properties
    # ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.spec.get("name", "default")

    @property
    def require_approval(self) -> bool:
        required = bool(self.spec.get("permissions", {}).get("require_approval", True))
        if required:
            return True

        # Keep safe default locked unless explicitly overridden for local debugging.
        allow_unsafe = os.environ.get("AGENTOS_ALLOW_UNSAFE_APPROVAL_OFF", "").strip().lower()
        if allow_unsafe in {"1", "true", "yes", "on"}:
            return False
        return True

    @property
    def max_steps(self) -> int:
        return self.spec.get("runtime", {}).get("max_steps", 12)

    @property
    def workspace_root(self) -> str:
        return str(self.spec.get("runtime", {}).get("workspace_root", "./")).strip() or "./"

    @property
    def web_allowlist(self) -> list[str]:
        items = self.spec.get("network", {}).get("web_allowlist", [])
        if not isinstance(items, list):
            return []
        return [str(x).strip().lower() for x in items if str(x).strip()]

    @property
    def browser_allowlist(self) -> list[str]:
        items = self.spec.get("network", {}).get("browser_allowlist", [])
        if not isinstance(items, list):
            return []
        return [str(x).strip().lower() for x in items if str(x).strip()]

    @property
    def memory_store_path(self) -> str:
        raw = self.spec.get("memory", {}).get("store_path", "./data/memory.sqlite")
        return str(self.workspace_dir / raw)

    @property
    def checkpointer_type(self) -> str:
        return self.spec.get("memory", {}).get("checkpointer", "inmemory")

    @property
    def checkpointer_db_path(self) -> str:
        raw = self.spec.get("memory", {}).get("db_path", "./data/session.sqlite")
        return str(self.workspace_dir / raw)

    @property
    def kernel_engine_provider(self) -> str:
        return str(self.spec.get("kernel_engine", {}).get("provider", "")).strip().lower()

    @property
    def kernel_engine_mode(self) -> str:
        return str(self.spec.get("kernel_engine", {}).get("mode", "single")).strip().lower()

    @property
    def codex_command(self) -> str:
        return str(
            self.spec.get("kernel_engine", {}).get("codex", {}).get("command", "codex")
        ).strip()

    @property
    def codex_timeout_sec(self) -> int:
        raw = self.spec.get("kernel_engine", {}).get("codex", {}).get("timeout_sec", 90)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 90

    @property
    def codex_model(self) -> str:
        return str(
            self.spec.get("kernel_engine", {}).get("codex", {}).get("model", "gpt-4o-mini")
        ).strip() or "gpt-4o-mini"

    @property
    def codex_supervision_enabled(self) -> bool:
        return bool(
            self.spec.get("kernel_engine", {}).get("codex", {}).get("supervision", {}).get("enabled", True)
        )

    @property
    def codex_restart_policy(self) -> str:
        return str(
            self.spec.get("kernel_engine", {}).get("codex", {}).get("supervision", {}).get("restart_policy", "on_failure")
        ).strip() or "on_failure"

    @property
    def codex_max_attempts(self) -> int:
        raw = self.spec.get("kernel_engine", {}).get("codex", {}).get("supervision", {}).get("max_attempts", 3)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 3

    @property
    def codex_cooldown_sec(self) -> int:
        raw = self.spec.get("kernel_engine", {}).get("codex", {}).get("supervision", {}).get("cooldown_sec", 5)
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 5

    @property
    def ollama_command(self) -> str:
        return str(
            self.spec.get("kernel_engine", {}).get("ollama", {}).get("command", "ollama")
        ).strip()

    @property
    def ollama_timeout_sec(self) -> int:
        raw = self.spec.get("kernel_engine", {}).get("ollama", {}).get("timeout_sec", 90)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 90

    @property
    def ollama_model(self) -> str:
        return str(
            self.spec.get("kernel_engine", {}).get("ollama", {}).get("model", "smollm2:135m-instruct-q5_K_M")
        ).strip() or "smollm2:135m-instruct-q5_K_M"

    def set_kernel_engine_provider(self, provider: str) -> None:
        normalized = str(provider).strip().lower()
        if normalized not in _ALLOWED_KERNEL_PROVIDERS:
            allowed = ", ".join(sorted(_ALLOWED_KERNEL_PROVIDERS - {""}))
            raise ValueError(f"Invalid provider '{provider}'. Allowed: {allowed}")

        self.spec.setdefault("kernel_engine", {})
        self.spec["kernel_engine"]["provider"] = normalized
        self.save_spec()
