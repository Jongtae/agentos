#!/usr/bin/env python3
"""Deterministic local HTTP fixture for the #382 Playwright transcript.

This serves the checked-out web assets and synthetic read models only. It does
not contact a model, Telegram, or any other external service.
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "personal_agent" / "web"
LONG_MEMORY = "prefix-" + "x" * 300 + "needle-after-truncation"


class Fixture:
    events = [{"id": 1, "tool": "fixture", "status": "running", "created": 1, "summary": "첫 이벤트", "details": {}}]
    test_requests = 0
    apply_requests = 0
    task_polls = 0
    requests = []
    results = []

    @classmethod
    def task(cls, detail=False):
        task = {"id": "task-382", "title": "브라우저 회귀 확인", "status": "running", "status_kind": "active", "started_at": 1, "observed_at": cls.events[-1]["created"], "events_count": len(cls.events), "waits": [], "artifacts": [], "configured": {}, "observed": {}}
        if detail:
            task.update(events=cls.events, source_references=[], conversation={"job_id": "task-382", "workspace_id": "workspace-382"})
        return task


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def send_json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if not path.startswith("/control/"):
            Fixture.requests.append({"method": "GET", "path": path})
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif path in ("/", "/app.js", "/style.css"):
            name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[path]
            raw = (WEB / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name])
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif path == "/api/status": self.send_json({"claimed": True, "authenticated": True, "local_access": True})
        elif path == "/api/tasks":
            Fixture.task_polls += 1
            self.send_json({"tasks": [Fixture.task()], "unknown_detail_message": "fixture"})
        elif path == "/api/tasks/task-382": self.send_json({"tasks": [Fixture.task(True)], "selected": Fixture.task(True), "unknown_detail_message": "fixture"})
        elif path == "/api/home": self.send_json({"state": "working", "workspaces": [{"id": "workspace-382", "title": "회귀 프로젝트"}]})
        elif path == "/api/state": self.send_json({"settings": {"model": {"provider": "openai", "endpoint": "https://example.invalid/v1", "model": "fixture-model"}, "model_ready": False, "subscription_engines": {"engines": []}, "context_inbox": {"sources": {}, "items": []}, "telegram": {"enabled": True, "paired": True, "username": "fixture_bot"}, "document_boundary": {}}, "jobs": [{"id": "task-382", "workspace_id": "workspace-382", "status": "running", "response": None, "message": "fixture Telegram request", "channel": "telegram:fixture-owner"}, {"id": "project-job", "workspace_id": "workspace-382", "status": "succeeded", "response": "fixture project result", "message": "fixture project request", "channel": "telegram:fixture-owner"}], "tool_events": [], "healthy": True})
        elif path == "/api/personal-space": self.send_json({"memories": [{"id": "memory-exact", "memory_key": "durable-key", "content": "exact durable memory", "created": 2}, {"id": "memory-long", "content": LONG_MEMORY, "created": 1}], "context": [], "results": []})
        elif path == "/api/workspaces/workspace-382": self.send_json({"id": "workspace-382", "title": "회귀 프로젝트", "purpose": "상세/결과 저장 회귀", "results": Fixture.results, "messages": []})
        elif path == "/control/counts": self.send_json({"test_requests": Fixture.test_requests, "apply_requests": Fixture.apply_requests, "events": len(Fixture.events), "task_polls": Fixture.task_polls})
        elif path == "/control/requests": self.send_json({"requests": Fixture.requests})
        else: self.send_json({"error": path}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if not path.startswith("/control/"):
            Fixture.requests.append({"method": "POST", "path": path})
        if path == "/control/reset-observation":
            Fixture.task_polls = 0
            Fixture.requests.clear()
            self.send_json({"ok": True})
        elif path == "/control/append-event":
            Fixture.events.append({"id": len(Fixture.events) + 1, "tool": "fixture", "status": "succeeded", "created": Fixture.events[-1]["created"] + 1, "summary": "폴링으로 추가된 이벤트", "details": {}})
            self.send_json({"events": len(Fixture.events)})
        elif path == "/api/model/test":
            Fixture.test_requests += 1
            time.sleep(0.8)
            self.send_json({"ok": True})
        elif path == "/api/model":
            Fixture.apply_requests += 1
            self.send_json({"ok": True})
        elif path == "/api/workspaces/workspace-382/save-result":
            Fixture.results[:] = [{"id": "result-1", "job_id": body.get("job_id"), "content": "fixture project result", "created": 3}]
            self.send_json({"id": "workspace-382", "title": "회귀 프로젝트", "purpose": "상세/결과 저장 회귀", "results": Fixture.results, "messages": []})
        else: self.send_json({"error": path}, 404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18782)
    args = parser.parse_args()
    print(f"fixture-only http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
