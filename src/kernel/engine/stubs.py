from __future__ import annotations

from types import SimpleNamespace

from kernel.engine.base import EngineRunResult, HealthCheckResult


class _UnavailableEngine:
    def __init__(self, provider: str):
        self._provider = provider

    @property
    def name(self) -> str:
        return self._provider

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            ok=False,
            reason="not_implemented",
            detail=f"{self._provider} engine is not implemented yet in this prototype.",
        )

    def run_intent(self, intent: str, context: str = "") -> EngineRunResult:
        return EngineRunResult(
            ok=False,
            error_type="not_implemented",
            error_message=f"{self._provider} engine is not implemented yet.",
        )

    def invoke(self, messages: list[object]) -> SimpleNamespace:
        return SimpleNamespace(content=f"[planner error] {self._provider} engine is not implemented yet")


class ClaudeEngineStub(_UnavailableEngine):
    def __init__(self):
        super().__init__("claude")


class GeminiEngineStub(_UnavailableEngine):
    def __init__(self):
        super().__init__("gemini")


class SetupGuideEngine:
    """
    Guide-mode engine for first-run `provider=none`.
    Health check intentionally fails to drive doctor/preflight guidance,
    but runtime `invoke()` returns a deterministic no-step response.
    """

    @property
    def name(self) -> str:
        return "none"

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            ok=False,
            reason="setup_required",
            detail="Kernel engine is not configured. Run setup-engine or set-engine.",
        )

    def run_intent(self, intent: str, context: str = "") -> EngineRunResult:
        return EngineRunResult(
            ok=True,
            content=(
                "Engine setup is required before execution. "
                "Run `python src/main.py --setup-engine` or `python src/main.py --set-engine ollama`."
            ),
        )

    def invoke(self, messages: list[object]) -> SimpleNamespace:
        return SimpleNamespace(
            content=(
                '{"summary":"Engine setup is required. Run --setup-engine or --set-engine ollama.",'
                '"steps":[]}'
            )
        )
