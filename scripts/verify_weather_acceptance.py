"""Live native-tool verification with isolated conversations and existing model config."""
import json,tempfile,time,sys
from pathlib import Path
if '--installed' in sys.argv:sys.path.insert(0,'/opt/homebrew/opt/agentos/libexec')
else:sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'src'))
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService
source=QuickStore(Path.home()/'.local/share/agentos')
results=[]
for label,prompt,prior in [('explicit','경기도 성남시 현재 날씨 알려줘',[]),('followup','성남시야. 직접 확인해줘',[('user','오늘 날씨 알려줘'),('assistant','저는 실시간 조회가 불가능합니다.')]),('missing_location','현재 날씨 알려줘',[])]:
 with tempfile.TemporaryDirectory() as root:
  store=QuickStore(root);svc=AgentService(store)
  svc.save_model({**source.config('model'),'api_key':source.secret('model_key')})
  with store.db() as db:
   for role,content in prior:db.execute('INSERT INTO messages(role,content,channel,created) VALUES (?,?,?,?)',(role,content,'web',time.time()))
  job=store.enqueue(prompt,'acceptance-'+label);svc.run_one()
  row=store.jobs()[0]
  with store.db() as db:events=[dict(r) for r in db.execute('SELECT * FROM tool_events WHERE job_id=? ORDER BY id',(job,))]
  success=[e for e in events if e['status']=='succeeded']
  expected='ask_location' if label=='missing_location' else 'weather'
  passed=row['status']=='succeeded' and any(e['tool']==expected for e in success)
  if expected=='weather' and passed:
   payload=json.loads(next(e['detail'] for e in success if e['tool']=='weather'))['result']
   passed=all(str(v) in row['response'] for v in [payload['forecast']['current']['temperature_2m'],payload['forecast']['current']['time'],payload['location']['name'],'https://open-meteo.com/'])
  result={'case':label,'passed':passed,'job_status':row['status'],'model':row['model'],'events':events,'response':row.get('response'),'error':row.get('error')}
  results.append(result);print(label,'PASS' if passed else 'FAIL',row['model'],flush=True)
(Path(__file__).resolve().parents[1]/'docs/archive/root-history/WEATHER_ACCEPTANCE_RESULT.json').write_text(json.dumps({'tested_at':time.time(),'installed':'--installed' in sys.argv,'results':results},ensure_ascii=False,indent=2))
if not all(r['passed'] for r in results):raise SystemExit(1)
