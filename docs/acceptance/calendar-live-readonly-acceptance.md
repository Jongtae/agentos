# Calendar Live Read-only Acceptance

Status: manual live proof, automated blocker capture

Phase 2 includes fixture-backed Calendar behavior and a runtime status surface
for read-only Calendar readiness. Live Calendar proof still requires explicit
tester credentials and must not be claimed by automated repository smokes.

## Manual VM Flow

In the VM or local test runtime:

```bash
scripts/agentos-kernelctl phase2-run --message "status" --json > calendar-status.json
scripts/agentos-kernelctl phase2-run --message "summarize my calendar roadmap events" --json > calendar-read.json
python3 scripts/kernel_calendar_live_acceptance.py \
  --status-json calendar-status.json \
  --read-json calendar-read.json \
  --query roadmap \
  --json
```

The acceptance pack may claim live proof only when:

- Calendar status reports `live_oauth_ready: true`
- Calendar read reports `adapter: calendar_oauth_readonly`
- Calendar read reports `proof.ok: true`
- no token, refresh token, access token, client secret, or private key appears
  in output
- no create, update, delete, invite, cancel, label, email, or draft mutation is
  executed

## Automated Smoke Boundary

`scripts/smoke_calendar_live_acceptance_pack.sh` verifies both:

- blocker capture when live Calendar OAuth is not observed
- schema validation for a synthetic live-success payload

It does not contact Calendar and does not claim user account proof.
