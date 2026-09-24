"""MP1 R-05 owner-local, policy-owned automated release acceptance."""
import tempfile

from personal_agent.a2a import A2ADelegation
from personal_agent.calendar import CalendarCreate
from personal_agent.capabilities import CapabilityRegistry
from personal_agent.personal_assistant import PersonalAssistantOrchestrator
from personal_agent.portable_state import export_owner_state, restore_owner_state
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


class Peer:
 def __init__(self): self.requests=[]
 def card(self):return {'protocol':'a2a/1','skill':'bounded-research','artifact_schema':'text'}
 def create(self,p):self.requests.append(p);return {'correlation_id':p['correlation_id']}
 def status(self,i,c):return {'correlation_id':c,'state':'completed','artifact':{'id':'artifact','text':'delegated answer'}}
 def cancel(self,i,c):pass

class Drive:
 def __init__(self):self.queries=[]
 def search(self,q):self.queries.append(q);return [{'id':'file-1','name':'project plan','mime_type':'text/plain','token':'never-expose'}]
 def read(self,file_id):return 'private Drive excerpt for the owner only'

def test_mp1_owner_local_orchestrated_flow_and_recovery_acceptance():
 with tempfile.TemporaryDirectory() as root:
  source,target=f'{root}/source',f'{root}/restored';store=QuickStore(source);store.claim(store.bootstrap.read_text(),'a-long-test-password')
  peer,drive,posts=Peer(),Drive(),[];calendar=CalendarCreate(store,lambda u,b,h:posts.append((u,b,h)) or {'id':'event-1'})
  assistant=PersonalAssistantOrchestrator(store,drive=drive,a2a=A2ADelegation(store,peer),calendar=calendar);service=AgentService(store,assistant_orchestrator=assistant);registry=CapabilityRegistry(store)
  for capability,scopes in (('google-drive-read',('read',)),('compatibility-a2a-peer',('delegate',)),('google-calendar-create',('calendar.events',))):registry.transition(capability,'enabled',scopes)
  assert service.personal_assistant_request({'message':'내 개인 공간을 보여줘'})['state']=='completed'
  search=service.personal_assistant_request({'message':'Drive 검색: project','query':'project'});assert search['state']=='completed' and search['sources']==[{'id':'file-1','name':'project plan','mime_type':'text/plain'}]
  excerpt=service.personal_assistant_request({'action':'drive-excerpt-draft','message':'Drive 발췌문: project','file_id':'file-1','length':12});assert excerpt['state']=='awaiting-approval' and not peer.requests
  excerpt_approval=service.personal_assistant_request({'action':'drive-excerpt-approve','message':'Drive 발췌 승인','excerpt_id':excerpt['excerpt']['id']})
  delegated=service.personal_assistant_request({'message':'A2A 위임: 발췌문을 요약해줘','drive_excerpt':{'excerpt_id':excerpt['excerpt']['id'],'approval_id':excerpt_approval['approval_id']}});assert delegated['state']=='requested' and peer.requests[-1]['context']=={'text':'private Driv'}
  draft=service.personal_assistant_request({'message':'일정 초안: 검토','event':{'summary':'review','start':'2026-01-01T10:00','end':'2026-01-01T11:00','timezone':'Asia/Seoul'}});assert draft['state']=='awaiting-approval' and not posts
  approval=service.personal_assistant_request({'action':'calendar-approve','message':'일정 승인','draft_id':draft['draft']['id']})
  created=service.personal_assistant_request({'action':'calendar-create','message':'일정 생성','draft_id':draft['draft']['id'],'approval_id':approval['approval']['approval_id']});assert created['state']=='completed' and len(posts)==1
  registry.transition('google-drive-read','paused');assert service.personal_assistant_request({'message':'Drive 검색: project'})['state']=='blocked'
  registry.transition('compatibility-a2a-peer','disconnected');assert service.personal_assistant_request({'message':'A2A 위임: 다시 조사해줘'})['state']=='blocked'
  registry.transition('google-calendar-create','paused');assert service.personal_assistant_request({'action':'calendar-create','message':'일정 생성','draft_id':draft['draft']['id'],'approval_id':approval['approval']['approval_id']})['state']=='blocked'
  assert service.personal_assistant_request({'message':'알 수 없는 요청'})['state']=='fallback'
  evidence=str(store.config('personal_assistant_evidence'));assert 'private Drive excerpt' not in evidence and 'never-expose' not in evidence and approval['approval']['approval_id'] not in evidence
  archive=export_owner_state(source,f'{root}/owner.tar.gz');restored=QuickStore(restore_owner_state(archive,target))
  assert restored.config('drive_excerpt_approvals') is None
  assert restored.config('personal_assistant_evidence')
  assert 'private Drive excerpt' not in str(restored.config('personal_assistant_evidence'))
  assert 'never-expose' not in str(restored.config('a2a_delegations'))
  assert approval['approval']['approval_id'] not in str(restored.config('calendar_create'))
