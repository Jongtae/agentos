"""
Browser tool isolation interface (Phase 3 scaffold).

This module intentionally does not execute browser automation in this phase.
It defines contracts and a disabled-by-default implementation boundary.
"""
from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from kernel.policies.approval_rules import classify_browser_navigation


BrowserAction = Literal["navigate", "click", "fill", "screenshot", "extract_text"]


@dataclass(frozen=True)
class BrowserIsolationRequest:
    action: BrowserAction
    url: str = ""
    selector: str = ""
    value: str = ""


@dataclass(frozen=True)
class BrowserIsolationResult:
    ok: bool
    detail: str


@dataclass(frozen=True)
class BrowserBackendSelection:
    requested: str
    selected: str
    fallback_reason: str


class BrowserIsolationBoundary(Protocol):
    @property
    def name(self) -> str:
        ...

    def is_enabled(self) -> bool:
        ...

    def validate(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        ...

    def run(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        ...


class BrowserToolIsolationStub:
    """
    Disabled implementation used until dedicated browser sandbox is introduced.
    """

    @property
    def name(self) -> str:
        return "browser_isolated"

    def is_enabled(self) -> bool:
        return False

    def validate(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        _ = request
        return BrowserIsolationResult(
            ok=False,
            detail="browser tool is not enabled in this phase",
        )

    def run(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        _ = request
        return BrowserIsolationResult(
            ok=False,
            detail="browser tool is not enabled in this phase",
        )

    def run_tool(self, args: dict) -> str:
        request = BrowserIsolationRequest(
            action=str(args.get("action", "navigate")),
            url=str(args.get("url", "")),
            selector=str(args.get("selector", "")),
            value=str(args.get("value", "")),
        )
        result = self.validate(request)
        if not result.ok:
            return f"[error] {result.detail}"
        result = self.run(request)
        return result.detail if result.ok else f"[error] {result.detail}"

    def run_cli(self, args: dict) -> str:
        return self.run_tool(args)


class BrowserWorkerIsolationBoundary:
    """
    Browser isolation boundary using a dedicated worker subprocess.
    """

    def __init__(self, worker_cmd: list[str] | None = None, timeout_sec: int = 5):
        if worker_cmd is None:
            root = Path(__file__).resolve().parents[3]
            worker = root / "scripts" / "browser_worker_stub.py"
            worker_cmd = [sys.executable, str(worker)]
        self._worker_cmd = worker_cmd
        self._timeout_sec = timeout_sec
        self._last_url = ""

    @property
    def name(self) -> str:
        return "browser_worker_boundary"

    def is_enabled(self) -> bool:
        return True

    def validate(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        if request.action not in ("navigate", "click", "fill", "screenshot", "extract_text"):
            return BrowserIsolationResult(ok=False, detail=f"unsupported action: {request.action}")
        if request.action in ("navigate", "extract_text") and not request.url:
            return BrowserIsolationResult(ok=False, detail="url is required for this action")
        if request.action == "navigate":
            nav = classify_browser_navigation(self._last_url, request.url)
            if nav.state == "blocked":
                return BrowserIsolationResult(ok=False, detail=f"blocked: {nav.reason}")
            if nav.state == "approval_required":
                return BrowserIsolationResult(ok=False, detail=f"approval_required: {nav.reason}")
        return BrowserIsolationResult(ok=True, detail="ok")

    def run(self, request: BrowserIsolationRequest) -> BrowserIsolationResult:
        check = self.validate(request)
        if not check.ok:
            return check

        payload = {
            "action": request.action,
            "url": request.url,
            "selector": request.selector,
            "value": request.value,
        }
        try:
            proc = subprocess.run(
                [*self._worker_cmd, json.dumps(payload)],
                capture_output=True,
                text=True,
                timeout=self._timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return BrowserIsolationResult(
                ok=False,
                detail=f"worker timed out after {self._timeout_sec}s",
            )

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip() or "worker failed"
            return BrowserIsolationResult(ok=False, detail=stderr)

        stdout = proc.stdout.strip()
        try:
            response = json.loads(stdout.splitlines()[-1] if stdout else "{}")
        except Exception:
            return BrowserIsolationResult(ok=False, detail="invalid worker response")

        if request.action == "navigate" and response.get("ok", False):
            self._last_url = request.url

        return BrowserIsolationResult(
            ok=bool(response.get("ok", False)),
            detail=str(response.get("detail", "")),
        )


class BrowserPlaywrightIsolationBoundary(BrowserWorkerIsolationBoundary):
    """
    Browser isolation boundary using playwright-enabled worker subprocess.
    """

    def __init__(self, worker_cmd: list[str] | None = None, timeout_sec: int = 8):
        if worker_cmd is None:
            root = Path(__file__).resolve().parents[3]
            worker = root / "scripts" / "browser_worker_playwright.py"
            worker_cmd = [sys.executable, str(worker)]
        super().__init__(worker_cmd=worker_cmd, timeout_sec=timeout_sec)

    @property
    def name(self) -> str:
        return "browser_playwright_boundary"


def is_browser_tool_enabled() -> bool:
    raw = os.environ.get("AGENTOS_ENABLE_BROWSER_TOOL", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def browser_worker_timeout_sec(default: int = 5) -> int:
    raw = os.environ.get("AGENTOS_BROWSER_WORKER_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except Exception:
        return default


def _is_playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def resolve_browser_backend() -> BrowserBackendSelection:
    raw = os.environ.get("AGENTOS_BROWSER_BACKEND", "").strip().lower()
    requested = raw or "worker"
    if requested in ("", "worker"):
        return BrowserBackendSelection(requested="worker", selected="worker", fallback_reason="")
    if requested == "stub":
        return BrowserBackendSelection(requested="stub", selected="stub", fallback_reason="")
    if requested == "playwright":
        if _is_playwright_available():
            return BrowserBackendSelection(
                requested="playwright",
                selected="playwright",
                fallback_reason="",
            )
        return BrowserBackendSelection(
            requested="playwright",
            selected="worker",
            fallback_reason="playwright_unavailable",
        )
    return BrowserBackendSelection(
        requested=requested,
        selected="worker",
        fallback_reason="invalid_backend",
    )


class BrowserExecutorTool:
    """
    Executor-compatible wrapper for browser worker isolation boundary.
    """

    name = "browser_run"

    def __init__(self, boundary: BrowserIsolationBoundary | None = None):
        if boundary is not None:
            self._boundary = boundary
            self._backend = BrowserBackendSelection(
                requested=boundary.name,
                selected=boundary.name,
                fallback_reason="",
            )
            return

        backend = resolve_browser_backend()
        self._backend = backend
        if backend.selected == "stub":
            self._boundary = BrowserToolIsolationStub()
        elif backend.selected == "playwright":
            self._boundary = BrowserPlaywrightIsolationBoundary(
                timeout_sec=max(2, browser_worker_timeout_sec(8))
            )
        else:
            self._boundary = BrowserWorkerIsolationBoundary(
                timeout_sec=browser_worker_timeout_sec()
            )

    @property
    def backend(self) -> BrowserBackendSelection:
        return self._backend

    def run(self, args: dict) -> str:
        request = BrowserIsolationRequest(
            action=str(args.get("action", "navigate")),
            url=str(args.get("url", "")),
            selector=str(args.get("selector", "")),
            value=str(args.get("value", "")),
        )
        result = self._boundary.run(request)
        return result.detail if result.ok else f"[error] {result.detail}"
