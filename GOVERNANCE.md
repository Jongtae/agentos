# Governance: contributors, AI roles and decisions

Personal AgentOS currently uses **maintainer-led governance**. The project owner maintains product direction, constitutional authority and stable-release authorization. Additional maintainers or reviewers may be delegated explicit scopes later; no AI or contributor receives those permissions from a role label alone.

## People, assignments and AI
- **Contributor**: the accountable person (or organization) behind an issue, PR or review.
- **Assignment**: a contributor's role on a particular PR/issue, not a permanent identity. One person may implement PR A, review PR B and prepare release notes for C.
- **AI role**: proposer, implementer, self-reviewer, independent-review assistant, maintainer-decision assistant or release-preparation assistant. AI instances are tools, not members, votes or GitHub permission principals.
- **Mandate**: bounded issue/PR, scope, expected evidence, time/budget if agreed and permitted actions.
- **Authority**: GitHub permissions, protected-branch requirements, secret access and release authorization, always separately granted.

Contributors own their AI accounts and costs. AI capability/availability profiles are voluntary; no model subscription, paid compute or model count is required for participation. Credit follows verified outcomes, bug reports, documentation, research and substantive reviews, not tokens spent.

## Decision rights
- Everyone may propose, question, implement and comment under the project code of conduct.
- Reviewers may recommend changes, approval or rejection with cited findings. The author's own AI reviews do not satisfy an independent-review requirement.
- An authorized maintainer decides merge only after applicable current-head checks and findings are resolved or explicitly accepted under policy. AI majority votes or persuasive prose are insufficient.
- Material constitutional/owner-authority changes require the existing dedicated owner governance decision; security/authority escalations follow the Development Constitution.
- Only an authorized release maintainer may approve stable release publication; merging `main` never publishes a release automatically.

## Disagreement and conflicts
Record the competing claims, affected contract, reproducer/evidence, residual risk and explicit decision. One substantive response and one focused re-review is the normal bounded loop; unresolved policy questions escalate to a human maintainer instead of endless AI debate. An author or material co-author cannot supply independent review of the same PR, regardless of using different AI models. Disclose relevant authorship or conflicts. A reviewer may be a contributor elsewhere in the project.

See [AI review protocol](docs/governance/ai-contribution-review.en.md), [release policy](docs/governance/release-policy.en.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [Development Constitution](docs/development-constitution.en.md). GitHub native reviews, permissions, CI and branch rules are authoritative for enforcement; documentation alone does not configure protection.
