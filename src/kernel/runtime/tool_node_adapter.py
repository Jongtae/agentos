from __future__ import annotations

from pathlib import Path
from typing import Literal

from kernel.broker import append_broker_events, mediate_managed_exec
from kernel.control_plane_capabilities import classify_execution_path
from kernel.planner.planner import Step


PolicyState = Literal["allowed", "approval_required", "blocked"]


class ToolNodeAdapter:
    """
    Phase 2 tool-node adapter layer.
    Bridges current tool contracts into a policy-aware node interface.
    """

    def __init__(self, tools: list, policy, workspace_dir: str | Path | None = None):
        self._tools = {t.name: t for t in tools}
        self._policy = policy
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else None

    def policy_state(self, step: Step) -> PolicyState:
        if self._policy.is_blocked(step):
            return "blocked"
        if self._policy.requires_approval(step):
            return "approval_required"
        return "allowed"

    def run_tool(self, step: Step) -> str:
        tool = self._tools.get(step.tool_name)
        if tool is None:
            available = ", ".join(sorted(self._tools.keys()))
            return f"[error] unknown tool '{step.tool_name}'. Available: {available}"
        try:
            return str(tool.run(step.args))
        except Exception as e:
            return f"[error] {step.tool_name} failed: {e}"

    def run_step(self, step: Step) -> dict:
        execution = classify_execution_path(step, self._policy)
        mediation = mediate_managed_exec(step, self._policy, step_index=0)
        if self._workspace_dir is not None:
            append_broker_events(
                self._workspace_dir,
                request=mediation.request,
                decision=mediation.decision,
                request_kind=mediation.request.kind,
            )
        state = mediation.state
        broker_payload = mediation.to_dict()
        if state == "blocked":
            return {
                "state": "blocked",
                "output": "[blocked] command refused by security policy",
                "broker": broker_payload,
                "execution": execution,
            }
        if state == "approval_required":
            req = mediation.approval_request
            return {
                "state": "approval_required",
                "output": f"[approval_required] {req.risk_reason}",
                "request": req,
                "broker": broker_payload,
                "execution": execution,
            }
        return {
            "state": "allowed",
            "output": self.run_tool(step),
            "broker": broker_payload,
            "execution": execution,
        }
