from __future__ import annotations

import os
from datetime import datetime, timezone
import uuid

from kernel.runtime.checkpoint_saver import CheckpointSaver


def is_agent_runner_enabled() -> bool:
    raw = os.environ.get("AGENTOS_USE_AGENT_RUNNER", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class AgentRunner:
    """
    Phase 2 skeleton wrapper.
    For now this delegates to KernelRuntime while preserving runtime attributes.
    """

    def __init__(self, runtime, checkpoint_saver: CheckpointSaver | None = None):
        object.__setattr__(self, "_runtime", runtime)
        object.__setattr__(self, "_checkpoint_saver", checkpoint_saver)
        object.__setattr__(self, "runner_mode", "phase2-skeleton")

    def run(self, user_input: str) -> str:
        run_id = str(uuid.uuid4())
        self._save_checkpoint(
            {
                "run_id": run_id,
                "status": "running",
                "user_input": user_input,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        try:
            result = self._runtime.run(user_input)
            self._save_checkpoint(
                {
                    "run_id": run_id,
                    "status": "completed",
                    "user_input": user_input,
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "result_preview": str(result)[:500],
                }
            )
            return result
        except Exception as e:
            self._save_checkpoint(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "user_input": user_input,
                    "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )
            raise

    def recover_last_run(self) -> dict | None:
        if self._checkpoint_saver is None:
            return None
        return self._checkpoint_saver.load_checkpoint()

    def _save_checkpoint(self, payload: dict) -> None:
        if self._checkpoint_saver is None:
            return
        self._checkpoint_saver.save_checkpoint(payload)

    def __getattr__(self, name):
        return getattr(self._runtime, name)

    def __setattr__(self, name, value):
        if name in ("_runtime", "_checkpoint_saver", "runner_mode"):
            object.__setattr__(self, name, value)
            return
        setattr(self._runtime, name, value)
