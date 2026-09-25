"""Small model adapters. Agent-engine and model contracts remain separate.

Compatible with the original AgentOS separation of engine health/run and model
construction; this module has no host CLI, systemd or third-party dependency.
"""
import json
from dataclasses import dataclass
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


class ProviderError(Exception):
    """Safe, user-facing error; never include upstream bodies, URLs or keys."""
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, body, headers=None, timeout=60):
    req = Request(url, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError('응답이 너무 큽니다. 요청 범위를 줄여 주세요.')
            return json.loads(raw)
    except HTTPError as exc:
        raise ProviderError('무료 모델의 호출 한도에 도달했습니다. 잠시 후 다시 시도하거나 다른 모델을 선택하세요.' if exc.code==429 else f'연결 대상이 HTTP {exc.code} 오류를 반환했습니다. 주소·모델·인증 설정을 확인하세요.', status=exc.code) from None
    except (URLError, TimeoutError, OSError) as exc:
        # A timeout is reported distinctly so a caller with its own time
        # budget (the decision layer) can name it; the owner-facing text is
        # unchanged.
        timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError)
        raise ProviderError('연결할 수 없거나 응답 시간이 초과되었습니다. 서버와 네트워크를 확인하세요.',
                            status='timeout' if timed_out else None) from None
    except (ValueError, TypeError):
        raise ProviderError('연결 대상이 올바른 JSON 응답을 반환하지 않았습니다.') from None


def validate_model(config):
    provider = config.get('provider', '')
    if provider not in ('ollama', 'compatible', 'openai', 'anthropic'):
        raise ValueError('모델 연결 방식을 선택하세요.')
    endpoint = config.get('endpoint', '').rstrip('/')
    parts = urlsplit(endpoint)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('인증 정보나 쿼리가 없는 HTTP(S) 서버 주소를 입력하세요.')
    if provider == 'openai' and endpoint != 'https://api.openai.com/v1':
        raise ValueError('OpenAI 주소는 https://api.openai.com/v1을 사용하세요.')
    if provider == 'anthropic' and endpoint != 'https://api.anthropic.com':
        raise ValueError('Anthropic 주소는 https://api.anthropic.com을 사용하세요.')
    model = config.get('model', '').strip()
    if not model or len(model) > 200:
        raise ValueError('사용할 모델 이름을 입력하세요.')
    return {'provider': provider, 'endpoint': endpoint, 'model': model}


@dataclass
class ModelResult:
    content: str
    provider: str
    model: str


class ModelAdapter:
    def __init__(self, transport=request_json):
        self.transport = transport

    def _send(self, url, body, headers, timeout):
        # Existing transports (including test doubles) take three positional
        # arguments; the timeout is passed only when a caller sets its own.
        return self.transport(url,body,headers) if timeout==60 else self.transport(url,body,headers,timeout)

    def tool_turn(self, config, key, messages, tools, tool_choice="auto", timeout=60, report_observed=False):
        """One tool-capable turn.  Returns ``(message, model)``.

        By default ``model`` falls back to the configured model when the
        provider reports none (existing callers).  ``report_observed=True``
        (the DecisionEngine, #580) returns ``''`` instead, so a requested
        model is never presented as the observed one.
        """
        import uuid
        cfg=validate_model(config);provider=cfg['provider']
        try:
            if provider in ('compatible','openai'):
                body={'model':cfg['model'],'messages':messages,'tools':tools,'tool_choice':tool_choice,'stream':False}
                if cfg['endpoint']=='https://openrouter.ai/api/v1':body['provider']={'require_parameters':True}
                data=self._send(cfg['endpoint']+'/chat/completions',body,{'Authorization':'Bearer '+key} if key else {},timeout)
                message=data['choices'][0]['message']
            elif provider=='ollama':
                converted=[];names={}
                for m in messages:
                    entry=dict(m)
                    if m.get('tool_calls'):
                        entry['tool_calls']=[]
                        for c in m['tool_calls']:
                            names[c['id']]=c['function']['name']
                            entry['tool_calls'].append({'function':{'name':c['function']['name'],'arguments':json.loads(c['function']['arguments'])}})
                    if m['role']=='tool':entry={'role':'tool','tool_name':names.get(m['tool_call_id'],''),'content':m['content']}
                    converted.append(entry)
                data=self._send(cfg['endpoint']+'/api/chat',{'model':cfg['model'],'messages':converted,'tools':tools,'stream':False},{'Authorization':'Bearer '+key} if key else {},timeout)
                message=data['message']
                if message.get('tool_calls'):
                    message['tool_calls']=[{'id':'call_'+uuid.uuid4().hex,'type':'function','function':{'name':c['function']['name'],'arguments':json.dumps(c['function']['arguments'])}} for c in message['tool_calls']]
            else:
                if not key:raise ValueError('Anthropic API 키를 입력하세요.')
                converted=[]
                for m in messages:
                    if m['role']=='system':continue
                    if m['role']=='tool':entry={'role':'user','content':[{'type':'tool_result','tool_use_id':m['tool_call_id'],'content':m['content']}]}
                    elif m['role']=='assistant' and m.get('tool_calls'):
                        blocks=[{'type':'text','text':m['content']}] if m.get('content') else []
                        blocks += [{'type':'tool_use','id':c['id'],'name':c['function']['name'],'input':json.loads(c['function']['arguments'])} for c in m['tool_calls']]
                        entry={'role':'assistant','content':blocks}
                    else:entry={'role':m['role'],'content':[{'type':'text','text':m.get('content') or ' '}]}
                    if converted and converted[-1]['role']==entry['role']:converted[-1]['content']+=entry['content']
                    else:converted.append(entry)
                choice={'type':'any'} if tool_choice=='required' else {'type':'auto'}
                data=self._send(cfg['endpoint']+'/v1/messages',{'model':cfg['model'],'system':'\n'.join(m['content'] for m in messages if m['role']=='system'),'messages':converted,'tools':[{'name':t['function']['name'],'description':t['function']['description'],'input_schema':t['function']['parameters']} for t in tools],'max_tokens':4096,'tool_choice':choice},{'x-api-key':key,'anthropic-version':'2023-06-01'},timeout)
                message={'role':'assistant','content':'\n'.join(c['text'] for c in data['content'] if c['type']=='text')}
                calls=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['input'])}} for c in data['content'] if c['type']=='tool_use']
                if calls:message['tool_calls']=calls
            if not isinstance(message,dict) or message.get('role','assistant')!='assistant':raise TypeError()
            message={k:v for k,v in message.items() if k in ('role','content','tool_calls','reasoning_details')};message['role']='assistant'
            if report_observed:
                actual=data.get('model') if isinstance(data,dict) else None
                return message,actual[:200] if isinstance(actual,str) and actual else ''
            actual=data.get('model') or cfg['model']
            return message,actual if isinstance(actual,str) else cfg['model']
        except (KeyError,IndexError,TypeError,AttributeError):raise ProviderError('도구 응답 형식이 올바르지 않습니다. 도구 호출 지원 모델을 선택하세요.') from None

    def invoke(self, config, key, messages):
        cfg = validate_model(config)
        provider, endpoint, model = cfg['provider'], cfg['endpoint'], cfg['model']
        headers = {'Authorization': 'Bearer '+key} if key else {}
        try:
            if provider == 'ollama':
                data = self.transport(endpoint+'/api/chat', {'model': model, 'messages': messages, 'stream': False}, headers)
                content = data['message']['content']
            elif provider in ('compatible','openai'):
                data = self.transport(endpoint+'/chat/completions', {'model': model, 'messages': messages, 'stream': False}, headers)
                content = data['choices'][0]['message']['content']
            else:
                if not key:
                    raise ValueError('Anthropic API 키를 입력하세요.')
                system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
                history = [m for m in messages if m['role'] != 'system']
                data = self.transport(endpoint+'/v1/messages', {'model': model, 'system': system, 'messages': history, 'max_tokens': 2048}, {'x-api-key': key, 'anthropic-version': '2023-06-01'})
                content = '\n'.join(c['text'] for c in data['content'] if c.get('type') == 'text')
            if not isinstance(content, str) or not content.strip():
                raise ProviderError('모델의 텍스트 응답이 없습니다. 이 모델의 API 호환성을 확인하세요.')
            actual=data.get('model') if isinstance(data,dict) else None
            return ModelResult(content[:24000], provider, actual[:200] if isinstance(actual,str) and actual else model)
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError('예상한 모델 응답 형식과 다릅니다. API 호환성을 확인하세요.') from None
