import gzip
import http.client
import io
import unittest
from unittest.mock import patch

from personal_agent.local_tools import PublicPageReader


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class Response:
    def __init__(self, body=b'<html><script>ignore()</script><p>Price: 120 USD</p></html>', status=200, headers=None):
        self.body=io.BytesIO(body); self.status=status; self.headers=Headers(headers or {'Content-Type':'text/html'})
    def read(self, size=-1): return self.body.read(size)


class Opener:
    def __init__(self, response): self.response=response; self.requests=[]
    def open(self, request, timeout=None): self.requests.append((request,timeout)); return self.response


def public_dns(host, port, type=None):
    return [(None,None,None,None,('93.184.216.34', port))]


class PublicPageReaderTests(unittest.TestCase):
    def test_reads_text_and_treats_script_as_data_boundary(self):
        opener=Opener(Response())
        result=PublicPageReader(opener=opener, resolver=public_dns).read('https://example.com/event#section')
        self.assertIn('Price: 120 USD', result['content'])
        self.assertNotIn('ignore()', result['content'])
        self.assertEqual(result['url'], 'https://example.com/event')
        self.assertEqual(opener.requests[0][0].get_header('User-agent'), 'AgentOS public-page-reader/1.0')

    def test_rejects_url_credentials_and_private_dns(self):
        with self.assertRaises(ValueError): PublicPageReader(resolver=public_dns).read('https://user:pass@example.com/')
        def private_dns(host, port, type=None): return [(None,None,None,None,('127.0.0.1', port))]
        with self.assertRaisesRegex(ValueError, '개인 네트워크'):
            PublicPageReader(opener=Opener(Response()), resolver=private_dns).read('https://example.com/')

    def test_validates_redirect_target_before_request(self):
        opener=Opener(Response(status=302, headers={'Location':'http://169.254.169.254/latest'}))
        def redirect_dns(host, port, type=None):
            if host == '169.254.169.254': return [(None,None,None,None,('169.254.169.254', port))]
            return public_dns(host, port, type)
        with self.assertRaisesRegex(ValueError, '개인 네트워크'):
            PublicPageReader(opener=opener, resolver=redirect_dns).read('https://example.com/')
        self.assertEqual(len(opener.requests), 1)

    def test_rejects_oversize_and_non_text(self):
        with self.assertRaisesRegex(ValueError, '응답 크기'):
            PublicPageReader(opener=Opener(Response(b'a'*(1_000_001))), resolver=public_dns).read('https://example.com/')
        with self.assertRaisesRegex(ValueError, 'HTML 또는 텍스트'):
            PublicPageReader(opener=Opener(Response(b'pdf', headers={'Content-Type':'application/pdf'})), resolver=public_dns).read('https://example.com/')

    def test_bounds_decompressed_content(self):
        body=gzip.compress(b'x'*2_000_001)
        with self.assertRaisesRegex(ValueError, '압축 해제'):
            PublicPageReader(opener=Opener(Response(body, headers={'Content-Type':'text/plain','Content-Encoding':'gzip'})), resolver=public_dns).read('https://example.com/')

    def test_malformed_http_is_a_recoverable_provider_failure(self):
        class Broken:
            def open(self, request, timeout=None): raise http.client.BadStatusLine('broken')
        with self.assertRaisesRegex(Exception, '공개 페이지를 가져오지 못했습니다'):
            PublicPageReader(opener=Broken(), resolver=public_dns).read('https://example.com/')


if __name__ == '__main__': unittest.main()
