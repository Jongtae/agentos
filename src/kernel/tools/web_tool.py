"""
WebTool — fetches text content from URLs.
Applies domain allowlist, response size cap, and timeout.
"""
from __future__ import annotations

from pathlib import Path
from kernel.capability_substrate import build_web_access_report


def _host_matches_rule(host: str, rule: str) -> bool:
    if host == rule:
        return True
    return host.endswith("." + rule)


class WebTool:
    name = "web_fetch"

    def __init__(self, workspace_dir: str | Path | None = None, domain_allowlist: list[str] | None = None):
        """
        domain_allowlist: list of allowed domains (e.g. ["example.com"]).
                          Empty list / None = allow all.
        """
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else Path.cwd()
        self._allowlist = set(domain_allowlist or [])

    def run(self, args: dict) -> str:
        """
        args:
            url (str): the URL to fetch
        """
        url = args.get("url", "").strip()
        if not url:
            return "[error] url is required"

        report = build_web_access_report(
            self._workspace_dir,
            url,
            domain_allowlist=list(self._allowlist),
            requires_authentication=bool(args.get("requires_authentication", False)),
            interactive=bool(args.get("interactive", False)),
            compatibility_required=bool(args.get("compatibility_required", False)),
            write_manifest=False,
        )
        if report.get("native_handled", False):
            return str((report.get("proof") or {}).get("text_preview", "")) or "(no text content found)"
        if report.get("escalated_handled", False):
            return f"[escalated] {report.get('escalation_reason', 'browser_navigation_required')}"
        reason = str((report.get("proof") or {}).get("reason", "fetch failed"))
        if reason == "domain_not_allowed":
            host = url.split("://", 1)[-1].split("/", 1)[0]
            return f"[error] domain '{host}' is not in the allowlist"
        return f"[error] {reason}"
