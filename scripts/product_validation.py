"""Evidence-first product validation for a Personal AgentOS release."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import subprocess
import time


@dataclass
class Finding:
    id: str
    title: str
    scope: str
    status: str
    evidence: str
    remediation: str = ""


class ProductValidator:
    """Collect only redacted, reproducible evidence about release claims."""

    def __init__(self, root: Path, runner=subprocess.run):
        self.root = Path(root).resolve()
        self.runner = runner
        self.findings: list[Finding] = []

    def add(self, id, title, scope, status, evidence, remediation=""):
        self.findings.append(Finding(id, title, scope, status, evidence, remediation))

    def text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def command(self, args, title, scope="v1", required=True, cwd=None):
        try:
            result = self.runner(args, cwd=str(cwd or self.root), text=True, capture_output=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.add(title.lower().replace(" ", "-"), title, scope, "failed" if required else "blocked", str(exc))
            return False
        if result.returncode == 0:
            self.add(title.lower().replace(" ", "-"), title, scope, "passed", "command succeeded: " + " ".join(args))
            return True
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()[-1200:]
        self.add(title.lower().replace(" ", "-"), title, scope, "failed" if required else "blocked", output or "command failed")
        return False

    def documentation(self):
        task = self.text("TASKS.md")
        roadmap = self.text("docs/roadmap.md")
        quickstart = self.text("QUICKSTART.md")
        stale = []
        for phrase in ("| M3 | Persistent runtime and official server install | Planned |", "| M4 | Role and tool extension contract | Planned |", "| M5 | v1 release acceptance | Planned |", "PDF/Office extraction is not implemented"):
            if phrase in task or phrase in quickstart:
                stale.append(phrase)
        delivered = (
            ("## M3 — Personal Telegram bot and first work", "## M3 — continuity and installation"),
            ("## M4 — Personal context inbox", "## M4 — extensibility"),
            ("## M5 — Trusted assistants and portability", "## M5 — v1 release"),
        )
        for headings in delivered:
            heading = next((candidate for candidate in headings if candidate in roadmap), headings[0])
            start = roadmap.find(heading)
            if start < 0:
                stale.append(heading + " is missing")
                continue
            end = roadmap.find("\n## ", start + 1)
            section = roadmap[start: end if end >= 0 else len(roadmap)]
            if not any(marker in section.casefold() for marker in ("completed", "delivered")):
                stale.append(heading + " has no completion record")
        if stale:
            self.add("DOC-001", "Published documents match v1 capability", "v1", "failed", "; ".join(stale), "Update user and delivery documents with the current supported scope and evidence.")
        else:
            self.add("DOC-001", "Published documents match v1 capability", "v1", "passed", "README, quickstart, tasks, and roadmap contain current v1 statements.")

    def source_contracts(self):
        service = self.text("src/personal_agent/quickstart_service.py")
        runtime = self.text("src/personal_agent/agent_runtime.py")
        if all(token in service for token in ("model_ready", "document_boundary", "connect_telegram")) and "delegate_agent" in runtime:
            self.add("RT-001", "Shared agent safety contracts are present", "v1", "passed", "Model readiness, document approval, Telegram pairing, and bounded delegation are implemented in the runtime.")
        else:
            self.add("RT-001", "Shared agent safety contracts are present", "v1", "failed", "One or more required runtime safeguards are absent.")
        plugins = self.text("src/personal_agent/plugins.py")
        quickstart = self.text("src/personal_agent/quickstart.py")
        reachable = "PluginRegistry" in quickstart or "/api/plugins" in quickstart or " plugins " in quickstart
        if "class PluginRegistry" in plugins and reachable:
            self.add("EXT-001", "Plugin lifecycle is reachable from AgentOS", "v1", "passed", "The manifest registry is reachable through a supported AgentOS surface.")
        elif "class PluginRegistry" in plugins:
            self.add("EXT-001", "Plugin lifecycle is reachable from AgentOS", "v1", "failed", "The registry has unit coverage but no CLI or authenticated API surface.", "Expose a safe local plugin command or authenticated settings API, then add an end-to-end lifecycle test.")
        else:
            self.add("EXT-001", "Plugin lifecycle is reachable from AgentOS", "v1", "failed", "No plugin lifecycle implementation was found.")

    def vision_gaps(self):
        self.add("VISION-001", "Native desktop and mobile clients", "future", "gap", "The product vision requires companion apps; v1 intentionally provides a responsive web UI and Telegram only.", "Define device pairing, revocation, notifications, and a first native client milestone.")
        self.add("VISION-002", "Additional message channels", "future", "gap", "Telegram is the first implemented channel; KakaoTalk and WeChat require separate platform feasibility and approval designs.", "Create channel-specific integration epics after Telegram contract stabilization.")
        self.add("VISION-003", "Managed and multi-tenant hosting", "future", "gap", "v1 supports one owner on macOS or one Linux/VPS runtime; hosted tenancy is excluded by the PRD.", "Design tenant isolation, billing, and operations separately from the single-owner runtime.")

    def local_checks(self, include_unit=False, include_homebrew=False, include_compose=False):
        if include_unit:
            self.command(["python3", "-m", "unittest", "discover", "-s", "tests", "-q"], "Automated contract suite")
        if include_homebrew:
            binary = shutil.which("agentos")
            if not binary:
                self.add("INST-001", "Installed Homebrew acceptance", "v1", "blocked", "agentos is not on PATH; run this check from a Homebrew-installed machine.")
            else:
                self.command(["python3", "scripts/quickstart_install_check.py"], "Installed Homebrew acceptance")
        if include_compose:
            if not shutil.which("docker"):
                self.add("OPS-001", "Docker Compose configuration", "v1", "blocked", "Docker is not installed on this machine.")
            else:
                self.command(["docker", "compose", "config", "--quiet"], "Docker Compose configuration")
                self.command(["python3", "scripts/verify_compose_acceptance.py"], "Docker Compose persistence acceptance")

    def live_checks(self, live_model=False, live_telegram=False):
        if live_model:
            self.command(["python3", "scripts/verify_general_agent.py", "--installed"], "Live model and capability acceptance")
            self.command(["python3", "scripts/verify_document_acceptance.py"], "Live document acceptance")
            self.command(["python3", "scripts/verify_document_boundary.py"], "Live document boundary acceptance")
        else:
            self.add("LIVE-001", "Live model and capability acceptance", "v1", "blocked", "Not requested; requires an existing model credential and can consume provider quota.")
        if live_telegram:
            self.add("LIVE-002", "Live Telegram acceptance", "v1", "blocked", "Manual paired-account check required: send a request after restart and verify shared history and delivery evidence.")
        else:
            self.add("LIVE-002", "Live Telegram acceptance", "v1", "blocked", "Not requested; requires the already paired private Telegram account.")

    def report(self):
        counts = {status: sum(f.status == status for f in self.findings) for status in ("passed", "failed", "blocked", "gap")}
        return {"generated_at": time.time(), "baseline": self._baseline(), "summary": counts, "findings": [asdict(f) for f in self.findings]}

    def _baseline(self):
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, text=True, capture_output=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"


def markdown(report: dict) -> str:
    lines = ["# Product validation report", "", f"Baseline: `{report['baseline']}`", "", "| Status | Count |", "| --- | ---: |"]
    lines += [f"| {status} | {count} |" for status, count in report["summary"].items()]
    lines += ["", "| ID | Requirement | Scope | Status | Evidence |", "| --- | --- | --- | --- | --- |"]
    for item in report["findings"]:
        evidence = item["evidence"].replace("\n", " ").replace("|", "\\|")[:300]
        lines.append(f"| {item['id']} | {item['title']} | {item['scope']} | {item['status']} | {evidence} |")
    return "\n".join(lines) + "\n"
