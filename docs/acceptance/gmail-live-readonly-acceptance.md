# Gmail Live Read-only Acceptance

Status: manual live proof, automated blocker capture

Phase 2 includes fixture-backed Gmail behavior and a read-only OAuth adapter.
Live Gmail proof still requires explicit user credentials and must not be
claimed by automated repository smokes.

## Manual VM Flow

In the VM or local test runtime:

```bash
scripts/agentos-kernelctl gmail-setup --serve-http --host 0.0.0.0 --display-host <vm-ip>
scripts/agentos-kernelctl gmail-status --json > gmail-status.json
scripts/agentos-kernelctl gmail-read --query "roadmap" --json > gmail-read.json
python3 scripts/kernel_gmail_live_acceptance.py \
  --status-json gmail-status.json \
  --read-json gmail-read.json \
  --query roadmap \
  --json
```

The acceptance pack may claim live proof only when:

- Gmail status reports `live_read_ready: true`
- Gmail read reports `adapter: gmail_oauth_readonly`
- Gmail read reports `proof.reason: gmail_live_read_ok`
- no token, refresh token, access token, or client secret appears in output
- no send, delete, archive, draft mutation, label mutation, or calendar mutation
  is executed

## Automated Smoke Boundary

`scripts/smoke_gmail_live_acceptance_pack.sh` verifies both:

- blocker capture when live OAuth is not observed
- schema validation for a synthetic live-success payload

It does not contact Gmail and does not claim user account proof.
