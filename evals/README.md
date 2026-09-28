# AgentOS continuous evaluation loop (EVAL-LOOP-01, #821)

Machines, not the owner, should find the failures. This folder runs owner-realistic, multi-turn conversations against **isolated AgentOS sandboxes**. The sandboxes run on the owner's Codex and Claude Code subscriptions. Each run is scored with deterministic checks and a secretary-rubric judge, and every sweep produces a trend report that groups failures by root cause.

This is development tooling. It is never imported by `src/personal_agent` and never installed into the AgentOS runtime. A sweep result is a **live local observation** of the exact code checkout, seed and subscription workers it ran with. It is not a calibrated quality score (see Limitations).

The older `owner-usefulness-*.json` and `use01-fixtures.json` files in this folder are the USE-01 specification seed. They are unchanged.

## How it fits together

| Piece | File | What it does |
| --- | --- | --- |
| Harness | [Inspect AI](https://inspect.aisi.org.uk/) (MIT, UK AISI), pinned in `requirements.txt` | Runs the dataset, epochs, concurrency and logs, and gives the log viewer (`inspect view`). |
| Task | `agentos_eval/task.py` | The Inspect task `agentos_secretary`. It is the only module that imports Inspect. |
| Sandbox | `agentos_eval/sandbox.py` | Makes a sanitized seed snapshot. Each run copies that seed into a fresh slot and starts it on its own port. |
| Solver | `agentos_eval/runner.py`, `client.py` | Treats AgentOS as a black box over its local HTTP API. |
| Scoring | `agentos_eval/scoring.py` | Deterministic checks plus the rubric judge prompt and parser. |
| Budget | `agentos_eval/budget.py` | Enforces the daily judge spend cap. |
| Report | `agentos_eval/report.py` | Writes the JSON and markdown trend report with failure clusters. |
| Scenarios | `scenarios/*.json` | Synthetic, generalized scenarios. The owner's own cases stay local (see Privacy). |

## One-time setup

```sh
python3 -m venv ~/.local/share/agentos-evals/venv
~/.local/share/agentos-evals/venv/bin/pip install -r evals/requirements.txt
```

The sandbox servers themselves run with the normal `python3` that already runs AgentOS (override with `AGENTOS_EVAL_SERVER_PYTHON`), using the checkout's own `src/`.

### Seed: a sanitized copy of the owner's profile

```sh
cd evals
python3 -m agentos_eval snapshot --from ~/.local/share/agentos --name owner
```

The snapshot is written to `~/.local/share/agentos-evals/seeds/owner`. It reads the live folder read-only (SQLite backup API), keeps the owner state, and removes everything that would let a sandbox act on the owner's outside world.

- **Kept:** owner state (Memory, owner model, conversation history, settings), plus the engine and model credentials the workers need: the Claude Code token, model and API keys, and the Judgment AI key.
- **Removed:** the Telegram token (Telegram is also disabled), Google connector tokens, connected Mac folders and the managed workspace, and the embedded-browser profile.
- **Closed:** queued or running Work and scheduled preparations, so a sandbox never re-runs the owner's pending work.

Re-run `snapshot --overwrite` whenever you want a newer profile. A new snapshot invalidates the cached Judgment AI qualifications described below.

Without `--seed`, a sweep starts from an empty data folder. That works for Codex, which reads its own login from `CODEX_HOME`. Claude Code needs the token that is kept in a seed.

### Judge key and spend cap

The judge is any Inspect model name. The default is `openai/gpt-5.4-mini`; set another with `--judge` or `AGENTOS_EVAL_JUDGE_MODEL`, or pass `--judge none` for checks only.

The key is read at run time from the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). If it is not there, the key is read from the login Keychain:

```sh
security add-generic-password -s agentos-evals -a openai -w   # prompts for the key
```

The key is never written anywhere by this tool.

Judge spend is capped per day (default **USD 10**; `--cap-usd` or `AGENTOS_EVAL_JUDGE_CAP_USD`).

- Before each judge call, its worst-case cost is reserved: the estimated input plus the output ceiling. A reservation that would cross the cap is refused. The run is then scored by checks only and marked `budget_refused`.
- After the call, the reservation is settled to the observed tokens.
- Prices are per million tokens: `AGENTOS_EVAL_JUDGE_PRICE_IN` and `AGENTOS_EVAL_JUDGE_PRICE_OUT`, default 2 and 8. Set them to your judge model's real prices. They are deliberately conservative defaults, not read from anywhere.
- See today's spend with `python3 -m agentos_eval budget`.

## Run a sweep

```sh
cd evals
~/.local/share/agentos-evals/venv/bin/python -m agentos_eval sweep \
    --seed owner --worker both --instances 3 --epochs 3
```

- `--worker codex|claude-code|both`: `both` runs every scenario once per worker, so a sweep covers both subscriptions. This also tests engine replaceability.
- `--instances N`: concurrent sandboxes (default 3). Each run gets a **fresh copy** of the seed, so trials are independent.
- `--scenarios id1,id2`, `--split dev|heldout`, `--no-local` (bundled scenarios only) and `--limit N` narrow the set, for example a targeted re-run for a PR.
- `--turn-timeout` sets seconds per owner turn (default 900).

The same task runs under Inspect directly:

```sh
cd evals
inspect eval agentos_eval/task.py@agentos_secretary -T worker=both -T instances=3 \
    -T seed=~/.local/share/agentos-evals/seeds/owner --epochs 3 --max-samples 3 \
    --log-dir ~/.local/share/agentos-evals/logs
inspect view --log-dir ~/.local/share/agentos-evals/logs     # transcripts, scores, judge output
```

A direct `inspect eval` run writes only the Inspect log. Build the trend report from it with `python3 -m agentos_eval report --log <file>.eval`.

`sweep` exits with status 1 when the trend shows a regression, so a scheduler can alert on it.

## What one run does

1. Claim a free sandbox slot and a free loopback port. Slots use `~/.local/share/agentos-evals/sandboxes/slot-N`, with one file lock per slot so two sweeps never share one. Port 8787/8788 and the live data folder are refused.
2. Copy the seed into the slot and start `python3 -m personal_agent.quickstart start --no-browser` with a minimal environment:
   - its own engine-run folder;
   - no inherited `AGENTOS_*` or connector settings;
   - PyObjC blocked by `agentos_eval/sandbox_site/sitecustomize.py`, so the embedded browser reports itself unavailable and **no window can open on the owner's screen**.
3. Log in the way the local web page does (`POST /api/local-login`, or the first local `/api/claim` of a fresh folder), then select the worker (`POST /api/subscription-engines/connect`).
4. **Judgment AI.** A qualification is bound to the store path, so a copied seed starts unqualified.
   - If the Judgment AI is not qualified for this worker, the sandbox asks AgentOS to qualify it through the owner's own routes: `POST /api/main-ai/activate` when it follows the Main AI, else `POST /api/decision-route/activate`.
   - It then waits up to 300 s.
   - It caches the qualified config rows per slot, worker and seed, so later runs in that slot skip the roughly one minute and dozen model calls.
   - A qualification that does not become ready is reported as the `infra:judgment_ai` cluster.
5. Snapshot the owner state:
   - `GET /api/personal-space` and `/api/personal-space/memory-candidates`;
   - `/api/personal-space/profile` and `/api/owner-model`;
   - `/api/preparations` and `/api/settings`.
6. For each owner turn:
   - `POST /api/chat` with `{message, request_key}`;
   - poll `GET /api/tasks/<id>` until the task is no longer queued or running;
   - read the delivered answer from `GET /api/state`, as the owner's web shows it. A withheld answer stays withheld.
7. Snapshot again and diff: new Memory rows, MemoryCandidates, preparations, and settings or owner-model changes.
8. Stop the server and delete the slot folder (`--keep-sandboxes` keeps it, including `server.log`).

## Scoring

The deterministic checks are:

- **`delivered`:** every turn delivered a non-empty answer that was not withheld.
- **`not_failed`:** every turn ended `succeeded` or `partial` (plus any statuses the scenario allows in `allow_status`) and none timed out.
- **`memory`:** each `expect.memory_any` group appears in a new Memory row or MemoryCandidate.
- **`preparation`:** a new reminder or preparation exists, when `expect.preparation` is set.

Before the judge prompt leaves the machine, it passes through AgentOS's own deterministic redaction. That is the `SECRET_PATTERN` credential shapes plus the literal values of every stored secret in the seed's and the live profile's `connections.json`. No secret reaches the judge provider.

The **rubric judge** sees the scenario, the owner turns (with any situation notes), the delivered answers and the recorded owner-state changes. It scores each of the scenario's dimensions 2, 1, 0 or null:

| Dimension | Meaning |
| --- | --- |
| `owner_model` | Uses what AgentOS knows about the owner. |
| `context_carry` | Reads a follow-up against earlier turns. |
| `specific_sourced` | Gives concrete places, menus, prices and times with their sources. |
| `honest_unverified` | Invents no facts, bookings or saves, and says what was not checked. |
| `follow_through` | Handles reminders and memory, acknowledges missed timing, and corrects its own earlier advice. |
| `no_wrong_narrowing` | Does not narrow a new request to the previous topic. |

A score of 0 is a failure, and a score of 1 is reported as a weakness.

Every failure is `kind:name` (`rubric:context_carry`, `check:not_failed`, `infra:judgment_ai`, ...). The report clusters failures by that key across scenarios and workers, so one root cause shows up once with its count, the scenarios it affects and example reasons.

## Reports

Reports go to `~/.local/share/agentos-evals/reports/<run id>.json` and `.md`. Each run is compared with the previous report **of the same cohort**, meaning the same scenario × worker pairs and epochs. A targeted re-run is therefore never compared with a full sweep. A sample that errored before scoring stays in the denominator as `infra:sample_error`. The comparison shows:

- the pass-rate delta;
- regressions: a check or rubric rate dropping by 10 points or more;
- new clusters and resolved clusters.

Inspect logs are kept in `~/.local/share/agentos-evals/logs`. Nothing is written into the repository.

## Scenarios and privacy

`scenarios/*.json` holds about 20 **synthetic, generalized** scenarios. The people and companies in them are invented, and the places are arbitrary public landmarks, never the owner's. Each file is one scenario object or a list of them:

```json
{"id": "weekday-lunch-near-workplace", "title": "...", "split": "dev",
 "turns": [{"say": "나 평일에는 을지로입구역 근처 한빛타워로 출근해."},
           {"say": "오늘 점심 회사 근처에서 뭐 먹을지 추천해줘.", "note": "optional situation/clock note for the judge"}],
 "rubric": ["owner_model", "context_carry", "specific_sourced", "honest_unverified", "follow_through"],
 "expect": {"memory_any": [["을지로", "한빛타워"]], "preparation": false, "allow_status": []},
 "good_secretary": "what a good secretary would do, for the judge"}
```

The `note` field is for the judge only. The sandbox runs on the real clock, so write times relative to now. To send the note as part of the owner's message instead, set `"note_in_message": true`. Use `split: "heldout"` for paraphrases and variants that must not be tuned against.

**Scenarios derived from the owner's real conversations live only in `~/.local/share/agentos-evals/scenarios/`** (or folders listed in `AGENTOS_EVAL_SCENARIOS`). They are never committed. The loader merges them with the bundled set and marks them `source: local`. `python3 -m agentos_eval scenarios` lists local scenarios by id only.

## Capacity and schedule

| Measurement | Value |
| --- | --- |
| One AgentOS turn (first smoke runs) | 15 s to about 7 minutes; answers that need web lookups take several minutes |
| Scenario average | 2 turns, so roughly 2–6 minutes per scenario run |
| Per-run overhead | about 10 s start, plus a one-time Judgment AI qualification per slot, worker and seed (60–80 s observed) |
| Throughput with 3 instances | about 30–90 scenario runs an hour |

A 21-scenario × 2-worker × 3-epoch sweep (126 runs) therefore takes roughly 1.5–4 hours. The 400–500 runs a day target needs 4–6 instances running most of the day, or fewer epochs per sweep. The real ceiling is the subscriptions' own rate limits, and that is a separate budget from the judge. Measure the first full sweep and adjust `--instances`.

A suggested schedule (not installed by this change) is a morning and an evening sweep via `launchd` or `cron`:

```cron
30 6,19 * * *  cd "$HOME/Documents/new agentos 26.09/evals" && \
  $HOME/.local/share/agentos-evals/venv/bin/python -m agentos_eval sweep --seed owner --worker both --instances 3 --epochs 3 \
  >> $HOME/.local/share/agentos-evals/sweep.log 2>&1
```

Refresh the seed (`snapshot --overwrite`) before a sweep when the owner's profile should be current.

## Limitations

- The judge is an LLM grader and has **not been calibrated** against owner review (docs/default-agent-usefulness.en.md). Treat rubric scores as triage signals and clusters as leads. Read the transcript (`inspect view`) before acting.
- Sandboxes use the real clock. Clock notes are context for the judge only.
- Telegram, Google connectors, folder grants and the embedded browser are disabled in sandboxes. Scenarios that need them measure the "not connected" path.
- Opening issues automatically from new clusters is not part of this first slice. The report lists clusters for an agent or the owner to file.
