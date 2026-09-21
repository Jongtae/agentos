import gzip
import http.client
import io
import ipaddress
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import build_opener

from personal_agent.local_tools import PublicPageReader, _denied_address, normalize_public_url
from personal_agent.providers import ProviderError


def system_resolver(host, port, type=None, timeout=None):
    """Resolve through the real platform parser without the subprocess wrapper."""
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


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


def public_dns(host, port, type=None, timeout=None):
    return [(None,None,None,None,('93.184.216.34', port))]


class PublicPageReaderTests(unittest.TestCase):
    def test_reads_text_and_treats_script_as_data_boundary(self):
        opener=Opener(Response())
        result=PublicPageReader(opener=opener, resolver=public_dns).read('https://example.com/event#section')
        self.assertIn('Price: 120 USD', result['content'])
        self.assertNotIn('ignore()', result['content'])
        self.assertEqual(result['url'], 'https://example.com/event')
        self.assertEqual(opener.requests[0][0].get_header('User-agent'), 'AgentOS public-page-reader/1.0')

    def test_plain_text_preserves_literal_angle_bracket_qualifiers(self):
        body=b'Grand total: USD 100 <before taxes>.'
        result=PublicPageReader(
            opener=Opener(Response(body,headers={'Content-Type':'text/plain'})),
            resolver=public_dns,
        ).read('https://example.com/total')
        self.assertEqual(result['content'],'Grand total: USD 100 <before taxes>.')

    def test_rejects_url_credentials_and_private_dns(self):
        with self.assertRaises(ValueError): PublicPageReader(resolver=public_dns).read('https://user:pass@example.com/')
        def private_dns(host, port, type=None, timeout=None): return [(None,None,None,None,('127.0.0.1', port))]
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

    def test_page_content_truncation_keeps_only_complete_sentences(self):
        body=('<p>'+('A'*23970)+'.</p><p>Grand total USD 100 before taxes and fees.</p>').encode()
        result=PublicPageReader(opener=Opener(Response(body)),resolver=public_dns).read('https://example.com/long')
        self.assertTrue(result['content_truncated'])
        self.assertTrue(result['content'].endswith('.'))
        self.assertNotIn('Grand total USD 1',result['content'])

    def test_punctuationless_page_truncation_keeps_complete_tokens(self):
        body=('<div>'+('catalog-item '*3000)+'</div>').encode()
        result=PublicPageReader(opener=Opener(Response(body)),resolver=public_dns).read('https://example.com/catalog')
        self.assertTrue(result['content_truncated'])
        self.assertTrue(result['content'])
        self.assertLessEqual(len(result['content']),24000)
        self.assertTrue(result['content'].endswith('catalog-item'))

    def test_cjk_page_truncation_keeps_complete_unicode_sentences(self):
        sentence='公開情報です。'
        body=('<div>'+sentence*5000+'</div>').encode()
        result=PublicPageReader(opener=Opener(Response(body)),resolver=public_dns).read('https://example.com/catalog')
        self.assertTrue(result['content_truncated'])
        self.assertTrue(result['content'])
        self.assertLessEqual(len(result['content']),24000)
        self.assertTrue(result['content'].endswith('。'))

    def test_validates_redirect_target_before_request(self):
        opener=Opener(Response(status=302, headers={'Location':'http://169.254.169.254/latest'}))
        def redirect_dns(host, port, type=None, timeout=None):
            if host == '169.254.169.254': return [(None,None,None,None,('169.254.169.254', port))]
            return public_dns(host, port, type, timeout)
        with self.assertRaisesRegex(ValueError, '개인 네트워크'):
            PublicPageReader(opener=opener, resolver=redirect_dns).read('https://example.com/')
        self.assertEqual(len(opener.requests), 1)

    def test_owner_scope_binds_initial_url_and_redirects(self):
        opener=Opener(Response())
        reader=PublicPageReader(opener=opener, resolver=public_dns)
        with self.assertRaisesRegex(ValueError, '승인한 공개 페이지 범위'):
            reader.read('https://example.com/event', approved_urls=['https://example.com/other'])
        self.assertEqual(normalize_public_url('HTTPS://Example.com/event?b=2&a=1#frag'), 'https://example.com/event?a=1&b=2')

    def test_normalization_preserves_scheme_mismatched_explicit_ports_and_scope(self):
        self.assertEqual(normalize_public_url('http://example.com:443/path'),'http://example.com:443/path')
        self.assertEqual(normalize_public_url('https://example.com:80/path'),'https://example.com:80/path')
        self.assertEqual(normalize_public_url('http://example.com:80/path'),'http://example.com/path')
        self.assertEqual(normalize_public_url('https://example.com:443/path'),'https://example.com/path')
        opener=Opener(Response())
        reader=PublicPageReader(opener=opener,resolver=public_dns)
        with self.assertRaisesRegex(ValueError,'승인한 공개 페이지 범위'):
            reader.read('http://example.com:443/path',approved_urls=['http://example.com/path'])
        self.assertEqual(opener.requests,[])
        reader.read('https://example.com:80/path',approved_urls=['https://example.com:80/path'])
        self.assertEqual(opener.requests[0][0].full_url,'https://example.com:80/path')

    def test_host_header_preserves_scheme_specific_authority_and_ipv6_brackets(self):
        authority=PublicPageReader._host_header
        self.assertEqual(authority(urlsplit('http://example.com:443/path')),'example.com:443')
        self.assertEqual(authority(urlsplit('https://example.com:80/path')),'example.com:80')
        self.assertEqual(authority(urlsplit('http://example.com:80/path')),'example.com')
        self.assertEqual(authority(urlsplit('https://example.com:443/path')),'example.com')
        self.assertEqual(authority(urlsplit('https://[2606:2800:220:1:248:1893:25c8:1946]:80/path')),
                         '[2606:2800:220:1:248:1893:25c8:1946]:80')

    def test_rejects_port_zero_for_hostname_ipv4_and_bracketed_ipv6_before_resolution(self):
        resolutions=[]
        def resolver(host,port,type=None,timeout=None):
            resolutions.append((host,port));return public_dns(host,port,type,timeout)
        opener=Opener(Response())
        reader=PublicPageReader(opener=opener,resolver=resolver)
        for url in ('http://example.com:0/path','https://93.184.216.34:0/path',
                    'https://[2606:2800:220:1:248:1893:25c8:1946]:0/path'):
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'포트'):
                reader.read(url,approved_urls=[url])
            with self.subTest(host=url),self.assertRaisesRegex(ValueError,'포트'):
                PublicPageReader._host_header(urlsplit(url))
            with self.subTest(resolve=url),self.assertRaisesRegex(ValueError,'포트'):
                reader._validate_host(url)
            with self.subTest(connect=url),self.assertRaisesRegex(ValueError,'포트'):
                reader._open_pinned(url,{'93.184.216.34'})
        self.assertEqual(resolutions,[]);self.assertEqual(opener.requests,[])

    def test_rejects_empty_or_out_of_range_explicit_ports(self):
        for url in ('http://example.com:/path','https://example.com:65536/path',
                    'https://[2606:2800:220:1:248:1893:25c8:1946]:/path'):
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'포트'):
                normalize_public_url(url)

    @patch('personal_agent.local_tools.socket.create_connection')
    def test_multiple_addresses_share_one_monotonic_deadline(self,create_connection):
        now=[0.0];timeouts=[]
        def fail(_address,timeout):
            timeouts.append(timeout);now[0]+=7;raise OSError('unreachable')
        create_connection.side_effect=fail
        reader=PublicPageReader(clock=lambda:now[0])
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            reader._open_pinned('http://example.com/', ['93.184.216.1','93.184.216.2','93.184.216.3'],deadline=12)
        self.assertEqual(timeouts,[12.0,5.0])

    @patch('personal_agent.local_tools.http.client.HTTPSConnection')
    @patch('personal_agent.local_tools.socket.create_connection')
    def test_connect_tls_request_and_headers_consume_one_deadline(self,create_connection,https_connection):
        now=[0.0];socket_timeouts=[];connect_timeouts=[]
        class Sock:
            def settimeout(self,value): socket_timeouts.append(value)
            def close(self): pass
        sock=Sock()
        class Context:
            def wrap_socket(self,raw,server_hostname=None): now[0]+=4;return raw
        class Connection:
            def __init__(self): self._context=Context();self.sock=None;self.initial_timeout=None
            def request(self,*args,**kwargs): now[0]+=2
            def getresponse(self): now[0]+=2;return Response()
            def close(self): pass
        connection=Connection()
        def construct(*args,**kwargs): connection.initial_timeout=kwargs['timeout'];return connection
        https_connection.side_effect=construct
        def connect(_address,timeout): connect_timeouts.append(timeout);now[0]+=3;return sock
        create_connection.side_effect=connect
        reader=PublicPageReader(clock=lambda:now[0])
        reader._open_pinned('https://example.com/',['93.184.216.34'],deadline=12)
        self.assertEqual(connection.initial_timeout,12.0)
        self.assertEqual(connect_timeouts,[12.0])
        self.assertEqual(socket_timeouts,[9.0,5.0,3.0])
        self.assertEqual(now[0],11.0)

    def test_dns_and_response_phases_share_one_absolute_deadline(self):
        now=[0.0];resolution_timeouts=[];open_timeouts=[]
        def resolver(host,port,type=None,timeout=None):
            resolution_timeouts.append(timeout);now[0]+=4
            return public_dns(host,port,type,timeout)
        class SlowOpener:
            def open(self,request,timeout=None):
                open_timeouts.append(timeout);now[0]+=9
                return Response()
        reader=PublicPageReader(opener=SlowOpener(),resolver=resolver,clock=lambda:now[0])
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            reader.read('https://example.com/')
        self.assertEqual(resolution_timeouts,[12.0])
        self.assertEqual(open_timeouts,[8.0])

    def test_dns_exhaustion_stops_before_transport(self):
        now=[0.0];opened=[]
        def resolver(host,port,type=None,timeout=None):
            self.assertEqual(timeout,12.0);now[0]=12.0
            return public_dns(host,port,type,timeout)
        class NeverOpen:
            def open(self,request,timeout=None): opened.append(request);return Response()
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            PublicPageReader(opener=NeverOpen(),resolver=resolver,clock=lambda:now[0]).read('https://example.com/')
        self.assertEqual(opened,[])

    def test_body_reads_receive_decreasing_deadline_and_cannot_overrun(self):
        now=[0.0]
        class SlowResponse(Response):
            def read(self,size=-1):
                now[0]+=7
                return b'chunk' if now[0] < 14 else b''
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            PublicPageReader(opener=Opener(SlowResponse()),resolver=public_dns,clock=lambda:now[0]).read('https://example.com/')

    @patch('personal_agent.local_tools.MAX_PAGE_SECONDS',0.05)
    def test_body_watchdog_shuts_down_socket_to_interrupt_blocking_read(self):
        released=threading.Event();shutdowns=[]
        class Sock:
            def settimeout(self,_value): pass
            def shutdown(self,how): shutdowns.append(how);released.set()
            def close(self): released.set()
        class Connection:
            sock=Sock()
        class BlockingResponse(Response):
            _agentos_connection=Connection()
            def read(self,size=-1):
                released.wait(1)
                return b''
        started=time.monotonic()
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            PublicPageReader(opener=Opener(BlockingResponse()),resolver=public_dns).read('https://example.com/')
        self.assertLess(time.monotonic()-started,0.5)
        self.assertEqual(shutdowns,[socket.SHUT_RDWR])

    @patch('personal_agent.local_tools.MAX_PAGE_SECONDS',0.1)
    def test_drip_fed_redirect_body_cannot_outlive_the_page_deadline(self):
        """A redirect drain bounded only in bytes made MAX_PAGE_SECONDS unenforceable.

        `_set_response_deadline` arms a per-``recv`` socket timeout, and that
        timeout restarts on every byte, so a server that drips one byte before
        each expiry stretches the discarded redirect body without limit. The
        drain is 64 KB, which is ~65k drip intervals per hop across up to four
        hops. Only the deadline guard, which closes the socket from a timer
        thread, bounds this in wall-clock time.
        """
        class DripSock:
            def __init__(self,stop): self.stop=stop
            def settimeout(self,_value): pass
            def shutdown(self,_how): self.stop.set()
            def close(self): self.stop.set()
        class DripConnection:
            def __init__(self,stop): self.sock=DripSock(stop)
            def close(self): self.sock.stop.set()
        class DripRedirect(Response):
            def __init__(self):
                super().__init__(b'',status=302,headers={
                    'Content-Type':'text/html','Location':'https://example.com/next'})
                self.stop=threading.Event(); self._agentos_connection=DripConnection(self.stop)
                self.drained=0
            def read(self,size=-1):
                body=bytearray()
                while not self.stop.wait(0.005):
                    body.extend(b'x')          # one byte per per-recv interval
                    self.drained+=1
                return bytes(body)
        response=DripRedirect()
        started=time.monotonic()
        with self.assertRaises(Exception):
            PublicPageReader(opener=Opener(response),resolver=public_dns).read('https://example.com/')
        elapsed=time.monotonic()-started
        self.assertTrue(response.stop.is_set(),'the deadline guard never closed the drained socket')
        self.assertLess(elapsed,1.0,f'drain ran {elapsed:.3f}s against a 0.1s page budget')
        self.assertLess(response.drained,64*1024)

    def test_honors_safe_declared_charset_without_corrupting_exact_price(self):
        body='<html><p>Price: £100.</p></html>'.encode('iso-8859-1')
        result=PublicPageReader(opener=Opener(Response(
            body,headers={'Content-Type':'text/html; charset=iso-8859-1'})),resolver=public_dns).read('https://example.com/')
        self.assertIn('£100',result['content'])
        self.assertNotIn('�',result['content'])

    def test_honors_supported_html_meta_charset_when_http_omits_it(self):
        for declaration in (
            '<meta charset="iso-8859-1">',
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">',
        ):
            with self.subTest(declaration=declaration):
                body=f'<html><head>{declaration}</head><body>Price: £100.</body></html>'.encode('iso-8859-1')
                result=PublicPageReader(opener=Opener(Response(
                    body,headers={'Content-Type':'text/html'})),resolver=public_dns).read('https://example.com/')
                self.assertIn('£100',result['content'])

    def test_ignores_non_charset_meta_attributes_and_rejects_conflicting_meta_charsets(self):
        ignored=b'<html><head><!-- <meta charset="iso-8859-1"> --><meta data-charset="iso-8859-1"></head><body>plain</body></html>'
        result=PublicPageReader(opener=Opener(Response(
            ignored,headers={'Content-Type':'text/html'})),resolver=public_dns).read('https://example.com/')
        self.assertIn('plain',result['content'])
        conflicting=b'<meta charset="utf-8"><meta charset="iso-8859-1">'
        with self.assertRaisesRegex(ValueError,'인코딩'):
            PublicPageReader(opener=Opener(Response(
                conflicting,headers={'Content-Type':'text/html'})),resolver=public_dns).read('https://example.com/')

    def test_rejects_unsupported_invalid_or_mismatched_charset(self):
        cases=(
            (b'plain',{'Content-Type':'text/plain; charset=utf-16'}),
            (b'plain',{'Content-Type':'text/plain; charset='}),
            (b'\xff',{'Content-Type':'text/plain; charset=utf-8'}),
        )
        for body,headers in cases:
            with self.subTest(headers=headers),self.assertRaisesRegex(ValueError,'인코딩'):
                PublicPageReader(opener=Opener(Response(body,headers=headers)),resolver=public_dns).read('https://example.com/')

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

    def test_rejects_truncated_or_concatenated_gzip_evidence(self):
        complete=gzip.compress(b'Grand total: USD 100.')
        for body in (complete[:-8], complete + gzip.compress(b'Injected total: USD 1.')):
            with self.subTest(size=len(body)),self.assertRaisesRegex(ValueError,'압축'):
                PublicPageReader(
                    opener=Opener(Response(body,headers={'Content-Type':'text/plain','Content-Encoding':'gzip'})),
                    resolver=public_dns,
                ).read('https://example.com/')

    def test_rejects_missing_content_type_instead_of_treating_html_as_text(self):
        response=Response(b'<script>Grand total: USD 1.</script>')
        response.headers=Headers({})
        with self.assertRaisesRegex(ValueError,'콘텐츠 유형'):
            PublicPageReader(opener=Opener(response),resolver=public_dns).read('https://example.com/')

    def test_xml_markup_is_parsed_into_visible_text(self):
        """A comment or script body is not something the page shows a reader."""
        for media_type in ('application/xml', 'text/xml'):
            with self.subTest(media_type=media_type):
                body=(b'<feed><!-- Grand total: USD 1. -->'
                      b'<item>No total published.</item></feed>')
                opener=Opener(Response(body=body, headers={'Content-Type':media_type}))
                result=PublicPageReader(opener=opener, resolver=public_dns).read('https://example.com/feed')
                self.assertIn('No total published.', result['content'])
                self.assertNotIn('Grand total', result['content'])
                self.assertNotIn('<item>', result['content'])

    def test_malformed_http_is_a_recoverable_provider_failure(self):
        class Broken:
            def open(self, request, timeout=None): raise http.client.BadStatusLine('broken')
        with self.assertRaisesRegex(Exception, '공개 페이지를 가져오지 못했습니다'):
            PublicPageReader(opener=Broken(), resolver=public_dns).read('https://example.com/')

    def test_malformed_chunked_body_is_a_recoverable_provider_failure(self):
        class Malformed(Response):
            def read(self,size=-1): raise http.client.IncompleteRead(b'partial',10)
        with self.assertRaisesRegex(Exception,'응답을 해석하지 못했습니다'):
            PublicPageReader(opener=Opener(Malformed()),resolver=public_dns).read('https://example.com/')

    @patch('personal_agent.local_tools.socket.create_connection')
    def test_connects_only_to_an_address_validated_in_this_request(self,create_connection):
        """A resolver answering public at validation and private at connect must not be followed."""
        answers=['93.184.216.34','127.0.0.1']
        attempts=[]
        def resolver(host,port,type=None,timeout=None):
            return [(None,None,None,None,(answers.pop(0),port))]
        def connect(address,timeout):
            attempts.append(address);raise OSError('refused')
        create_connection.side_effect=connect
        with self.assertRaises((ProviderError,OSError)):
            PublicPageReader(resolver=resolver).read('http://example.com/')
        self.assertEqual(attempts,[('93.184.216.34',80)])
        # The private second answer is still queued: the connect phase pinned
        # the validated address instead of resolving the host a second time.
        self.assertEqual(answers,['127.0.0.1'])

    @patch('personal_agent.local_tools.socket.create_connection')
    def test_encoded_loopback_host_forms_never_reach_a_private_address(self,create_connection):
        attempts=[]
        def connect(address,timeout):
            attempts.append(address[0]);raise OSError('refused')
        create_connection.side_effect=connect
        for url in ('http://2130706433/','http://127.1/'):
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'개인 네트워크|메타데이터'):
                PublicPageReader(resolver=system_resolver).read(url)
        self.assertEqual(attempts,[])
        # macOS resolves 0177.0.0.1 to the public 177.0.0.1 while glibc gives
        # 127.0.0.1. Address pinning makes that divergence harmless, so assert
        # the security outcome rather than the platform's resolver quirk: the
        # reader either refuses the host or connects only to the exact public
        # address it validated, never to loopback.
        for url in ('http://0177.0.0.1/','http://0x7f.1/'):
            with self.subTest(url=url):
                attempts.clear()
                try: PublicPageReader(resolver=system_resolver).read(url)
                except (ValueError,ProviderError,OSError): pass
                for raw in attempts:
                    self.assertFalse(_denied_address(ipaddress.ip_address(raw)),raw)

    def test_redirect_to_a_cleartext_scheme_is_refused(self):
        opener=Opener(Response(status=302,headers={'Location':'http://example.com/downgraded'}))
        with self.assertRaisesRegex(ValueError,'비보안'):
            PublicPageReader(opener=opener,resolver=public_dns).read('https://example.com/start')
        self.assertEqual(len(opener.requests),1)
        # An upgrade in the other direction stays allowed.
        class Upgrade:
            def __init__(self):
                self.requests=[]
                self.responses=[Response(status=302,headers={'Location':'https://example.com/secure'}),Response()]
            def open(self,request,timeout=None):
                self.requests.append(request);return self.responses.pop(0)
        upgrade=Upgrade()
        result=PublicPageReader(opener=upgrade,resolver=public_dns).read('http://example.com/start')
        self.assertEqual(result['url'],'https://example.com/secure')
        self.assertEqual(upgrade.requests[-1].full_url,'https://example.com/secure')

    def test_redirect_releases_the_previous_response_and_connection(self):
        closed=[]
        class Connection:
            def close(self): closed.append('connection')
        class Redirecting(Response):
            _agentos_connection=Connection()
            def __init__(self):
                super().__init__(status=302,headers={'Content-Type':'text/html','Location':'https://example.com/next'})
            def close(self): closed.append('response')
        class Chain:
            def __init__(self): self.responses=[Redirecting(),Response()]
            def open(self,request,timeout=None): return self.responses.pop(0)
        PublicPageReader(opener=Chain(),resolver=public_dns).read('https://example.com/start')
        self.assertEqual(sorted(closed),['connection','response'])

    @patch('personal_agent.local_tools.MAX_PAGE_SECONDS',0.05)
    @patch('personal_agent.local_tools.socket.create_connection')
    def test_deadline_expiry_during_connect_does_not_leak_the_socket(self,create_connection):
        closed=[]
        class Sock:
            def settimeout(self,_value): pass
            def close(self): closed.append('socket')
        def connect(_address,timeout):
            time.sleep(0.2);return Sock()
        create_connection.side_effect=connect
        reader=PublicPageReader(resolver=public_dns)
        with self.assertRaisesRegex(Exception,'시간이 제한'):
            reader.read('http://example.com/')
        # The expired deadline raises ProviderError, not OSError. The pinned
        # connection must still be released on that unwind path.
        self.assertIn('socket',closed)

    def test_a_real_urllib_opener_is_refused_as_a_production_transport(self):
        with self.assertRaisesRegex(TypeError,'test-only'):
            PublicPageReader(opener=build_opener())

    def test_injected_transport_may_not_report_an_unvalidated_final_url(self):
        class Wandering(Response):
            url='https://collector.example/collect'
        with self.assertRaisesRegex(ValueError,'확인되지 않은 주소'):
            PublicPageReader(opener=Opener(Wandering()),resolver=public_dns).read('https://example.com/event')


if __name__ == '__main__': unittest.main()
