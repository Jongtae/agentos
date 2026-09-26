"""One-use branch editing helper for #625; deletes itself. No product access."""
from pathlib import Path
import json
import re
import subprocess

BASE = '9aa0c3e6b3658842ab4c5da35d21c76b1384c219'
BRANCH = 'codex/625-current-context-handoff'
ROOT = Path(__file__).resolve().parents[1]
DOCS = ['AGENTS.md', 'PRD.md', 'TASKS.md', 'docs/personal-agentos-architecture.en.md',
        'docs/presence-experience-contract.en.md', 'docs/assistant-execution-contract.en.md',
        'docs/assistant-execution-delivery.en.md', 'docs/roadmap.md']
HELPERS = ['scripts/context_625_adopt_once.py', '.github/workflows/context-625-adopt.yml']
NEW = ['docs/current-context-contract.en.md', 'docs/current-context-implementation.en.md']

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()

def require(ok, why):
    if not ok:
        raise SystemExit(why)

require(git('branch', '--show-current') == BRANCH, 'wrong branch')
require(not git('status', '--porcelain'), 'worktree is not clean')
require(git('merge-base', BASE, 'HEAD') == BASE, 'unexpected base')
require(not (ROOT/'src/personal_agent/delivery-plan.yaml').exists(), 'retired mirror exists')
for name in [*DOCS, 'delivery-plan.yaml']:
    original = subprocess.check_output(['git', 'show', f'{BASE}:{name}'], cwd=ROOT)
    require((ROOT/name).read_bytes() == original, f'preimage changed: {name}')
for name in NEW:
    require((ROOT/name).is_file(), f'missing deliverable: {name}')

path = ROOT/'delivery-plan.yaml'
plan = json.loads(path.read_text())
program = plan['programs']['PRESENCE-01']
require(plan['next_goal']['id'] == 'PRESENCE-01', 'owner selected a different program')
by_issue = {r.get('issue'): r for r in plan['iterations']}
require(607 in by_issue and 608 in by_issue, 'missing existing recovery/eval children')
require(not any(n in by_issue for n in (625,626,627)), 'context already registered')
recovery, evaluation = by_issue[607]['id'], by_issue[608]['id']
order = program['ordered_substeps']
require(recovery in order and evaluation in order and order.index(recovery)<order.index(evaluation), 'unexpected execution order')
ids = ['CONTEXT-ADOPT-01','CONTEXT-INPUT-01','CONTEXT-STATE-01']
plan['iterations'].extend([
 {'id':ids[0],'milestone':'Model-First Presence','issue':625,'kind':'governance',
  'activation_status':'owner-activated-goal-ready','contract':'current-context-contract.en.md',
  'tests':['python3 scripts/verify_master_plan_docs.py','python3 scripts/verify_src_layout.py'],
  'summary':'Owner-directed selective #383 adoption and implementer-ready current-context plan; documentation only, no runtime or live authority.'},
 {'id':ids[1],'milestone':'Model-First Presence','issue':626,'kind':'implementation',
  'depends_on':[ids[0],recovery],'contract':'current-context-contract.en.md',
  'tests':['PYTHONPATH=src python3 -m pytest -q tests/test_context_observations.py'],
  'summary':'Preserve volunteered Telegram location and source time with atomic cursor/dedupe, owner controls and bounded same-QuickStore retention. Follow current-context-implementation.en.md INPUT, CT-01–CT-08.'},
 {'id':ids[2],'milestone':'Model-First Presence','issue':627,'kind':'implementation',
  'depends_on':[ids[1],recovery],'contract':'current-context-contract.en.md',
  'tests':['PYTHONPATH=src python3 -m pytest -q tests/test_current_context.py tests/test_context_consumption.py'],
  'summary':'Use revisable source-bound current state in actual API/CLI weather and local-information tasks; preserve Memory/disclosure authority. Follow current-context-implementation.en.md STATE/EGRESS, CT-09–CT-18.'}
])
idx = order.index(recovery)+1
order[idx:idx] = ids
by_issue[608].setdefault('depends_on',[])
if ids[2] not in by_issue[608]['depends_on']:
    by_issue[608]['depends_on'].append(ids[2])
program['current_context_track'] = {
 'adoption_issue':625, 'implementation_issues':[626,627],
 'contract':'docs/current-context-contract.en.md',
 'playbook':'docs/current-context-implementation.en.md',
 'scope':'Single-owner reactive current state only; #383 patterns/proactivity/multi-person scope remains unselected.',
 'verification':'#612 focused unit tests; necessary no-model boundary integration; no new evaluator.',
 'authority':'Repository implementation after dependencies/review; no actual owner-location collection, paid model run or deployment is authorized by plan adoption.'
}
program['authority'] += ' Owner request 2026-09-26 / #625 additionally selects the bounded #626/#627 current-context implementation after #607; not all of #383.'
program['non_goals'] = [
 ('Unselected #383 Attention/background preparation, pattern learning and multi-person collaboration; #625/#626/#627 current-state scope is explicitly selected.' if '#383' in str(x) else x)
 for x in program.get('non_goals',[])]
program['completion_rule'] += ' The selected current-context extension also requires #626/#627 before #608/#512/#513; input-to-tool consumption is required, not an unused context field. #612 verification cost limits remain.'
plan['next_goal']['action'] += ' Owner amendment 2026-09-26 / #625: perform the bounded documentation adoption now; after existing #607, execute CONTEXT-INPUT-01 #626 then CONTEXT-STATE-01 #627 before #608/#512/#513. Current-state understanding is not excluded by historical #383 Attention deferrals. Do not activate habits, background tracking or multi-person collaboration. Existing #616 and unrelated owner-directed work retain their prior scope/order.'

all_ids = {r['id'] for r in plan['iterations']}
require(len(all_ids)==len(plan['iterations']), 'duplicate iteration ID')
for item in plan['iterations'][-3:]:
    require(set(item.get('depends_on',[])) <= all_ids, 'missing context dependency')
require(order.index(ids[2])<order.index(evaluation), 'context would be stranded after final eval')
path.write_text(json.dumps(plan,separators=(',',':'),ensure_ascii=False)+'\n')

for name in DOCS:
    p=ROOT/name
    text=p.read_text()
    prefix='docs/' if '/' not in name else ''
    note=('\n## Current-context adoption — #625 (2026-09-26)\n\n'
          f'For the selected single-owner current-state scope, read [Current context contract]({prefix}current-context-contract.en.md) and [Implementer playbook]({prefix}current-context-implementation.en.md). '
          'This selectively adopts #383 observation/time/current-state principles, not background Attention or multi-person collaboration. '
          'The plan is existing #605 → #606 → #607 → #626 input/time → #627 current-state consumption → #608/#512/#513; #625 is the immediate documentation adoption. '
          'Existing #616 and other independently directed work are preserved. Current-context claims remain unimplemented until those children deliver. '
          'Earlier blanket #383 deferrals do not exclude these two explicitly selected slices. #612 unit-test-first verification and concrete reuse still govern; no extra evaluator, graph platform or per-tick model calls. '
          'The new source-time, retention, inference/disclosure defaults and migration/test details are canonical in the two linked documents rather than duplicated here.\n')
    require('## Current-context adoption — #625' not in text, f'already adopted: {name}')
    title, rest=text.split('\n',1)
    p.write_text(title+'\n'+note+'\n'+rest.lstrip('\n'))

for name in NEW:
    p=ROOT/name
    for target in re.findall(r'\[[^]]+\]\(([^)#]+)(?:#[^)]*)?\)',p.read_text()):
        if '://' not in target:
            require((p.parent/target).exists(),f'broken local link: {name}: {target}')
for name in HELPERS:
    (ROOT/name).unlink()
changed=set(git('diff','--name-only').splitlines())
require(changed <= set(DOCS+['delivery-plan.yaml']+HELPERS), 'unexpected file mutation')
print('Context adoption: 3 plan entries, 2 implementation owners, canonical pointers; helpers removed. No runtime edits.')
