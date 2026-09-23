import json,tempfile,unittest
from pathlib import Path
from personal_agent.agent_runtime import Capabilities,run_agent
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.providers import ModelAdapter
CFG={'provider':'compatible','endpoint':'https://openrouter.ai/api/v1','model':'openrouter/free'}
class GeneralRuntimeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=QuickStore(Path(self.tmp.name)/'data');self.root=Path(self.tmp.name)/'docs';self.root.mkdir();(self.root/'launch.txt').write_text('Project Aurora launches October 12.')
  self.svc=AgentService(self.store);self.svc.save_roots({'paths':[str(self.root)]})
  self.caps=Capabilities(self.store,None,CFG,'','job',lambda *a:None)
 def tearDown(self):self.tmp.cleanup()
 def test_file_search_read_and_boundary(self):
  hits=self.caps.execute('find_files',{'query':'Aurora'})['files'];self.assertEqual(hits[0]['path'],'launch.txt')
  self.assertIn('October',self.caps.execute('read_file',{'root_id':hits[0]['root_id'],'path':hits[0]['path']})['content'])
  for path in ['../data/private/connections.json','/etc/passwd']:
   with self.assertRaises(ValueError):self.caps.read_file(hits[0]['root_id'],path)
  (self.root/'escape.txt').symlink_to(Path(self.tmp.name)/'data/private/quickstart.db')
  with self.assertRaises(ValueError):self.caps.read_file(hits[0]['root_id'],'escape.txt')
 def test_notes_idempotent(self):
  self.caps.execute('save_note',{'content':'hello'});self.caps.execute('save_note',{'content':'hello'})
  self.assertEqual(len(self.store.notes()),1)
 def test_tools_do_not_change_with_topic(self):
  payloads=[]
  def transport(u,b,h):payloads.append(b);return {'choices':[{'message':{'content':'일반 답변'}}]}
  for text in ['성남시 날씨','다른 것도 할 수 있어?','파일 찾아줘','에이전트에게 물어봐']:
   run_agent(ModelAdapter(transport),CFG,'',[{'role':'user','content':text}],'',self.caps,lambda *a:None)
  names=[{x['function']['name'] for x in p['tools']} for p in payloads]
  self.assertTrue(all(n==names[0] for n in names));self.assertIn('delegate_agent',names[0]);self.assertTrue(all(p['tool_choice']=='auto' for p in payloads))
 def test_delegation_is_separate_and_cannot_recurse(self):
  seen=[]
  def transport(u,b,h):seen.append(b);return {'model':'specialist-test','choices':[{'message':{'content':'검토 보고서'}}]}
  self.caps.adapter=ModelAdapter(transport)
  r=self.caps.execute('delegate_agent',{'agent_id':'reviewer','task':'이 문구를 검토: 안녕하세요'})
  self.assertEqual(r['model'],'specialist-test');self.assertIn('보고서',r['report'])
  self.assertNotIn('delegate_agent',{t['function']['name'] for t in seen[0]['tools']})
  self.assertNotIn('save_note',{t['function']['name'] for t in seen[0]['tools']})
 def test_chain_find_read_final(self):
  count=0
  def transport(u,b,h):
   nonlocal count
   count+=1
   if count==1:name,args='find_files',{'query':'Aurora'}
   elif count==2:
    hit=json.loads(b['messages'][-1]['content'])['files'][0];name,args='read_file',{'root_id':hit['root_id'],'path':hit['path']}
   else:
    self.assertIn('October 12',b['messages'][-1]['content']);return {'choices':[{'message':{'content':'October 12'}}]}
   return {'choices':[{'message':{'tool_calls':[{'id':str(count),'function':{'name':name,'arguments':json.dumps(args)}}]}}]}
  result=run_agent(ModelAdapter(transport),CFG,'',[{'role':'user','content':'Aurora 출시일을 파일에서 찾아줘'}],'',self.caps,lambda *a:None)
  self.assertEqual(result.content,'October 12')
 def test_weather_falls_back_to_tool_result_when_model_returns_no_final_text(self):
  calls=[0]
  def transport(u,b,h):
   calls[0]+=1
   if calls[0]==1:return {'choices':[{'message':{'tool_calls':[{'id':'weather','function':{'name':'weather','arguments':'{"city":"Seongnam-si","country":"KR"}'}}]}}]}
   return {'choices':[{'message':{'content':''}}]}
  class Weather:
   def execute(self,plan):return {'location':{'name':'Seongnam-si','admin1':'Gyeonggi-do','country':'South Korea'},'forecast':{'current':{'time':'2026-09-07T12:00','temperature_2m':24,'apparent_temperature':25,'precipitation':0,'wind_speed_10m':3},'current_units':{'temperature_2m':'°C','apparent_temperature':'°C','precipitation':'mm','wind_speed_10m':'km/h'},'timezone':'Asia/Seoul'},'sources':['https://open-meteo.example']}
  caps=Capabilities(self.store,ModelAdapter(transport),CFG,'','job',lambda *a:None,network=Weather())
  result=run_agent(caps.adapter,CFG,'',[{'role':'user','content':'성남시 날씨'}],'',caps,lambda *a:None)
  self.assertIn('Seongnam-si',result.content)
  self.assertIn('24 °C',result.content)
if __name__=='__main__':unittest.main()

class ProviderToolProtocolTests(unittest.TestCase):
 def test_ollama_roundtrip(self):
  seen=[]
  def transport(url,body,headers):
   seen.append(body)
   if len(seen)==1:return {'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'list_notes','arguments':{}}}]}}
   return {'message':{'role':'assistant','content':'done'}}
  adapter=ModelAdapter(transport);cfg={'provider':'ollama','endpoint':'http://localhost:11434','model':'test'}
  history=[{'role':'user','content':'notes'}]
  msg,_=adapter.tool_turn(cfg,'',history,[])
  adapter.tool_turn(cfg,'',history+[msg,{'role':'tool','tool_call_id':msg['tool_calls'][0]['id'],'content':'[]'}],[])
  self.assertEqual(seen[1]['messages'][-1]['tool_name'],'list_notes')
  self.assertEqual(seen[1]['messages'][-2]['tool_calls'][0]['function']['arguments'],{})
 def test_anthropic_parallel_results(self):
  seen=[]
  def transport(url,body,headers):
   seen.append(body)
   if len(seen)==1:return {'content':[{'type':'tool_use','id':i,'name':'list_notes','input':{}} for i in ['a','b']]}
   return {'content':[{'type':'text','text':'done'}]}
  adapter=ModelAdapter(transport);cfg={'provider':'anthropic','endpoint':'https://api.anthropic.com','model':'test'}
  history=[{'role':'system','content':'policy'},{'role':'user','content':'notes'}]
  msg,_=adapter.tool_turn(cfg,'test',history,[])
  adapter.tool_turn(cfg,'test',history+[msg]+[{'role':'tool','tool_call_id':i,'content':'[]'} for i in ['a','b']],[])
  self.assertEqual([b['tool_use_id'] for b in seen[1]['messages'][-1]['content']],['a','b'])
  self.assertEqual(seen[1]['messages'][-2]['content'][0]['type'],'tool_use')
 def test_free_router_pins_model_within_run(self):
  seen=[]
  def transport(url,body,headers):
   seen.append(body['model'])
   if len(seen)==1:return {'model':'selected/model:free','choices':[{'message':{'tool_calls':[{'id':'a','function':{'name':'list_agents','arguments':'{}'}}]}}]}
   return {'model':'selected/model:free','choices':[{'message':{'content':'done'}}]}
  with tempfile.TemporaryDirectory() as folder:
   store=QuickStore(Path(folder));adapter=ModelAdapter(transport)
   caps=Capabilities(store,adapter,CFG,'','job',lambda *a:None)
   run_agent(adapter,CFG,'',[{'role':'user','content':'agents'}],'',caps,lambda *a:None)
  self.assertEqual(seen,['openrouter/free','selected/model:free'])
 def test_rate_limit_reroute_preserves_completed_tool(self):
  from personal_agent.providers import ProviderError
  seen=[]
  def transport(url,body,headers):
   seen.append(body)
   if len(seen)==1:return {'model':'selected/model:free','choices':[{'message':{'tool_calls':[{'id':'a','function':{'name':'save_note','arguments':'{"content":"once"}'}}]}}]}
   if len(seen)==2:raise ProviderError('rate limited',status=429)
   self.assertEqual(body['model'],'openrouter/free')
   self.assertEqual(body['messages'][-1]['role'],'tool')
   return {'model':'other/model:free','choices':[{'message':{'content':'saved'}}]}
  with tempfile.TemporaryDirectory() as folder:
   store=QuickStore(Path(folder));adapter=ModelAdapter(transport)
   caps=Capabilities(store,adapter,CFG,'','job',lambda *a:None)
   run_agent(adapter,CFG,'',[{'role':'user','content':'save once'}],'',caps,lambda *a:None)
   self.assertEqual(len(store.notes()),1)
 def test_corrected_arguments_keep_failure_log_but_complete(self):
  count=0;events=[]
  def transport(url,body,headers):
   nonlocal count
   count+=1
   if count<3:return {'choices':[{'message':{'tool_calls':[{'id':str(count),'function':{'name':'list_agents','arguments':'{"bad":"key"}' if count==1 else '{}'}}]}}]}
   return {'choices':[{'message':{'content':'done'}}]}
  with tempfile.TemporaryDirectory() as folder:
   store=QuickStore(Path(folder));adapter=ModelAdapter(transport)
   caps=Capabilities(store,adapter,CFG,'','job',lambda *a:None)
   result=run_agent(adapter,CFG,'',[{'role':'user','content':'list agents'}],'',caps,lambda *a:events.append(a))
   self.assertEqual(result.outcome,'succeeded')
   self.assertIn(('list_agents','failed'),[(e[0],e[1]) for e in events])
 def test_failed_capability_is_not_repeated_for_the_same_arguments(self):
  from personal_agent.providers import ProviderError
  calls=[];events=[];turn=[0]
  def transport(url,body,headers):
   turn[0]+=1
   if turn[0]<3:return {'choices':[{'message':{'tool_calls':[{'id':str(turn[0]),'function':{'name':'web_search','arguments':'{"query":"same query"}'}}]}}]}
   return {'choices':[{'message':{'content':'search failed'}}]}
  class BrokenNetwork:
   def execute(self,plan):calls.append(plan);raise ProviderError('offline')
  with tempfile.TemporaryDirectory() as folder:
   store=QuickStore(Path(folder));adapter=ModelAdapter(transport)
   caps=Capabilities(store,adapter,CFG,'','job',lambda *a:None,network=BrokenNetwork())
   result=run_agent(adapter,CFG,'',[{'role':'user','content':'search'}],'',caps,lambda *a:events.append(a))
  self.assertEqual(result.outcome,'failed')
  self.assertEqual(len(calls),1)
  failed=[json.loads(e[2]) for e in events if e[0]=='web_search' and e[1]=='failed']
  self.assertEqual([e['attempt'] for e in failed],[1,2])
  self.assertIn('한 번만 실행',failed[-1]['error'])
 def test_trace_evidence_keeps_file_content_out_of_event_store(self):
  events=[];count=[0]
  def transport(url,body,headers):
   count[0]+=1
   if count[0]==1:return {'choices':[{'message':{'tool_calls':[{'id':'read','function':{'name':'read_file','arguments':'{"root_id":"root","path":"launch.txt"}'}}]}}]}
   return {'choices':[{'message':{'content':'done'}}]}
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'docs';root.mkdir();(root/'launch.txt').write_text('secret Aurora release detail')
   store=QuickStore(Path(folder)/'data');store.put('file_roots',[{'id':'root','path':str(root)}])
   caps=Capabilities(store,ModelAdapter(transport),CFG,'','job',lambda *a:None)
   run_agent(caps.adapter,CFG,'',[{'role':'user','content':'read'}],'',caps,lambda *a:events.append(a))
  trace=json.loads([e[2] for e in events if e[0]=='read_file' and e[1]=='succeeded'][0])
  self.assertEqual(trace['attempt'],1)
  self.assertEqual(trace['evidence']['path'],'launch.txt')
  self.assertNotIn('secret Aurora release detail',json.dumps(trace))
