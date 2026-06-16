# Docker Runtime Preview Closeout v1

Status: Initial preview implemented

Issue: [#48](https://github.com/Jongtae/agentos/issues/48)

## What This Proves

- `docker compose up` is the primary public try path for the runtime preview.
- `http://localhost:8787` exposes a browser-visible AgentOS preview.
- The preview shows runtime, LLM, Telegram, workspace, and activity state.
- Prompts can be routed through the Phase 2 intent/capability path.
- Activity/proof events are visible through the browser and JSON endpoints.
- User-owned output is written through mounted workspace/user-data paths.

## What This Does Not Prove

- ISO boot ownership
- installer readiness
- reboot/rejoin behavior
- kernel-level supervision
- recovery partition behavior
- VM/ISO freshness

## Validation

Observed locally:

```bash
python3 -m py_compile scripts/docker_entrypoint.py scripts/docker_runtime_preview.py
scripts/smoke_docker_runtime_preview_python.sh
docker compose config
```

Docker daemon was not running in the local environment during this slice, so the
full `scripts/smoke_docker_runtime_preview.sh` check is expected to require
Docker Desktop before it can pass locally.

## Follow-Up

- Run the full Docker smoke on a host with Docker daemon available.
- Expand the web preview from status/prompt/activity into a richer setup flow.
- Keep Telegram polling clearly labeled as Docker preview behavior.
- Continue keeping ISO/VM proof separate from Docker proof.
