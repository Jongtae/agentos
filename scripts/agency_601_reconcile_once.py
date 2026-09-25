"""One-shot conflict reconciliation of the verified concurrent #599 plan.
No runtime changes, no force push, and no unreviewed main content discarded.
"""
import json
from pathlib import Path
import subprocess
BASE='4a0d3e6fba987121298addb7349778a0a1b349bc'
OURS='de96d1f2b6958b54b3adf2b68d96c925b4972828'
THEIRS='a7f66961c473644d65b0700b808b00d7fece8fe1'
def read(ref,path):return subprocess.check_output(['git','show',ref+':'+path],text=True)
conflicts=set(subprocess.check_output(['git','diff','--name-only','--diff-filter=U'],text=True).splitlines())
if conflicts-{'delivery-plan.yaml'}:raise SystemExit('Unexpected conflict: '+repr(conflicts))
b,o,t=[json.loads(read(ref,'delivery-plan.yaml')) for ref in (BASE,OURS,THEIRS)]
record=[]
def merge(base,ours,theirs,path=''):
 if ours==theirs:return ours
 if ours==base:return theirs
 if theirs==base:return ours
 if isinstance(ours,dict) and isinstance(theirs,dict):
  result={}
  for k in set(ours)|set(theirs):
   if k not in ours:result[k]=theirs[k]
   elif k not in theirs:result[k]=ours[k]
   else:result[k]=merge(base.get(k) if isinstance(base,dict) else None,ours[k],theirs[k],path+'/'+k)
  return result
 if isinstance(ours,list) and isinstance(theirs,list):
  if all(isinstance(v,dict) and 'id' in v for v in ours+theirs):
   bd={v['id']:v for v in (base or [])};od={v['id']:v for v in ours};td={v['id']:v for v in theirs}
   ids=list(od)+[k for k in td if k not in od]
   return [merge(bd.get(k),od[k],td[k],path+'/'+k) if k in od and k in td else od.get(k,td.get(k)) for k in ids]
  if all(isinstance(v,(str,int)) for v in ours+theirs):return list(dict.fromkeys(ours+theirs))
 if isinstance(ours,str) and isinstance(theirs,str):
  # Current new program/child wording is normative. Retain superseded incoming
  # prose as attributable historical decision evidence, never as a second queue.
  allowed=('summary','authority','completion_rule','action','rule','purpose','description','validation','evidence','non_goals')
  if path.rsplit('/',1)[-1] in allowed:
   record.append({'path':path,'incoming_decision':theirs,'disposition':'Preserved as historical #599 decision; current #600 refinement governs the expanded scope.'})
   return ours
 raise SystemExit('Unresolved semantic conflict: '+path)
merged=merge(b,o,t)
program=merged['programs']['PRESENCE-01']
program.setdefault('execution_integration',{})['concurrent_owner_decision']={'commit':THEIRS,'pr':599,'retained_conflicting_prose':record}
# #599's independent work-unit/evaluation ownership and existing dependencies
# are retained by recursive union; the current program orders shared files.
Path('delivery-plan.yaml').write_text(json.dumps(merged,ensure_ascii=False,separators=(',',':'))+'\n')
subprocess.run(['git','add','delivery-plan.yaml'],check=True)
if subprocess.check_output(['git','diff','--name-only','--diff-filter=U'],text=True).strip():raise SystemExit('Unresolved files remain')
Path(__file__).unlink()
