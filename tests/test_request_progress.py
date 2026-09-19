import json
import tempfile
import time
import unittest

from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


class RequestProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.service = AgentService(self.store, ModelAdapter(lambda *args, **kwargs: {}), lambda *args, **kwargs: {})

    def tearDown(self):
        self.temp.cleanup()

    def test_task_progress_is_scoped_and_redacted(self):
        first = self.store.enqueue("search project", "first")
        second = self.store.enqueue("other request", "second")
        now = time.time()
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (first,))
            db.execute("UPDATE jobs SET status='succeeded',response='done',provider='ollama',model='observed-model' WHERE id=?", (second,))
            db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)", (first, "web_search", "running", json.dumps({"query": "private search", "token": "secret-token"}), now))
            db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)", (first, "web_search", "succeeded", json.dumps({"evidence": ["source"], "url": "https://private.example"}), now + 1))
        view = self.service.task_progress(first)
        selected = view["selected"]
        self.assertEqual(selected["id"], first)
        self.assertEqual([event["job_id"] for event in selected["events"]], [first, first])
        self.assertNotIn("private search", json.dumps(selected, ensure_ascii=False))
        self.assertNotIn("secret-token", json.dumps(selected, ensure_ascii=False))
        self.assertEqual(selected["observed"]["provider"], None)
        self.assertEqual(len(view["tasks"]), 2)

    def test_status_and_restart_are_observed_without_replay(self):
        running = self.store.enqueue("long request", "running")
        failed = self.store.enqueue("failed request", "failed")
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (running,))
            db.execute("UPDATE jobs SET status='failed',error='provider failed' WHERE id=?", (failed,))
        before = self.service.task_progress()["tasks"]
        self.assertEqual(next(item for item in before if item["id"] == running)["status_kind"], "active")
        self.assertEqual(next(item for item in before if item["id"] == failed)["status_kind"], "attention")
        self.store.recover()
        after = self.service.task_progress()["selected"]
        self.assertIsNone(after)
        states = {item["id"]: item["status"] for item in self.service.task_progress()["tasks"]}
        self.assertEqual(states[running], "interrupted")

