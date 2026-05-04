#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path


def _fail(detail: str, code: int = 2) -> None:
    print(json.dumps({"ok": False, "detail": detail}, ensure_ascii=True))
    raise SystemExit(code)


def main() -> None:
    if len(sys.argv) < 2:
        _fail("missing request payload")

    try:
        req = json.loads(sys.argv[1])
    except Exception:
        _fail("invalid request payload")

    action = str(req.get("action", ""))
    url = str(req.get("url", ""))
    selector = str(req.get("selector", ""))
    value = str(req.get("value", ""))

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        _fail("playwright dependency is not installed")

    if action not in ("navigate", "click", "fill", "screenshot", "extract_text"):
        _fail(f"unsupported action: {action}")
    if action in ("navigate", "extract_text") and not url:
        _fail("url is required for this action")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=5000)

            detail = ""
            if action == "navigate":
                detail = f"playwright navigate ok {url}"
            elif action == "click":
                if not selector:
                    _fail("selector is required for click")
                page.click(selector, timeout=3000)
                detail = f"playwright click ok {selector}"
            elif action == "fill":
                if not selector:
                    _fail("selector is required for fill")
                page.fill(selector, value, timeout=3000)
                detail = f"playwright fill ok {selector}"
            elif action == "screenshot":
                out = Path(tempfile.gettempdir()) / "agentos-playwright-shot.png"
                page.screenshot(path=str(out), full_page=True)
                detail = f"playwright screenshot ok {out}"
            elif action == "extract_text":
                if selector:
                    text = page.locator(selector).first.inner_text(timeout=3000)
                else:
                    text = page.inner_text("body", timeout=3000)
                text = " ".join(text.split())[:200]
                detail = f"playwright extract_text ok {text}"

            context.close()
            browser.close()
            print(json.dumps({"ok": True, "detail": detail}, ensure_ascii=True))
    except Exception as e:
        _fail(f"playwright worker failed: {e}", code=1)


if __name__ == "__main__":
    main()
