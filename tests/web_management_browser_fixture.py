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
from urllib.parse import parse_qs, urlsplit

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
    memories = [{"id": "memory-exact", "memory_key": "durable-key", "content": "exact durable memory", "created": 2}, {"id": "memory-long", "content": LONG_MEMORY, "created": 1}]
    extra_memories = []
    capability_state = "enabled"
    drafts = {}
    tasks_empty = False
    model = {"provider": "openai", "endpoint": "https://example.invalid/v1", "model": "fixture-model"}
    other_results = [{"id": f"other-{index}", "job_id": f"other-job-{index}", "workspace_id": "workspace-other", "content": f"other result {index}", "created": 100 + index} for index in range(30)]
    delay_state = False
    state_inflight = False
    delay_save = False
    delay_task_detail = False
    delay_workspace_detail = False
    workspace_detail_inflight = False
    delay_records = False
    records_inflight = False
    fail_records_once = False
    file_roots = []
    file_workspace = {"references": [], "workspace": ""}
    workspace_updated = {"workspace-382": 1, "workspace-other": 2}
    rich_tasks = False
    many_tasks = False
    new_turns = 0
    new_turn_times = []
    rich_now = time.time()

    RICH_RESULT = ("**서울–도쿄 항공권 비교**\n\n- 대한항공 KE703 · 왕복 412,000원 · [예약 페이지](https://example.invalid/ke703)\n- 아시아나 OZ102 · 왕복 398,000원\n\n"
                   "가장 저렴한 조건은 `OZ102`이며, 출발 시각은 08:30입니다.\n<script>alert('x')</script> <b>raw html</b>")

    @classmethod
    def rich_task_rows(cls, detail=False):
        """Fixture-only conversation turns for presentation checks (#558 / #559 direction).

        Covers success, failure followed by an attributed retry, an identical
        request with no recorded relation, a partial result, an unknown
        delivery, and a correction that is still running.
        """
        now = cls.rich_now
        def row(task_id, title, started, status, kind, **extra):
            base = {"id": task_id, "title": title, "status": status, "status_kind": kind, "started_at": now - started, "observed_at": now - started + 40,
                    "events_count": 2, "waits": [], "artifacts": [], "configured": {}, "observed": {}}
            base.update(extra)
            return base
        cli = {"kind": "subscription", "engine": "codex", "status": "succeeded"}
        rows = {
            "task-failed": row("task-failed", "회의록 폴더 요약해서 저장해줘", 86400 * 2, "failed", "finished", error="Claude Code 엔진이 작업을 완료하지 못했습니다(종료 코드 1). 엔진 로그인이 필요합니다. 설정 › AI 연결에서 로그인을 확인하세요. 엔진 응답: Not logged in · Please run /login", route={"kind": "subscription", "engine": "claude-code", "status": "failed"}, failure_class="auth"),
            "task-retry": row("task-retry", "자 다시 해봐", 86400 * 2 - 600, "succeeded", "finished", response="회의록 3개를 요약해 **결과 폴더**에 새 파일로 저장했어요.\n\n- 9월 첫째 주 회의\n- 9월 둘째 주 회의\n- 9월 셋째 주 회의", route=cli, relation={"kind": "retry", "work_id": "task-failed"}),
            "task-done": row("task-done", "서울 도쿄 항공권 비교해줘", 3600, "succeeded", "finished", response=cls.RICH_RESULT, route=cli, events_count=3, observed_at=now - 3430),
            "task-done-again": row("task-done-again", "서울 도쿄 항공권 비교해줘", 1800, "succeeded", "finished", response=cls.RICH_RESULT, route={"kind": "direct-api", "model": "gpt-4o-mini", "status": "succeeded"}),
            "task-partial": row("task-partial", "지난달 영수증 모아줘", 900, "partial", "finished", response="영수증 2개를 찾았어요.\n\n- 9월 3일 카페 12,000원\n- 9월 9일 서점 18,500원", error="Gmail 두 번째 페이지를 읽지 못했습니다.", route=cli),
            "task-unknown": row("task-unknown", "팀에 회의 일정 보내줘", 600, "succeeded", "finished", response="회의 일정 메시지를 보냈어요.", route=cli),
            "task-correction": row("task-correction", "아니, 지난달 것만", 120, "running", "active", route={**cli, "status": "running"}, relation={"kind": "correction", "work_id": "task-partial"}),
        }
        if detail:
            def ev(i, tool, status, ago, summary, **details):
                return {"id": i, "tool": tool, "status": status, "created": now - ago, "summary": summary, "details": details}
            rows["task-failed"]["events"] = [ev(31, "subscription_engine", "running", 86400 * 2, "실행을 시작했습니다.", engine="codex", mode="bounded-agentos-mcp"), ev(32, "subscription_engine", "failed", 86400 * 2 - 40, "결과 저장 폴더가 설정되지 않아 파일을 남기지 못했습니다.", engine="codex", exit_code=1, attempt=1)]
            rows["task-retry"]["events"] = [ev(41, "subscription_engine", "running", 86400 * 2 - 600, "실행을 시작했습니다.", engine="codex", mode="bounded-agentos-mcp"), ev(42, "subscription_engine", "succeeded", 86400 * 2 - 560, "실행을 완료했습니다.", engine="codex", exit_code=0)]
            rows["task-done"]["events"] = [ev(11, "subscription_engine", "running", 3600, "실행을 시작했습니다.", engine="codex", mode="bounded-agentos-mcp"), ev(12, "web_search", "succeeded", 3500, "근거를 확인했습니다.", scope="public-web"), ev(13, "subscription_engine", "succeeded", 3440, "실행을 완료했습니다.", engine="codex", exit_code=0)]
            rows["task-done"]["source_references"] = ["https://example.invalid/ke703"]
            rows["task-done-again"]["events"] = [ev(21, "model", "succeeded", 1760, "실행을 완료했습니다.")]
            rows["task-partial"]["events"] = [ev(51, "subscription_engine", "running", 900, "실행을 시작했습니다.", engine="codex"), ev(52, "subscription_engine", "succeeded", 860, "실행을 완료했습니다.", engine="codex", exit_code=0)]
            rows["task-unknown"]["events"] = [ev(61, "subscription_engine", "running", 600, "실행을 시작했습니다.", engine="codex"), ev(62, "subscription_engine", "succeeded", 560, "실행을 완료했습니다.", engine="codex", exit_code=0)]
            rows["task-correction"]["events"] = [ev(71, "subscription_engine", "running", 120, "실행을 시작했습니다.", engine="codex", mode="bounded-agentos-mcp")]
            for value in rows.values():
                value["conversation"] = {"job_id": value["id"]}
        return rows

    @classmethod
    def rich_jobs(cls):
        rows = cls.rich_task_rows()
        messages = {"task-done": "서울 도쿄 항공권 비교해줘. 다음 주 금요일 출발, 일요일 귀국으로.", "task-done-again": "서울 도쿄 항공권 비교해줘. 다음 주 금요일 출발, 일요일 귀국으로."}
        return [{"id": key, "status": value["status"], "response": value.get("response"), "error": value.get("error"), "message": messages.get(key, value["title"]),
                 "channel": "telegram:fixture-owner", "delivery": "unknown" if key == "task-unknown" else "sent"} for key, value in rows.items()]

    @classmethod
    def task(cls, detail=False):
        task = {"id": "task-382", "title": "브라우저 회귀 확인", "status": "running", "status_kind": "active", "started_at": 1, "observed_at": cls.events[-1]["created"], "events_count": len(cls.events), "waits": [], "artifacts": [], "configured": {}, "observed": {}}
        if detail:
            task.update(events=cls.events, source_references=[], conversation={"job_id": "task-382"})
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

    @staticmethod
    def observe(method, path):
        if not path.startswith("/control/"):
            Fixture.requests.append({"method": method, "path": path})

    def reject_observed_method(self, method):
        path = urlsplit(self.path).path
        self.observe(method, path)
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_json({"error": f"{method} is not supported by this fixture"}, 405)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        self.observe("GET", path)
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
            rows = [] if Fixture.tasks_empty else [Fixture.task()]
            if Fixture.rich_tasks and not Fixture.tasks_empty:
                rows += list(Fixture.rich_task_rows().values())
            if Fixture.many_tasks and not Fixture.tasks_empty:
                # Fixture-only history across four days for long-trace navigation (#572).
                base = Fixture.rich_now
                rows += [{"id": f"task-many-{i}", "title": f"질문 {i}: 오늘 할 일 정리해줘", "status": "succeeded", "status_kind": "finished",
                          "started_at": base - 86400 * 3 - 300 + i * 5400, "observed_at": base - 86400 * 3 - 300 + i * 5400 + 30,
                          "events_count": 0, "waits": [], "artifacts": [], "configured": {}, "observed": {},
                          "response": f"답변 {i}: 할 일 세 가지를 정리했어요.", "route": {"kind": "subscription", "engine": "codex", "status": "succeeded"}}
                         for i in range(40)]
                rows += [{"id": f"task-new-{i}", "title": f"새 질문 {i}", "status": "succeeded", "status_kind": "finished",
                          "started_at": Fixture.new_turn_times[i], "observed_at": Fixture.new_turn_times[i] + 1, "events_count": 0, "waits": [], "artifacts": [],
                          "configured": {}, "observed": {}, "response": f"새 답변 {i}", "route": {"kind": "subscription", "engine": "codex", "status": "succeeded"}}
                         for i in range(Fixture.new_turns)]
                rows = sorted(rows, key=lambda row: row["started_at"])[-40:]
            self.send_json({"tasks": rows, "unknown_detail_message": "fixture"})
        elif path.startswith("/api/tasks/task-") and Fixture.rich_tasks and path.rsplit("/", 1)[-1] in Fixture.rich_task_rows():
            selected = Fixture.rich_task_rows(True)[path.rsplit("/", 1)[-1]]
            self.send_json({"tasks": [selected], "selected": selected, "unknown_detail_message": "fixture"})
        elif path == "/api/tasks/task-382":
            selected = Fixture.task(True)
            if Fixture.delay_task_detail:
                Fixture.delay_task_detail = False
                time.sleep(3.0)
            self.send_json({"tasks": [selected], "selected": selected, "unknown_detail_message": "fixture"})
        elif path == "/api/home": self.send_json({"state": "working", "workspaces": [{"id": "workspace-382", "title": "회귀 프로젝트", "updated": Fixture.workspace_updated["workspace-382"]}, {"id": "workspace-other", "title": "다른 프로젝트", "updated": Fixture.workspace_updated["workspace-other"]}]})
        elif path == "/api/state":
            model = dict(Fixture.model)
            file_roots = list(Fixture.file_roots)
            file_workspace = {"references": [dict(item) for item in Fixture.file_workspace["references"]], "workspace": Fixture.file_workspace["workspace"]}
            if Fixture.delay_state:
                Fixture.delay_state = False
                Fixture.state_inflight = True
                time.sleep(1.5)
                Fixture.state_inflight = False
            self.send_json({"settings": {"model": model, "model_ready": False, "subscription_engines": ({"selected": "codex", "engines": [{"id": "codex", "name": "Codex", "installed": True, "connected": True, "login": {"state": "signed-in", "checked_at": Fixture.rich_now}}, {"id": "claude-code", "name": "Claude Code", "installed": True, "connected": False, "credential": False, "login": {"state": "signed-out", "checked_at": Fixture.rich_now}}]} if Fixture.rich_tasks else {"engines": []}), "file_roots": [{"path": path} for path in file_roots], "file_workspace": file_workspace, "context_inbox": {"sources": {}, "items": []}, "telegram": {"enabled": True, "paired": True, "username": "fixture_bot"}, "conversation_settings": {"state": "read", "capabilities": [{"id": "google-drive-read", "kind": "connector", "state": Fixture.capability_state, "recovery": "Owner can resume after review."}]}, "document_boundary": {}}, "jobs": [{"id": "task-382", "status": "running", "response": None, "message": "fixture Telegram request", "channel": "telegram:fixture-owner"}] + (Fixture.rich_jobs() if Fixture.rich_tasks else []) + [{"id": "project-job", "status": "succeeded", "response": "fixture project result", "message": "fixture project request", "channel": "telegram:fixture-owner"}], "tool_events": [], "healthy": True})
        elif path == "/api/personal-space": self.send_json({"memories": Fixture.memories, "context": [], "results": (Fixture.results + Fixture.other_results)[-50:]})
        elif path == "/api/personal-records":
            if Fixture.fail_records_once:
                Fixture.fail_records_once = False
                self.send_json({"error": "fixture records refresh failed"}, 500)
                return
            query = parse_qs(parsed.query).get("query", [""])[0].casefold()
            record_filter = parse_qs(parsed.query).get("filter", ["all"])[0]
            limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
            offset = int(parse_qs(parsed.query).get("offset", ["0"])[0])
            items = [
                {**item, "type": "memory" if item.get("memory_key") else "note",
                 "label": "기억" if item.get("memory_key") else "메모", "deleteKind": "memories"}
                for item in Fixture.memories + Fixture.extra_memories
            ] + [
                {**item, "type": "artifact", "label": "저장된 결과", "deleteKind": "results"}
                for item in Fixture.results + Fixture.other_results
            ]
            counts = {kind: sum(item["type"] == kind for item in items)
                      for kind in ("note", "memory", "temporary", "artifact")}
            matches = [item for item in items if
                       (record_filter == "all" or item["type"] == record_filter or
                        (record_filter == "saved" and item["type"] in ("note", "memory"))) and
                       (not query or query in " ".join(str(item.get(key, "")) for key in
                                                       ("label", "memory_key", "content", "source_kind")).casefold())]
            page = matches[offset:offset + limit]
            if Fixture.delay_records:
                Fixture.delay_records = False
                Fixture.records_inflight = True
                time.sleep(5.0)
                Fixture.records_inflight = False
            self.send_json({"items": page, "counts": counts, "match_count": len(matches),
                            "offset": offset, "limit": limit, "has_more": offset + len(page) < len(matches)})
        elif path == "/api/workspaces/workspace-382": self.send_json({"id": "workspace-382", "title": "회귀 프로젝트", "purpose": "상세/결과 저장 회귀", "result_count": len(Fixture.results), "saved_job_ids": [item["job_id"] for item in Fixture.results], "results": Fixture.results, "messages": []})
        elif path == "/api/workspaces/workspace-other":
            detail = {"id": "workspace-other", "title": "다른 프로젝트", "purpose": "늦은 응답 격리 회귀", "result_count": len(Fixture.other_results) + 1, "saved_job_ids": [item["job_id"] for item in Fixture.other_results] + ["project-job"], "results": [dict(item) for item in Fixture.other_results], "messages": []}
            if Fixture.delay_workspace_detail:
                Fixture.delay_workspace_detail = False
                Fixture.workspace_detail_inflight = True
                time.sleep(1.5)
                Fixture.workspace_detail_inflight = False
            self.send_json(detail)
        elif path == "/control/counts": self.send_json({"test_requests": Fixture.test_requests, "apply_requests": Fixture.apply_requests, "events": len(Fixture.events), "task_polls": Fixture.task_polls})
        elif path == "/control/requests": self.send_json({"requests": Fixture.requests})
        elif path == "/control/state-inflight": self.send_json({"state_inflight": Fixture.state_inflight})
        elif path == "/control/workspace-detail-inflight": self.send_json({"workspace_detail_inflight": Fixture.workspace_detail_inflight})
        elif path == "/control/records-inflight": self.send_json({"records_inflight": Fixture.records_inflight})
        else: self.send_json({"error": path}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.observe("POST", path)
        if path == "/control/reset-observation":
            Fixture.task_polls = 0
            Fixture.requests.clear()
            self.send_json({"ok": True})
        elif path == "/control/append-event":
            Fixture.events.append({"id": len(Fixture.events) + 1, "tool": "fixture", "status": "succeeded", "created": Fixture.events[-1]["created"] + 1, "summary": "폴링으로 추가된 이벤트", "details": {}})
            self.send_json({"events": len(Fixture.events)})
        elif path == "/control/new-turn":
            Fixture.new_turns += 1
            Fixture.new_turn_times.append(time.time())
            self.send_json({"new_turns": Fixture.new_turns})
        elif path == "/control/many-tasks":
            Fixture.rich_tasks = True
            Fixture.many_tasks = True
            self.send_json({"many_tasks": True})
        elif path == "/control/rich-tasks":
            Fixture.rich_tasks = True
            self.send_json({"rich_tasks": True})
        elif path == "/control/empty-tasks":
            Fixture.tasks_empty = True
            self.send_json({"tasks_empty": True})
        elif path == "/control/delay-state":
            Fixture.delay_state = True
            self.send_json({"delay_state": True})
        elif path == "/control/add-record-pages":
            Fixture.extra_memories = [
                {"id": f"extra-memory-{index}", "content": f"extra durable note {index}",
                 "created": 1000 + index}
                for index in range(105)
            ]
            self.send_json({"extra_memories": len(Fixture.extra_memories)})
        elif path == "/control/delay-records":
            Fixture.delay_records = True
            self.send_json({"delay_records": True})
        elif path == "/control/fail-next-records":
            Fixture.fail_records_once = True
            self.send_json({"fail_records_once": True})
        elif path == "/control/set-openrouter":
            Fixture.model = {"provider": "compatible", "endpoint": "https://openrouter.ai/api/v1", "model": "fixture/connected"}
            self.send_json({"model": Fixture.model})
        elif path == "/control/delay-save":
            Fixture.delay_save = True
            self.send_json({"delay_save": True})
        elif path == "/control/delay-task-detail":
            Fixture.delay_task_detail = True
            self.send_json({"delay_task_detail": True})
        elif path == "/control/delay-workspace-detail":
            Fixture.delay_workspace_detail = True
            self.send_json({"delay_workspace_detail": True})
        elif path == "/api/model/test":
            Fixture.test_requests += 1
            time.sleep(0.8)
            self.send_json({"ok": True, "test_proof": "p" * 43})
        elif path == "/api/model":
            Fixture.apply_requests += 1
            self.send_json({"ok": True})
        elif path == "/api/openrouter/models":
            self.send_json({"models": [{"id": "fixture/free", "name": "Fixture Free"}]})
        elif path == "/api/openrouter/connect":
            Fixture.model = {"provider": "compatible", "endpoint": "https://openrouter.ai/api/v1", "model": "fixture/connected"}
            self.send_json({"connected": True})
        elif path == "/api/files/roots":
            Fixture.file_roots = list(body.get("paths", []))
            self.send_json({"roots": Fixture.file_roots})
        elif path == "/api/file-workspace":
            Fixture.file_workspace = {"references": [{"path": value} for value in body.get("references", [])], "workspace": body.get("workspace", "")}
            self.send_json(Fixture.file_workspace)
        elif path == "/api/settings/request":
            operation = body.get("operation")
            if operation == "draft":
                action = body.get("intent", "").split()[-1]
                preview = {"id": "fixture-draft", "target": "google-drive-read", "action": action, "effect": f"google-drive-read {action}", "digest": f"fixture-{action}"}
                Fixture.drafts[preview["id"]] = preview
                self.send_json({"state": "awaiting-confirmation", "preview": preview})
            elif operation == "confirm":
                preview = Fixture.drafts.pop(body.get("draft_id"), None)
                if not preview or body.get("digest") != preview["digest"]:
                    self.send_json({"error": "invalid draft"}, 409)
                else:
                    Fixture.capability_state = {"pause": "paused", "disconnect": "disconnected", "resume": "enabled"}[preview["action"]]
                    self.send_json({"state": "applied", "capability": {"id": "google-drive-read", "state": Fixture.capability_state}})
            elif operation == "cancel":
                Fixture.drafts.pop(body.get("draft_id"), None)
                self.send_json({"state": "cancelled"})
            else:
                self.send_json({"error": "unsupported settings operation"}, 400)
        elif path == "/api/workspaces/workspace-382/save-result":
            if Fixture.delay_save:
                Fixture.delay_save = False
                time.sleep(1.2)
            if any(item["job_id"] == body.get("job_id") for item in Fixture.results):
                self.send_json({"error": "이미 프로젝트에 저장된 완료 결과입니다."}, 409)
            else:
                Fixture.results[:] = [{"id": "result-1", "job_id": body.get("job_id"), "workspace_id": "workspace-382", "content": "fixture project result", "created": 3}]
                Fixture.workspace_updated["workspace-382"] += 1
                self.send_json({"id": "workspace-382", "title": "회귀 프로젝트", "purpose": "상세/결과 저장 회귀", "result_count": len(Fixture.results), "saved_job_ids": [item["job_id"] for item in Fixture.results], "results": Fixture.results, "messages": []})
        else: self.send_json({"error": path}, 404)

    def do_PUT(self):
        self.reject_observed_method("PUT")

    def do_PATCH(self):
        self.reject_observed_method("PATCH")

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/personal-space/memories/"):
            self.observe("DELETE", path)
            memory_id = path.rsplit("/", 1)[-1]
            Fixture.memories[:] = [item for item in Fixture.memories if item["id"] != memory_id]
            Fixture.extra_memories[:] = [item for item in Fixture.extra_memories if item["id"] != memory_id]
            self.send_json({"deleted": memory_id})
        elif path.startswith("/api/personal-space/results/"):
            self.observe("DELETE", path)
            result_id = path.rsplit("/", 1)[-1]
            before = len(Fixture.results)
            Fixture.results[:] = [item for item in Fixture.results if item["id"] != result_id]
            if len(Fixture.results) != before:
                Fixture.workspace_updated["workspace-382"] += 1
                self.send_json({"deleted": True, "id": result_id, "kind": "results", "workspace_id": "workspace-382"})
            else:
                before = len(Fixture.other_results)
                Fixture.other_results[:] = [item for item in Fixture.other_results if item["id"] != result_id]
                deleted = len(Fixture.other_results) != before
                if deleted: Fixture.workspace_updated["workspace-other"] += 1
                self.send_json({"deleted": deleted, "id": result_id, "kind": "results", "workspace_id": "workspace-other" if deleted else None})
        else:
            self.reject_observed_method("DELETE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18782)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fixture-only http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
