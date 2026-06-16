# Docker Runtime Preview Acceptance

Status: Active Preview

Docker is the easiest public way to try the AgentOS runtime today. It does not
claim to prove boot ownership, installer behavior, reboot/rejoin, recovery
partition behavior, kernel-level supervision, or ISO freshness.

## Required User Flow

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
docker compose up
```

Then open:

```text
http://localhost:8787
```

## Acceptance Criteria

- `docker compose up` starts a local AgentOS preview.
- `http://localhost:8787` opens.
- Runtime status is visible.
- A customer-facing Runtime Home is visible.
- Work Inbox, Activity Timeline, Recovery Center, and Evidence Dashboard states are summarized.
- LLM setup/readiness state is visible.
- Telegram setup/readiness state is visible.
- Activity feed is visible.
- At least one prompt can be routed through intent dispatch.
- Proof/log output is written under `./agentos-data` or mounted workspace paths.
- Missing credentials appear as degraded/setup-needed states, not raw tracebacks.
- No raw Telegram token, OpenAI key, or OAuth token is written to committed files or proof/activity output.

## Suggested Manual Checks

Run these from the web preview:

```text
hi
status
workspace 파일 목록 보여줘
search AgentOS roadmap and summarize it
```

Expected behavior:

- greeting does not trigger web search
- status returns runtime state
- Runtime Home explains product-layer readiness and proof blockers
- workspace request uses bounded local workspace behavior
- search-style request routes through search-like intent
- activity feed narrates request, intent, capability, and result

## Automated Smoke

```bash
scripts/smoke_docker_runtime_preview.sh
```

The smoke should validate compose config, build the image, start the preview,
check `localhost:8787`, verify `/api/product`, run a prompt through
`/api/prompt`, verify activity, and check that common secret patterns are not
present in the response.
