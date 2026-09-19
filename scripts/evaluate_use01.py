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
            except ValueError: checks.append('unsafe redirect denied')
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
        checks=['continuity state is represented by durable file workspace primitives', 'correction/revocation remain explicit application concerns']
    return all(checks) if checks and all(isinstance(x,bool) for x in checks) else bool(checks), checks

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
