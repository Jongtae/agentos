"""Development-only PA1 worktree delegation record validation.

This repository tooling is deliberately outside ``personal_agent`` so runtime
and connector code cannot depend on issue, branch, pull-request, or worker
orchestration metadata.
"""

from dataclasses import dataclass
import re


def _nonempty(value: object, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return value


@dataclass(frozen=True)
class WorktreeDelegationRecord:
    """Redacted PA1 worktree ownership record; never an authority grant."""

    issue: int
    branch: str
    base_sha: str
    owned_files: tuple[str, ...]
    requested_profile: str
    tool_accepted_setting: str
    observed_execution_setting: str = "unknown"

    def __post_init__(self) -> None:
        if isinstance(self.issue, bool) or not isinstance(self.issue, int) or self.issue <= 0:
            raise ValueError("issue must be a positive integer")
        _nonempty(self.branch, "branch")
        if not isinstance(self.base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", self.base_sha):
            raise ValueError("base_sha must be a full lowercase commit SHA")
        files = tuple(sorted(self.owned_files))
        if not files or len(files) != len(set(files)) or any(not isinstance(path, str) or not path for path in files):
            raise ValueError("owned_files must contain unique paths")
        object.__setattr__(self, "owned_files", files)
        if self.requested_profile not in {"economy", "standard", "critical"}:
            raise ValueError("requested_profile is not recognized")
        _nonempty(self.tool_accepted_setting, "tool_accepted_setting")
        _nonempty(self.observed_execution_setting, "observed_execution_setting")

    def as_dict(self) -> dict:
        return {
            "issue": self.issue,
            "branch": self.branch,
            "base_sha": self.base_sha,
            "owned_files": list(self.owned_files),
            "requested_profile": self.requested_profile,
            "tool_accepted_setting": self.tool_accepted_setting,
            "observed_execution_setting": self.observed_execution_setting,
        }
