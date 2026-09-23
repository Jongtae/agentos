"""Local kind acceptance. Creates two unique test environments and leaves them for inspection."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[3]
KUBE = str(ROOT / '.tools/kubeconfig')
BASE = ['kubectl', '--kubeconfig', KUBE]


def kube(*args):
    return subprocess.check_output(BASE + list(args), text=True).strip()


def cli(action, owner):
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / 'cli.py'), '--kubeconfig', KUBE, action, owner], cwd=ROOT, check=True)


def credential(owner):
    raw = kube('-n', 'agent-'+owner, 'get', 'secret', 'identity', '-o', 'json')
    return base64.b64decode(json.loads(raw)['data']['token']).decode()


@contextmanager
def connection(owner):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(BASE + ['-n', 'agent-'+owner, 'port-forward', 'service/runtime', f'{port}:8080', '--address=127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url+'/healthz', timeout=1): break
            except (OSError, urllib.error.URLError): time.sleep(.1)
        else: raise RuntimeError('port-forward did not become ready')
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


def request(url, token, path='/v1/tasks', body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url+path, data=raw, headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def completed(url, token, task_id):
    for _ in range(100):
        task = next(t for t in request(url, token)['tasks'] if t['id'] == task_id)
        if task['status'] == 'succeeded': return json.loads(task['result'])
        time.sleep(.1)
    raise AssertionError('task did not complete')


def main():
    suffix = uuid.uuid4().hex[:6]
    alice, bob = 'alice-'+suffix, 'bob-'+suffix
    for owner in (alice, bob): cli('create', owner)
    at, bt = credential(alice), credential(bob)
    with connection(alice) as a, connection(bob) as b:
        assert request(a, at, '/v1/me')['owner'] == alice
        try:
            request(a, bt, '/v1/me')
            raise AssertionError('other user credential accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 401
        task = request(a, at, body={'action': 'remember', 'key': 'private', 'value': 'alice-only', 'request_key': 'once'})
        completed(a, at, task['id'])
        assert request(a, at, body={'action': 'remember', 'key': 'private', 'value': 'alice-only', 'request_key': 'once'})['id'] == task['id']
        task = request(b, bt, body={'action': 'recall', 'key': 'private'})
        assert completed(b, bt, task['id']) == {'value': None}
        scheduled = request(a, at, body={'action': 'remember', 'key': 'background', 'value': 'done', 'delay_seconds': 2})
    # No API connections remain while scheduled work runs.
    time.sleep(3)
    with connection(alice) as a:
        assert completed(a, at, scheduled['id']) == {'saved': 'background'}
        pending = request(a, at, body={'action': 'remember', 'key': 'after-resume', 'value': 'done', 'delay_seconds': 5})
    cli('pause', alice)
    kube('-n', 'agent-'+alice, 'wait', '--for=delete', 'pod', '-l', 'app=personal-agent', '--timeout=60s')
    time.sleep(6)
    cli('resume', alice)
    with connection(alice) as a:
        assert completed(a, at, pending['id']) == {'saved': 'after-resume'}
        task = request(a, at, body={'action': 'recall', 'key': 'private'})
        assert completed(a, at, task['id']) == {'value': 'alice-only'}
    # Workspace file is on the PVC, and must also survive Pod replacement.
    kube('-n', 'agent-'+alice, 'exec', 'deployment/runtime', '--', 'python', '-c', "from pathlib import Path; Path('/data/workspace/proof.txt').write_text('persistent')")
    kube('-n', 'agent-'+alice, 'rollout', 'restart', 'deployment/runtime')
    kube('-n', 'agent-'+alice, 'rollout', 'status', 'deployment/runtime', '--timeout=120s')
    with connection(alice) as a, connection(bob) as b:
        task = request(a, at, body={'action': 'list_files'})
        assert completed(a, at, task['id']) == {'files': ['proof.txt']}
        task = request(b, bt, body={'action': 'list_files'})
        assert completed(b, bt, task['id']) == {'files': []}
    pvcs = [json.loads(kube('-n', 'agent-'+o, 'get', 'pvc', 'data', '-o', 'json'))['spec']['volumeName'] for o in (alice, bob)]
    assert pvcs[0] != pvcs[1]
    report = {'result': 'passed', 'owners': [alice, bob], 'checks': ['identity', 'wrong-token-rejected', 'separate-memory', 'idempotent-request', 'disconnected-schedule', 'pause-resume-overdue-task', 'memory-survives-pod', 'files-survive-pod', 'separate-pvcs'], 'network_policy_enforcement': 'not_verified', 'llm': 'not_connected'}
    (ROOT / 'E2E_RESULT.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
