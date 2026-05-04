#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from urllib.parse import urlparse, parse_qs


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "detail": "missing request payload"}))
        raise SystemExit(2)

    try:
        req = json.loads(sys.argv[1])
    except Exception:
        print(json.dumps({"ok": False, "detail": "invalid request payload"}))
        raise SystemExit(2)

    action = str(req.get("action", ""))
    url = str(req.get("url", ""))

    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "sleep" in qs:
            sec = float(qs["sleep"][0])
            time.sleep(sec)
    except Exception:
        pass

    fixture_details = {
        "navigate": "fixture:navigate_ok",
        "click": "fixture:click_ok",
        "fill": "fixture:fill_ok",
        "screenshot": "fixture:screenshot_ok",
        "extract_text": "fixture:extract_text_ok",
    }
    detail = fixture_details.get(action, f"fixture:unsupported:{action}")
    if action not in fixture_details:
        print(json.dumps({"ok": False, "detail": detail}, ensure_ascii=True))
        raise SystemExit(2)
    if url:
        detail += f" {url}"
    print(json.dumps({"ok": True, "detail": detail}, ensure_ascii=True))


if __name__ == "__main__":
    main()
