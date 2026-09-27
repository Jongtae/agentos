"""A stand-in for ``personal_agent.browser_worker`` that speaks the same JSON-lines protocol.

Used by ``tests/test_browser_webkit.py`` to exercise ``WebKitWorkerDriver``'s
process boundary (timeouts, crash restart, seed import, typed target errors)
on any platform.  ``argv[1]`` is a log file: every received command is
appended as one JSON line.  The URL of a ``navigate`` selects a behaviour:
``/crash`` exits, ``/hang`` never answers, ``/slow`` answers ``timeout``,
``/blocked`` answers ``blocked_destination``.
"""
import json
import os
import sys
import time

LOG = sys.argv[1]
cookies = []
page = {'url': 'about:blank'}


def emit(message):
    sys.stdout.write(json.dumps(message) + '\n')
    sys.stdout.flush()


def log(command):
    with open(LOG, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(command) + '\n')


if os.environ.get('AGENTOS_FAKE_WORKER_MODE') == 'unavailable':
    emit({'event': 'unavailable', 'error': 'webkit_failed'})
    sys.exit(2)
sys.stderr.write('library noise that must never reach a log\n')
emit({'event': 'ready', 'pid': os.getpid()})
for line in sys.stdin:
    command = json.loads(line)
    log(command)
    ident, op = command.get('id'), command.get('op')
    if op == 'navigate':
        url = command['url']
        if '/crash' in url:
            os._exit(3)
        if '/hang' in url:
            time.sleep(60)
            continue
        if '/blocked' in url:
            emit({'id': ident, 'ok': False, 'error': 'blocked_destination'})
            continue
        if '/slow' in url:
            emit({'id': ident, 'ok': False, 'error': 'timeout'})
            continue
        page['url'] = url
        emit({'id': ident, 'ok': True, 'url': url})
    elif op == 'snapshot':
        emit({'id': ident, 'ok': True, 'page': {'url': page['url'], 'title': 't', 'forms': [],
                                                 'text': 'landed page' if page['url'].endswith(('/landed', '/opened')) else 'x',
                                                 'elements': [{'index': 3, 'role': 'button', 'name': 'Go', 'tag': 'button',
                                                               'type': 'submit', 'autocomplete': '', 'form': None,
                                                               'href': None, 'value': None, 'disabled': False},
                                                              {'index': 7, 'role': 'button', 'name': 'Pay', 'tag': 'button',
                                                               'type': 'submit', 'autocomplete': '', 'form': 1,
                                                               'href': None, 'value': None, 'disabled': False},
                                                              {'index': 8, 'role': 'textbox', 'name': 'Card', 'tag': 'input',
                                                               'type': 'text', 'autocomplete': 'billing cc-number', 'form': 1,
                                                               'href': None, 'value': None, 'disabled': False},
                                                              {'index': 9, 'role': 'button', 'name': 'Quick', 'tag': 'span',
                                                               'type': '', 'autocomplete': '', 'form': None, 'label_form': 1,
                                                               'href': None, 'value': None, 'disabled': False}]}})
    elif op == 'click':
        # #736, as the real worker's settle_click: a click that starts a navigation a
        # moment later (a script timer) or asks for a new window (loaded into this
        # view) answers only once that navigation has landed, with navigated=true.
        # ``/lateresolve``: the navigation's destination check (DNS) takes longer than the
        # click grace; the real worker waits while that policy decision is pending.
        if command.get('index') == 3 and page['url'].endswith(('/delayed', '/popup', '/lateresolve')):
            time.sleep(1.5 if page['url'].endswith('/lateresolve') else 0.2)
            page['url'] = page['url'].rsplit('/', 1)[0] + ('/opened' if page['url'].endswith('/popup') else '/landed')
            emit({'id': ident, 'ok': True, 'navigated': True})
        elif command.get('index') == 7:
            emit({'id': ident, 'ok': False, 'error': 'target_obscured'})
        elif command.get('index') == 9 and command.get('approved') is not True:
            # As the real worker: the press submitted the payment form, which was cancelled (#698).
            emit({'id': ident, 'ok': False, 'error': 'approval_required',
                  'form': {'dom': 0, 'method': 'post', 'action': 'https://shop.test/pay'}})
        else:
            emit({'id': ident, 'ok': True})
    elif op == 'type':
        emit({'id': ident, 'ok': True})
    elif op == 'show':
        if 'closefirst' in str(command.get('url')):
            emit({'event': 'hidden'})
            time.sleep(0.1)
        emit({'id': ident, 'ok': True})
        if 'autoclose' in str(command.get('url')):
            time.sleep(0.2)
            emit({'event': 'hidden'})
    elif op == 'settle':
        emit({'id': ident, 'ok': True, 'settled': True, 'waited': 0})
    elif op == 'cookies_import':
        cookies.extend(command.get('cookies') or [])
        emit({'id': ident, 'ok': True, 'imported': len(command.get('cookies') or [])})
    elif op == 'cookies_export':
        grouped = {}
        for row in cookies:
            grouped.setdefault(row['domain'].lstrip('.'), []).append(row)
        emit({'id': ident, 'ok': True, 'sites': grouped, 'hosts': []})
    elif op == 'cookies_delete':
        before = len(cookies)
        cookies[:] = [row for row in cookies if row['domain'].lstrip('.') != command.get('site')]
        emit({'id': ident, 'ok': True, 'deleted': before - len(cookies)})
    elif op == 'cookies_clear':
        cookies.clear()
        emit({'id': ident, 'ok': True})
    elif op == 'quit':
        emit({'id': ident, 'ok': True})
        break
    else:
        emit({'id': ident, 'ok': False, 'error': 'unknown_op'})
