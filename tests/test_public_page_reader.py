import gzip
import http.client
import io
import unittest
from unittest.mock import patch

from personal_agent.local_tools import PublicPageReader, normalize_public_url


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

    def test_rejects_literal_private_link_local_and_metadata_hosts_without_request(self):
        opener=Opener(Response())
        for url in ('http://127.0.0.1/admin','http://10.0.0.8/','http://[::1]/',
                    'http://169.254.169.254/latest/meta-data/','https://metadata.google.internal/'):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, '개인 네트워크|메타데이터'):
                PublicPageReader(opener=opener,resolver=public_dns).read(url)
        self.assertEqual(opener.requests,[])

    def test_request_is_anonymous_and_does_not_run_page_javascript(self):
        opener=Opener(Response(b'<html><button>Buy</button><script>fetch("/checkout")</script></html>'))
        result=PublicPageReader(opener=opener,resolver=public_dns).read('https://example.com/item')
        headers=dict(opener.requests[0][0].header_items())
        self.assertNotIn('Cookie',headers);self.assertNotIn('Authorization',headers)
        self.assertNotIn('checkout',result['content'])
        self.assertIn('no cookies, login, JavaScript or mutation',result['scope'])

    def test_validates_redirect_target_before_request(self):
        opener=Opener(Response(status=302, headers={'Location':'http://169.254.169.254/latest'}))
        def redirect_dns(host, port, type=None):
            if host == '169.254.169.254': return [(None,None,None,None,('169.254.169.254', port))]
            return public_dns(host, port, type)
        with self.assertRaisesRegex(ValueError, '개인 네트워크'):
            PublicPageReader(opener=opener, resolver=redirect_dns).read('https://example.com/')
        self.assertEqual(len(opener.requests), 1)

    def test_owner_scope_binds_initial_url_and_redirects(self):
        opener=Opener(Response())
        reader=PublicPageReader(opener=opener, resolver=public_dns)
        with self.assertRaisesRegex(ValueError, '승인한 공개 페이지 범위'):
            reader.read('https://example.com/event', approved_urls=['https://example.com/other'])
        self.assertEqual(normalize_public_url('HTTPS://Example.com/event?b=2&a=1#frag'), 'https://example.com/event?a=1&b=2')

    def test_owner_scope_rejects_public_redirect_collector(self):
        opener=Opener(Response(status=302, headers={'Location':'https://collector.example/collect?x=1'}))
        reader=PublicPageReader(opener=opener, resolver=public_dns)
        with self.assertRaisesRegex(ValueError, '승인한 공개 페이지 범위'):
            reader.read('https://example.com/event', approved_urls=['https://example.com/event'])

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
