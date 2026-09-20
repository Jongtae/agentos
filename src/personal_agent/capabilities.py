"""Reviewed capability lifecycle; never installs or executes arbitrary code."""
import time

CATALOGUE=(
 {'id':'builtin-mcp-read','kind':'mcp','version':'1','tools':['read_only'],'scopes':['read']},
 {'id':'google-drive-read','kind':'mcp','version':'1','tools':['search','read_selected'],'scopes':['read']},
 {'id':'compatibility-a2a-peer','kind':'a2a','version':'1','tools':['delegate'],'scopes':['delegate']},
 {'id':'google-calendar-create','kind':'mcp','version':'1','tools':['draft_event'],'scopes':['calendar.events']},
 {'id':'isolated-runtime-placeholder','kind':'runtime','version':'1','tools':[],'scopes':[]},
)
STATES={'available','connected-disabled','enabled','paused','auth-required','error','disconnected'}

class CapabilityRegistry:
 def __init__(self,store): self.store=store
 def list(self):
  saved=self.store.config('capability_registry',{})
  saved=saved if isinstance(saved,dict) else {}
  return [{**item,'tools':list(item['tools']),'scopes':list(item['scopes']),'state':saved.get(item['id'],{}).get('state','available'),'grant':list(saved.get(item['id'],{}).get('grant',[]))} for item in CATALOGUE]
 def transition(self,capability_id,target,approved_scopes=()):
  item=next((x for x in CATALOGUE if x['id']==capability_id),None)
  if not item or target not in STATES: raise ValueError('검토된 capability와 상태를 확인하세요.')
  if target=='enabled' and set(item['scopes'])!=set(approved_scopes): raise ValueError('선언된 scope의 명시 승인이 필요합니다.')
  saved=self.store.config('capability_registry',{});prior=saved.get(capability_id,{})
  event={'state':target,'changed_at':time.time()}
  if target=='enabled': event['approved_scopes']=sorted(approved_scopes)
  grant=event.get('approved_scopes',prior.get('grant',[]))
  if target in {'available','auth-required','error','disconnected'}: grant=[]
  saved[capability_id]={**prior,'state':target,'changed_at':event['changed_at'],'grant':grant,'audit':[*(prior.get('audit',[])),event][-50:]};self.store.put('capability_registry',saved)
  return next(x for x in self.list() if x['id']==capability_id)
 def require_enabled(self,capability_id,scope):
  """The sole lifecycle gate used before a reviewed capability is invoked."""
  item=next((x for x in self.list() if x['id']==capability_id),None)
  if not item or scope not in item['scopes']:
   raise ValueError('검토된 capability와 scope를 확인하세요.')
  if item['state']!='enabled' or scope not in item.get('grant',[]):
   raise ValueError('이 capability는 현재 사용할 수 없습니다. 연결 상태와 승인을 확인하세요.')
  return item
