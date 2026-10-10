# Contributing to Personal AgentOS (human + AI)

Thank you for contributing. **Use any AI or no AI.** You do not need a paid subscription, a particular provider, a GPU, or a minimum compute budget. We evaluate reproducible contributions, not model brands or AI usage volume.

## Start here
1. Read [AGENTS.md](AGENTS.md), the [Development Constitution](docs/development-constitution.en.md) and the [documentation map](docs/README.md). They are canonical even if your coding assistant has its own instructions.
2. For a question or exploratory idea, start a discussion or issue; for a reproducible bug, open a bug report. Small documentation/bug fixes may go straight to a focused PR. For architecture, authority, persistent state or breaking changes, discuss the contract/decision first.
3. Before a substantial change, check existing code, issues, contracts and upstream solutions (C15); propose the smallest generalized change (C16). Do not add domain-, provider-, site- or probe-specific branches to the kernel.
4. Fork or branch, write focused tests, and open a PR. Include the structured **Existing solutions review (Adopt / Adapt / Build)** required by CI, commands/results, limitations and relevant evidence. Never include credentials, private owner data or fabricated live evidence.
5. Respond to review findings with a code/test reference or an explicit unresolved limitation. A PR merge is **not** a public release.

## AI-assisted work
A contributor may run multiple AI agents as proposer, implementer, self-reviewer, reviewer or release-preparation assistant. Each role follows the shared [AI collaboration and review contract](docs/governance/ai-contribution-review.en.md). The **human GitHub contributor** remains accountable for submissions, review claims and follow-up. A second model reviewing your own PR is **self-review**, not independent review. Another contributor's review can count as independent only if that person did not author or materially co-author the change.

AI-generated claims, PR comments and model-produced findings are untrusted until checked against code, tests and current contracts. Cite the exact PR head for review evidence. Do not grant an AI unattended merge, secret, production or release authority.

## Optional contribution capacity
You may describe skills, preferred AI tools, role interests, rough availability and willingness to review. These are for coordinating work, **not acceptance criteria or a ranking**. Do not disclose API keys, account entitlements, exact quota, spend or personal financial information. People using free or local models are equally welcome. See [Contributor governance](GOVERNANCE.md).

## Safety, licensing and release
Report security issues privately using [the security policy](.github/SECURITY.md). Contributions are submitted under the repository's [AGPL-3.0-only license](LICENSE); do not copy incompatible third-party code. Current development/release boundaries are in [development governance](docs/development-governance.en.md) and [release policy](docs/governance/release-policy.en.md). The release procedure remains [docs/release.en.md](docs/release.en.md).

A public contribution does **not** activate a goal in `delivery-plan.yaml`. Maintainers decide scheduling and integration separately.
