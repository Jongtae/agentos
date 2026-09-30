# v1 acceptance

Validated on 2026-09-07:

- Automated validation is required for each delivery iteration; V1-02 covers
  paired-owner task cards, progress, queued-only cancellation, document
  approval, and restart/ambiguous-delivery recovery without automatic replay.
- The installed CLI setup, authenticated note, restart persistence, and
  single-instance checks passed.
- Docker Compose built the current image, retained a named data volume, and
  reported a healthy loopback service.
- Model, Telegram pairing, document boundaries, local documents, notes, and
  bounded delegation retain their acceptance evidence from M1 and M2.

For V1-02 live acceptance, the paired owner must submit a natural-language
request, observe its status-only task card, cancel or approve a task, and
check the card after a restart or delivery failure. AgentOS does not claim
Telegram delivery when it is uncertain and does not replay the work or the
uncertain delivery automatically.

The owner must supply their own model credentials and Telegram bot token;
these secrets are never packaged in a release artifact.
