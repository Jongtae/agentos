"""A read-only fake holdings API for API-READ-01 (#1216): tests only, never shipped.

It answers ``GET /v1/holdings`` with holdings (quantity, average price,
market value), cash, totals and the time the data is as of, for one account
bound to one key.  ``POST /v1/orders`` exists only so tests can prove an
order is refused without approval and never sent twice; nothing is executed.

Fault injections (``FakeHoldingsApi.fault``):

* ``no_auth``       - every request is answered 401;
* ``other_account`` - the response belongs to another account;
* ``stale``         - the data is three days old;
* ``partial``       - one holding has no market value and a next page is pending;
* ``mismatch``      - the reported total differs from the sum of the holdings;
* ``timeout_once``  - the first request times out, the next one answers.

Run it for an owner observation (loopback only, a fresh fake key each start):

    PYTHONPATH=src python3 tests/fake_holdings_api.py --data ~/.local/share/agentos

registers the slot ``fake-holdings`` in that owner store and serves until
Ctrl-C; ``--remove`` deletes the slot again.
"""
import argparse
import copy
import json
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ACCOUNT = 'ACC-1001'
OTHER_ACCOUNT = 'ACC-2002'
HOLDINGS_PATH = '/v1/holdings'
ORDERS_PATH = '/v1/orders'
SLOT = 'fake-holdings'
FAULTS = ('no_auth', 'other_account', 'stale', 'partial', 'mismatch', 'timeout_once')


def fake_key():
    """A fresh fake credential built at run time, so no literal looks like a secret (#1206)."""
    return 'fk_' + secrets.token_hex(16)


def holdings(as_of, *, price_shift=0):
    rows = [
        {'symbol': 'AAA', 'name': 'Alpha', 'quantity': 12, 'average_price': 41250.5, 'market_value': 520800.1},
        {'symbol': 'BBB', 'name': 'Beta', 'quantity': 3, 'average_price': 188000, 'market_value': 571500 + price_shift},
        {'symbol': 'CCC', 'name': 'Gamma', 'quantity': 0.5, 'average_price': 0.1, 'market_value': 0.2},
    ]
    market = sum((round(row['market_value'] * 10) for row in rows)) / 10
    cash = 1250340
    return {'account_id': ACCOUNT, 'currency': 'KRW', 'as_of': as_of.isoformat(), 'holdings': rows,
            'cash': cash, 'total_market_value': market, 'total_value': market + cash}


class FakeHoldingsApi:
    """The fake API as an ``api_requests`` transport; ``calls`` records what reached it."""

    def __init__(self, key, *, now, fault=None, host='broker.fake.test'):
        self.key, self.now, self.fault, self.host = key, now, fault, host
        self.price_shift = 0
        self.calls = []
        self.orders = []

    def data(self):
        as_of = datetime.fromtimestamp(self.now(), timezone.utc) - timedelta(seconds=60)
        if self.fault == 'stale':
            as_of -= timedelta(days=3)
        body = holdings(as_of, price_shift=self.price_shift)
        if self.fault == 'other_account':
            body['account_id'] = OTHER_ACCOUNT
        if self.fault == 'partial':
            del body['holdings'][1]['market_value']
            body['next_page'] = 'cursor-2'
        if self.fault == 'mismatch':
            body['total_market_value'] += 1000
        return body

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({'method': method, 'url': url, 'headers': dict(headers), 'body': body})
        if self.fault == 'timeout_once' and len(self.calls) == 1:
            raise TimeoutError('fake timeout')
        if self.fault == 'no_auth' or headers.get('Authorization') != f'Bearer {self.key}':
            return 401, {'content-type': 'application/json'}, b'{"error":"unauthorized"}'
        path = urlsplit(url).path
        if method == 'GET' and path == HOLDINGS_PATH:
            return 200, {'content-type': 'application/json'}, json.dumps(self.data()).encode()
        if method == 'POST' and path == ORDERS_PATH:
            self.orders.append({'body': body, 'idempotency_key': headers.get('Idempotency-Key')})
            return 201, {'content-type': 'application/json'}, b'{"accepted":true}'
        return 404, {'content-type': 'application/json'}, b'{"error":"not found"}'

    def raw(self):
        """What the API returns now, for comparing with what AgentOS handed on."""
        return copy.deepcopy(self.data())


def serve(api, port):
    class Handler(BaseHTTPRequestHandler):
        def _answer(self, method):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            try:
                status, headers, data = api(method, f'http://127.0.0.1:{self.server.server_address[1]}{self.path}',
                                            dict(self.headers), body, 15)
            except TimeoutError:
                return
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._answer('GET')

        def do_POST(self):
            self._answer('POST')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    import time
    from personal_agent.api_requests import remove_slot, save_slot
    from personal_agent.quickstart_store import QuickStore
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--data', required=True)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--fault', choices=FAULTS, default=None)
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    store = QuickStore(args.data)
    if args.remove:
        print('removed' if remove_slot(store, SLOT) else 'no slot')
        return
    key = fake_key()
    save_slot(store, SLOT, [f'127.0.0.1:{args.port}'], key, subject_field='$.account_id', subject_value=ACCOUNT)
    api = FakeHoldingsApi(key, now=time.time, fault=args.fault)
    server = serve(api, args.port)
    print(f'slot {SLOT} -> http://127.0.0.1:{args.port}{HOLDINGS_PATH} (fault: {args.fault or "none"}); Ctrl-C to stop')
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == '__main__':
    sys.exit(main())
