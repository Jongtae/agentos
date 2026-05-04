from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class HealthCheckResult:
    ok: bool
    reason: str
    detail: str = ""


@dataclass
class EngineRunResult:
    ok: bool
    content: str = ""
    error_type: str = ""
    error_message: str = ""
    exit_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class KernelEngine(Protocol):
    @property
    def name(self) -> str:
        ...

    def health_check(self) -> HealthCheckResult:
        ...

    def run_intent(self, intent: str, context: str = "") -> EngineRunResult:
        ...

    def invoke(self, messages: list[Any]) -> Any:
        ...
