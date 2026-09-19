#!/usr/bin/env python3
"""Run the frozen USE-01 deterministic fixture evaluator.

This intentionally reports boundary/fixture evidence separately from model quality.
The candidate is exercised through the same public-page reader and file workspace
primitives used by the application; no credentials or provider calls are made.
"""
import argparse, hashlib, io, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from personal_agent.file_workspace import FileWorkspace
from personal_agent.local_tools import PublicPageReader
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService
from personal_agent.agent_runtime import Capabilities, run_agent
from personal_agent.providers import ModelAdapter

ROOT=Path(__file__).resolve().parents[1]

class _Response:
    status=200
    def __init__(self, body, content_type='text/html', location=None):
        self._body=io.BytesIO(body.encode()); self.headers={'Content-Type':content_type}
        if location:self.status=302;self.headers['Location']=location
    def read(self, size=-1):return self._body.read(size)

class _Opener:
    def __init__(self, response):self.response=response
    def open(self, request, timeout=None):return self.response

def _dns(host, port, type=None):return [(None,None,None,None,('93.184.216.34',port))]

def deterministic_case(case, fixtures):
    """Return (passed, checks) for one observable fixture contract."""
    family=case['family']; cid=case['id']; checks=[]
    if family=='U1':
        if cid=='U1-06':
            def private_dns(host, port, type=None):
                return [(None,None,None,None,('169.254.169.254',port))] if '169.254' in host else _dns(host,port,type)
            try:
                PublicPageReader(_Opener(_Response('',location='http://169.254.169.254/latest')), private_dns).read('https://official.example/events')
            except ValueError: checks.append(True)
        else:
            page=fixtures['public_pages']['safe']; result=PublicPageReader(_Opener(_Response(page['body'])),_dns).read(page['url'])
            checks += ['official.example' in result['url'], '120 USD' in result['content'], '2030-04-02' in result['content']]
    elif family=='U2':
        with tempfile.TemporaryDirectory() as tmp:
            ref=Path(tmp)/'references'; out=Path(tmp)/'workspace'; ref.mkdir();out.mkdir()
            for doc in fixtures['documents']:
                (ref/doc['name']).write_text(doc['content'])
            store=QuickStore(Path(tmp)/'state'); workspace=FileWorkspace(store); workspace.configure([str(ref)],str(out))
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ref.iterdir()}
            sources=[workspace.read(workspace.status()['references'][0]['id'],doc['name']) for doc in fixtures['documents']]
            result=workspace.save(cid,'meeting-brief','Decisions: launch review on 2030-04-20. Venue remains pending. Next: Mina confirms by 2030-04-18. Budget: 7300 USD; tax unknown.',sources)
            checks += [Path(out/result['path']).is_file(), '2030-04-20' in (out/result['path']).read_text(), '7300 USD' in (out/result['path']).read_text()]
            checks.append(before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ref.iterdir()})
    else:
        if cid=='U3-01':
            with tempfile.TemporaryDirectory() as tmp:
                ref=Path(tmp)/'references'; out=Path(tmp)/'workspace'; ref.mkdir();out.mkdir(); (ref/'meeting.md').write_text('Decision: review on 2030-04-20. Next: Mina confirms venue.')
                state=Path(tmp)/'state'; first=QuickStore(state); workspace=FileWorkspace(first); configured=workspace.configure([str(ref)],str(out)); source=workspace.read(configured['references'][0]['id'],'meeting.md')
                saved=workspace.save(cid,'meeting brief','Decision: review on 2030-04-20. Next: Mina confirms venue.',[source])
                restarted=FileWorkspace(QuickStore(state)); reused=restarted.search('__latest__')
                checks=[Path(out/saved['path']).is_file(), bool(reused), reused[0]['id']==saved['id'], '2030-04-20' in reused[0]['content']]
        elif cid=='U3-02':
            with tempfile.TemporaryDirectory() as tmp:
                ref=Path(tmp)/'references'; out=Path(tmp)/'workspace'; ref.mkdir();out.mkdir(); (ref/'prices.md').write_text('Per adult: 120 USD. Quantity is corrected to one adult.')
                store=QuickStore(Path(tmp)/'state'); workspace=FileWorkspace(store); configured=workspace.configure([str(ref)],str(out)); source=workspace.read(configured['references'][0]['id'],'prices.md')
                saved=workspace.save(cid,'current comparison','Quantity: 1 adult. Total: 120 USD. Do not purchase.',[source]); current=workspace.search('__latest__')
                checks=[bool(current), '1 adult' in current[0]['content'], '120 USD' in current[0]['content'], '2 adults' not in current[0]['content']]
        elif cid=='U3-03':
            with tempfile.TemporaryDirectory() as tmp:
                ref=Path(tmp)/'references'; ref.mkdir(); (ref/'memo.md').write_text('owner material')
                out=Path(tmp)/'out'; out.mkdir(); store=QuickStore(Path(tmp)/'state'); workspace=FileWorkspace(store); state=workspace.configure([str(ref)],str(out)); ref_id=state['references'][0]['id']; store.put('file_workspace',{'references':[],'workspace':state['workspace'],'workspace_id':state['workspace_id']})
                try: workspace.read(ref_id,'memo.md')
                except ValueError: checks=[True]
        elif cid=='U3-05':
            with tempfile.TemporaryDirectory() as tmp:
                store=QuickStore(Path(tmp)/'state'); service=AgentService(store); service.save_model({'provider':'compatible','endpoint':'https://provider-a.example/v1','model':'a'}); service.set_document_approval({'approved':True}); approved=service.document_boundary()['approved']; service.save_model({'provider':'compatible','endpoint':'https://provider-b.example/v1','model':'b'}); checks=[approved, service.document_boundary()['requires_approval'], not service.document_boundary()['approved']]
        elif cid=='U3-06':
            events=[]
            def transport(url,body,headers): return {'choices':[{'message':{'content':'안녕하세요'}}]}
            with tempfile.TemporaryDirectory() as tmp:
                store=QuickStore(Path(tmp)/'state'); caps=Capabilities(store,ModelAdapter(transport),{'provider':'compatible','endpoint':'https://provider.example','model':'test'},'','job',lambda *event:events.append(event))
                result=run_agent(caps.adapter,caps.config,'',[{'role':'user','content':'old search'},{'role':'assistant','content':'old result'},{'role':'user','content':'Just say hello; no tools.'}],'',caps,lambda *event:events.append(event)); checks=[result.content=='안녕하세요', not any(event[0] in ('web_search','public_page_read') for event in events)]
        elif cid=='U3-07':
            from personal_agent.agent_runtime import evidence_summary
            summary=evidence_summary('read_file',{'root_id':'r','path':'memo.md','content':'PRIVATE','locations':['줄 1']}); checks=[summary['path']=='memo.md', summary['characters']==7, 'PRIVATE' not in json.dumps(summary)]
        else:
            checks=[False, 'grader-not-implemented-for-live-continuity-control']
    return bool(checks) and all(check is True for check in checks), checks

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--mode',choices=('deterministic','live'),default='deterministic'); parser.add_argument('--label',default='candidate'); parser.add_argument('--json',action='store_true'); args=parser.parse_args()
    seed=json.loads((ROOT/'evals/owner-usefulness-v0.1.json').read_text()); fixtures=json.loads((ROOT/'evals/use01-fixtures.json').read_text()); rubric=json.loads((ROOT/'evals/owner-usefulness-rubric-v0.1.json').read_text())
    if args.mode=='live':
        report={'label':args.label,'mode':'live','live_quality':'not_run/pending_owner_operation','reason':'No separately authorized provider, destination, data scope or budget was supplied.','cases':[]}
    else:
        rows=[]
        for case in seed['cases']:
            for trial in range(1, rubric['trial_policy']['trials_per_case']+1):
                passed,checks=deterministic_case(case,fixtures); rows.append({'case':case['id'],'family':case['family'],'trial':trial,'passed':passed,'checks':checks,'evidence_class':'deterministic-fixture-boundary'})
        report={'label':args.label,'mode':'deterministic','rubric':rubric['version'],'live_quality':'not_run/pending_owner_operation','case_count':len(seed['cases']),'trial_count':len(rows),'passed':sum(r['passed'] for r in rows),'failed':sum(not r['passed'] for r in rows),'held_out_cases':len(rubric['held_out_paraphrases']),'cases':rows}
    print(json.dumps(report,ensure_ascii=False,indent=2) if args.json else json.dumps({'mode':report['mode'],'label':report['label'],'passed':report.get('passed'),'failed':report.get('failed'),'live_quality':report['live_quality']},ensure_ascii=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
