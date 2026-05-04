from __future__ import annotations

from kernel.engine.base import KernelEngine


class EngineRouter:
    """Single-mode router for kernel engines."""

    def __init__(self, mode: str, engines: dict[str, KernelEngine]):
        if mode != "single":
            raise ValueError(f"Unsupported kernel_engine mode: {mode}. Only 'single' is supported.")
        self._mode = mode
        self._engines = engines

    def get_engine(self, provider: str) -> KernelEngine:
        key = (provider or "").strip().lower()
        engine = self._engines.get(key)
        if not engine:
            available = ", ".join(sorted(self._engines.keys()))
            raise ValueError(f"Unknown kernel engine provider: '{provider}'. Available: {available}")
        return engine
