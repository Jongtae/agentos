"""
Executor — dispatches Steps to their corresponding Tools.
No LLM, no framework dependencies.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kernel.planner.planner import Step

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self, tools: list):
        self._tools: dict[str, object] = {t.name: t for t in tools}

    def execute(self, step: "Step") -> str:
        tool = self._tools.get(step.tool_name)
        if not tool:
            available = ", ".join(self._tools.keys())
            return f"[error] unknown tool '{step.tool_name}'. Available: {available}"
        try:
            result = tool.run(step.args)
            logger.debug("Tool %s → %s chars", step.tool_name, len(str(result)))
            return str(result)
        except Exception as e:
            logger.error("Tool %s failed: %s", step.tool_name, e)
            return f"[error] {step.tool_name} failed: {e}"

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools.keys())
