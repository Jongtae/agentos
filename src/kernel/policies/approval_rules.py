"""
Approval Rules — decides whether a Step requires human approval before execution.
Approval decisions live here, NOT inside tool implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .command_policy import classify

if TYPE_CHECKING:
    from kernel.planner.planner import Step


@dataclass
class ApprovalRequest:
    step_index: int
    tool_name: str
    description: str
    command_or_path: str
    risk_reason: str


@dataclass(frozen=True)
class BrowserNavigationDecision:
    state: str  # allowed | approval_required | blocked
    reason: str


def classify_browser_navigation(current_url: str, target_url: str) -> BrowserNavigationDecision:
    """
    Classify browser domain transition risk.
    """
    try:
        parsed = urlparse(target_url)
    except Exception:
        return BrowserNavigationDecision(state="blocked", reason="invalid target url")

    if parsed.scheme not in ("http", "https"):
        return BrowserNavigationDecision(state="blocked", reason="only http/https navigation allowed")

    host = parsed.hostname or ""
    host_l = host.lower()
    if host_l in ("localhost", "0.0.0.0", "::1") or host_l.startswith("127."):
        return BrowserNavigationDecision(state="blocked", reason="local/admin endpoint blocked")

    denylist = _parse_domain_rules(os.environ.get("AGENTOS_BROWSER_DOMAIN_DENYLIST", ""))
    for rule in denylist:
        if _host_matches_rule(host_l, rule):
            return BrowserNavigationDecision(
                state="blocked",
                reason=f"denylisted domain: {rule}",
            )

    allowlist = _parse_domain_rules(os.environ.get("AGENTOS_BROWSER_DOMAIN_ALLOWLIST", ""))
    for rule in allowlist:
        if _host_matches_rule(host_l, rule):
            return BrowserNavigationDecision(
                state="allowed",
                reason=f"allowlisted domain: {rule}",
            )

    if not current_url:
        return BrowserNavigationDecision(state="allowed", reason="initial navigation")

    current = urlparse(current_url)
    current_host = (current.hostname or "").lower()
    if current_host == host_l:
        return BrowserNavigationDecision(state="allowed", reason="same-domain navigation")

    return BrowserNavigationDecision(
        state="approval_required",
        reason="cross-domain navigation requires approval",
    )


def _parse_domain_rules(raw: str) -> list[str]:
    rules = []
    for item in raw.split(","):
        rule = item.strip().lower()
        if not rule:
            continue
        rules.append(rule)
    return rules


def _host_matches_rule(host: str, rule: str) -> bool:
    if host == rule:
        return True
    return host.endswith("." + rule)


def browser_policy_config_from_env() -> dict:
    return {
        "allowlist": _parse_domain_rules(os.environ.get("AGENTOS_BROWSER_DOMAIN_ALLOWLIST", "")),
        "denylist": _parse_domain_rules(os.environ.get("AGENTOS_BROWSER_DOMAIN_DENYLIST", "")),
    }


class PolicyEngine:
    """
    Evaluates Steps and determines approval requirements.

    Rules (in priority order):
      1. Step.is_destructive=True         → always approval
      2. bash: command classified blocked  → refuse outright
      3. bash: command classified approval_required → approval
      4. file_write with overwrite=True   → approval
      5. Everything else                  → allowed
    """

    def __init__(self, require_approval: bool = True):
        self.require_approval = require_approval
        self._browser_current_url = ""
        self._last_browser_decision = BrowserNavigationDecision(state="not_started", reason="not_started")

    def begin_run(self) -> None:
        """Reset per-run policy state."""
        self._browser_current_url = ""
        self._last_browser_decision = BrowserNavigationDecision(state="not_started", reason="not_started")

    def _browser_decision(self, step: "Step") -> BrowserNavigationDecision | None:
        if step.tool_name != "browser_run":
            return None
        action = str(step.args.get("action", "navigate"))
        if action != "navigate":
            return None
        target = str(step.args.get("url", ""))
        decision = classify_browser_navigation(self._browser_current_url, target)
        self._last_browser_decision = decision
        return decision

    def requires_approval(self, step: "Step") -> bool:
        """True if the step needs user approval before execution."""
        if not self.require_approval:
            return False

        if step.is_destructive:
            return True

        if step.tool_name == "bash":
            cmd = step.args.get("command", "")
            cls = classify(cmd)
            return cls == "approval_required"  # "blocked" is handled separately

        if step.tool_name == "file_write":
            return step.args.get("overwrite", False)

        browser_decision = self._browser_decision(step)
        if browser_decision is not None:
            return browser_decision.state == "approval_required"

        return False

    def is_blocked(self, step: "Step") -> bool:
        """True if the step must be refused (no approval possible)."""
        if step.tool_name == "bash":
            cmd = step.args.get("command", "")
            return classify(cmd) == "blocked"
        browser_decision = self._browser_decision(step)
        if browser_decision is not None:
            return browser_decision.state == "blocked"
        return False

    def build_request(self, step: "Step", step_index: int) -> ApprovalRequest:
        """Build a human-readable approval request for display."""
        if step.tool_name == "bash":
            cmd = step.args.get("command", "")
            reason = "Command requires approval (not in safe allowlist)"
        elif step.tool_name == "file_write":
            cmd = step.args.get("path", "")
            reason = "File will be overwritten"
        elif step.tool_name == "browser_run":
            cmd = step.args.get("url", "")
            decision = self._browser_decision(step)
            reason = decision.reason if decision else "Browser navigation requires approval"
        else:
            cmd = str(step.args)
            reason = f"Destructive action: {step.description}"

        return ApprovalRequest(
            step_index=step_index,
            tool_name=step.tool_name,
            description=step.description,
            command_or_path=cmd,
            risk_reason=reason,
        )

    def on_step_executed(self, step: "Step", result: str) -> None:
        """
        Update policy state after successful step execution.
        """
        if step.tool_name != "browser_run":
            return
        action = str(step.args.get("action", "navigate"))
        if action != "navigate":
            return
        if result.startswith("[error]"):
            return
        self._browser_current_url = str(step.args.get("url", ""))

    @property
    def browser_current_url(self) -> str:
        return self._browser_current_url

    @property
    def last_browser_decision(self) -> BrowserNavigationDecision:
        return self._last_browser_decision
