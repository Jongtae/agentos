"""Retired Kubernetes owner-runtime cluster (REUSE-R8 / #435).

The runtime and provisioning CLI were relocated out of the product package to
scripts/legacy/kubernetes/ because nothing in the shipped runtime imports them
and no Dockerfile builds the `personal-agent:dev` image the CLI targets. The
behaviour is preserved and still exercised here, loaded by path the same way the
repository already tests other scripts/ modules.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

LEGACY = Path(__file__).resolve().parents[1] / "scripts" / "legacy" / "kubernetes"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"legacy_kubernetes_{name}", LEGACY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_runtime, _cli = _load("runtime"), _load("cli")
Store, handler, manifests = _runtime.Store, _runtime.handler, _cli.manifests


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_memory_survives_new_runtime(self):
        self.store.enqueue({'action': 'remember', 'key': 'name', 'value': 'Alice'})
        self.store.tick()
        recovered = Store(self.temp.name)
        recovered.enqueue({'action': 'recall', 'key': 'name'})
        recovered.tick()
        self.assertEqual(json.loads(recovered.tasks()[0]['result']), {'value': 'Alice'})

    def test_idempotency_and_conflicting_reuse(self):
        body = {'action': 'remember', 'key': 'x', 'value': '1', 'request_key': 'once'}
        self.assertEqual(self.store.enqueue(body)['id'], self.store.enqueue(body)['id'])
        with self.assertRaises(ValueError):
            self.store.enqueue(dict(body, value='2'))
        self.assertEqual(len(self.store.tasks()), 1)

    def test_scheduled_work_waits_and_survives_reopen(self):
        self.store.enqueue({'action': 'list_files', 'delay_seconds': 60})
        Store(self.temp.name).tick()
        self.assertEqual(self.store.tasks()[0]['status'], 'queued')
        with self.store.connect() as db:
            db.execute('UPDATE tasks SET due=0')
        Store(self.temp.name).tick()
        self.assertEqual(self.store.tasks()[0]['status'], 'succeeded')

    def test_concurrent_ticks_do_not_duplicate(self):
        self.store.enqueue({'action': 'remember', 'key': 'x', 'value': '1'})
        threads = [threading.Thread(target=self.store.tick) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(self.store.tasks()), 1)
        self.assertEqual(self.store.tasks()[0]['status'], 'succeeded')

    def test_separate_stores(self):
        self.store.enqueue({'action': 'remember', 'key': 'private', 'value': 'Alice'})
        self.store.tick()
        with tempfile.TemporaryDirectory() as other:
            bob = Store(other)
            bob.enqueue({'action': 'recall', 'key': 'private'})
            bob.tick()
            self.assertIsNone(json.loads(bob.tasks()[0]['result'])['value'])

    def test_reject_invalid_tools_and_delays(self):
        for body in ([], {'action': 'shell'}, {'action': 'remember'}, {'action': 'list_files', 'delay_seconds': float('nan')}, {'action': 'list_files', 'delay_seconds': True}):
            with self.assertRaises(ValueError): self.store.enqueue(body)

    def test_http_rejects_other_identity(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.store, 'a'*32, 'alice'))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = 'http://127.0.0.1:' + str(server.server_port) + '/v1/me'
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Bearer '+'b'*32}))
            self.assertEqual(error.exception.code, 401)
            with urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Bearer '+'a'*32})) as response:
                self.assertEqual(json.load(response)['owner'], 'alice')
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_invalid_namespace_rejected(self):
        for owner in ('../bob', 'alice/bob', 'ALICE', '', 'a-', '-a'):
            with self.assertRaises(ValueError): manifests(owner, 'test', 'x')


if __name__ == '__main__':
    unittest.main()
