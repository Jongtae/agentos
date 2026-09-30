"""Inspect AI task: AgentOS as a black-box solver, scored by checks plus a rubric judge.

Run with Inspect directly::

    inspect eval evals/agentos_eval/task.py@agentos_secretary -T worker=both -T instances=3 \\
        -T seed=~/.local/share/agentos-evals/seeds/owner --epochs 3 --max-samples 6

or through ``python -m agentos_eval sweep`` (evals/README.md), which also writes
the trend report.  This is the only module that imports Inspect AI.
"""
import asyncio
import os
import sys
from pathlib import Path

if __package__ in (None, ''):
    # `inspect eval evals/agentos_eval/task.py` loads this file by path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import (ChatMessageAssistant, ChatMessageSystem, ChatMessageUser, GenerateConfig,
                              ModelOutput, get_model)
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver
from inspect_ai.util import EarlyStop

from agentos_eval import scenarios as scenario_module
from agentos_eval.budget import JudgeBudget, estimate_tokens
from agentos_eval.paths import eval_home
from agentos_eval.redaction import Redactor
from agentos_eval.runner import WORKERS, StopOnUsageLimit, run_scenario
from agentos_eval.sandbox import SandboxPool
from agentos_eval.scoring import (JUDGE_MAX_TOKENS, JUDGE_SYSTEM, combine, deterministic_checks, judge_prompt,
                                  parse_judgment)

DEFAULT_JUDGE = 'openai/gpt-5.4-mini'

def workers_for(worker):
    if worker in ('both', 'split'):
        return WORKERS
    if worker not in WORKERS:
        raise ValueError(f'worker must be codex, claude-code or both (got {worker!r})')
    return (worker,)


def dataset(scenario_ids='', split='', worker='codex', include_local=True):
    ids = [item for item in scenario_ids.split(',') if item] if isinstance(scenario_ids, str) else list(scenario_ids)
    loaded = scenario_module.load(include_local=include_local, split=split or None, ids=ids or None)
    samples = []
    for scenario in loaded:
        for each in workers_for(worker):
            samples.append(Sample(id=f"{scenario['id']}@{each}", input=scenario['turns'][0]['say'],
                                  metadata={'scenario': scenario, 'worker': each}))
    return MemoryDataset(samples, name='agentos-secretary')


@solver
def agentos_blackbox(pool, turn_timeout=900, judgment_timeout=300):
    async def solve(state: TaskState, generate: Generate):
        meta = state.metadata
        record = await asyncio.to_thread(run_scenario, meta['scenario'], meta['worker'], pool,
                                         turn_timeout=turn_timeout, judgment_timeout=judgment_timeout)
        messages = []
        for turn in record['turns']:
            messages.append(ChatMessageUser(content=turn['say']))
            messages.append(ChatMessageAssistant(content=turn['answer'] or f"(no answer; status {turn['status']})"))
        state.messages = messages or state.messages
        last = record['turns'][-1]['answer'] if record['turns'] else ''
        state.output = ModelOutput.from_content(model='agentos', content=last or '')
        state.metadata['run'] = record
        state.completed = True
        return state
    return solve


@scorer(metrics={'*': [mean()]})
def secretary(judge='grader', budget_path=None, seed=None):
    budget = JudgeBudget.from_environ(budget_path or eval_home() / 'judge-budget.json')
    redact = Redactor.for_seed(seed)

    async def score(state: TaskState, target: Target):
        scenario, run = state.metadata['scenario'], state.metadata.get('run') or {'error': 'solver did not run'}
        checks, failures = deterministic_checks(scenario, run)
        judgment, judge_status = None, 'skipped'
        if judge != 'none' and not run.get('error'):
            prompt = redact(judge_prompt(scenario, run))
            reserved = budget.reserve(estimate_tokens(JUDGE_SYSTEM + prompt), JUDGE_MAX_TOKENS)
            if reserved is None:
                judge_status = 'budget_refused'
            else:
                try:
                    model = get_model(role='grader') if judge == 'grader' else get_model(judge)
                    output = await model.generate([ChatMessageSystem(content=JUDGE_SYSTEM), ChatMessageUser(content=prompt)],
                                                  config=GenerateConfig(max_tokens=JUDGE_MAX_TOKENS))
                    usage = output.usage
                    budget.settle(reserved, usage.input_tokens if usage else None, usage.output_tokens if usage else None)
                    judgment = parse_judgment(output.completion, scenario['rubric'])
                    judge_status = 'judged'
                except Exception as exc:  # noqa: BLE001 - a judge outage must stay in the denominator
                    judge_status = 'judge_error'
                    failures = [*failures, {'kind': 'infra', 'name': 'judge',
                                            'reason': redact(f'{type(exc).__name__}: {exc}')[:200]}]
        value, metadata = combine(scenario, run, checks, failures, judgment, judge_status)
        explanation = (judgment or {}).get('summary') or '; '.join(f"{row['name']}: {row['reason']}" for row in failures)
        return Score(value=value, answer=(state.output.completion or '')[:500], explanation=explanation or 'ok',
                     metadata=metadata)
    return score


@task
def agentos_secretary(scenarios='', split='', worker='codex', instances=3, seed='', judge='',
                      turn_timeout=900, judgment_timeout=300, include_local=True, keep_sandboxes=False):
    """Multi-turn owner scenarios against fresh AgentOS sandboxes, on Codex and/or Claude Code."""
    seed = seed or os.environ.get('AGENTOS_EVAL_SEED', '')
    judge = judge or os.environ.get('AGENTOS_EVAL_JUDGE_MODEL', DEFAULT_JUDGE)
    pool = SandboxPool(size=int(instances), seed=Path(seed).expanduser() if seed else None,
                       keep=str(keep_sandboxes).lower() in ('1', 'true', 'yes'))
    include_local = str(include_local).lower() not in ('0', 'false', 'no')
    return Task(dataset=dataset(scenarios, split, worker, include_local),
                solver=agentos_blackbox(pool, int(turn_timeout), int(judgment_timeout)),
                scorer=secretary('none' if judge == 'none' else 'grader', seed=Path(seed).expanduser() if seed else None),
                model='none/none',
                early_stopping=StopOnUsageLimit(EarlyStop),
                model_roles=None if judge == 'none' else {'grader': judge},
                metadata={'worker': worker, 'instances': int(instances), 'seed': bool(seed), 'judge': judge})
