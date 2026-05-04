"""
Planner — converts user intent + context into a structured Plan.

The Planner uses the LLM to produce a JSON plan. It never executes anything.
Output: Plan with a list of Step objects that the Executor will run.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_TOOL_ORDER = [
    "bash",
    "document_access",
    "file_read",
    "file_write",
    "file_list",
    "web_fetch",
    "browser_run",
]

_TOOL_SPECS = {
    "bash": (
        "execute shell commands in the workspace directory",
        '{ "command": "shell command string" }',
    ),
    "document_access": (
        "read a supported local document through the native document substrate",
        '{ "path": "relative/path/to/document.md|.json|.html|.txt" }',
    ),
    "file_read": (
        "read a file's contents through the compatibility file path",
        '{ "path": "relative/path/to/file" }',
    ),
    "file_write": (
        "write content to a file",
        '{ "path": "relative/path", "content": "text", "overwrite": false }',
    ),
    "file_list": (
        "list directory contents",
        '{ "path": "relative/directory/path" }',
    ),
    "web_fetch": (
        "fetch text content from a URL",
        '{ "url": "https://example.com" }',
    ),
    "browser_run": (
        "execute isolated browser actions (navigate/click/type/read_text)",
        '{ "action": "navigate|click|type|read_text", "url": "https://example.com", "selector": "#id", "value": "text" }',
    ),
}


# ──────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────

@dataclass
class Step:
    tool_name: str          # "bash" | "file_read" | "file_write" | "file_list" | "web_fetch"
    description: str        # human-readable description
    args: dict              # tool-specific arguments
    is_destructive: bool = False  # True → always requires approval


@dataclass
class Plan:
    summary: str
    steps: list[Step] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are the planning component of AgentOS — an AI Kernel OS.

Your ONLY job is to produce a JSON execution plan from a user intent.
You do NOT execute anything. You produce a plan that the runtime will execute.

Available tools:
{tool_lines}

Output ONLY valid JSON — no prose, no markdown fences, no explanation:
{{
  "summary": "one sentence describing the overall plan",
  "steps": [
    {{
      "tool_name": "bash",
      "description": "what this step does",
      "args": {{ "command": "ls -la" }},
      "is_destructive": false
    }}
  ]
}}

Rules:
- Keep steps minimal — prefer fewer, targeted steps over many small ones
- Set is_destructive=true for: delete operations, overwriting files, sending data externally
- Never include secrets or API keys in args
- Never use a tool that is not listed in Available tools
- If the intent is simple and can be answered without tools, return steps: []
  with summary containing your direct answer
"""


def _build_system_prompt(available_tools: list[str]) -> str:
    lines: list[str] = []
    for tool_name in _TOOL_ORDER:
        if tool_name not in available_tools:
            continue
        description, args_spec = _TOOL_SPECS[tool_name]
        lines.append(f"- {tool_name:11}: {description}")
        lines.append(f"                args: {args_spec}")

    if not lines:
        lines.append("- (none)      : no tools available; return direct answer in summary with steps: []")

    return _SYSTEM_PROMPT_TEMPLATE.format(tool_lines="\n".join(lines))


# ──────────────────────────────────────────────────────────────
# Planner class
# ──────────────────────────────────────────────────────────────

class Planner:
    def __init__(self, llm, available_tools: list[str] | None = None):
        self._llm = llm
        if available_tools is None:
            available_tools = ["bash", "document_access", "file_read", "file_write", "file_list", "web_fetch"]
        available_set = set(available_tools)
        self._available_tools = [name for name in _TOOL_ORDER if name in available_set]
        self._system_prompt = _build_system_prompt(self._available_tools)

    def plan(self, intent: str, context: str = "") -> Plan:
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
        except ImportError:
            # Keep codex-only runtime path usable even when langchain deps are absent.
            class _Msg:
                def __init__(self, msg_type: str, content: str):
                    self.type = msg_type
                    self.content = content

            SystemMessage = lambda content: _Msg("system", content)  # noqa: E731
            HumanMessage = lambda content: _Msg("human", content)  # noqa: E731

        user_content = intent
        if context:
            user_content = f"Context from memory:\n{context}\n\nUser intent: {intent}"

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            response = self._llm.invoke(messages)
            return self._parse(response.content)
        except Exception as e:
            logger.error("Planner LLM call failed: %s", e)
            return Plan(
                summary=f"[planner error] {e}",
                steps=[],
            )

    def _parse(self, raw: str) -> Plan:
        text = raw.strip()

        # Strip markdown fences if present
        if "```" in text:
            blocks = text.split("```")
            for block in blocks[1::2]:   # odd-indexed = inside fences
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                if block.startswith("{"):
                    text = block
                    break

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Plan JSON parse error: %s\nRaw response: %s", e, raw[:300])
            # Fallback: treat the entire response as a direct answer
            return Plan(summary=raw.strip(), steps=[])

        steps = []
        for s in data.get("steps", []):
            if not isinstance(s, dict):
                continue
            tool = s.get("tool_name", "")
            if not tool:
                continue
            if tool not in self._available_tools:
                logger.info("Planner dropped disallowed tool step: %s", tool)
                continue
            steps.append(Step(
                tool_name=tool,
                description=s.get("description", ""),
                args=s.get("args", {}),
                is_destructive=bool(s.get("is_destructive", False)),
            ))

        return Plan(
            summary=data.get("summary", ""),
            steps=steps,
        )
