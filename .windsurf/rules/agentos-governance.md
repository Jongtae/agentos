---
trigger: always_on
description: Personal AgentOS canonical repository governance
---

This is a Windsurf compatibility entrypoint, not an independent source of policy.

Before planning or changing code, read and follow:
- AGENTS.md
- docs/development-constitution.en.md
- the activated GitHub issue/spec/goal contract.

The constitutional Reuse first: Adopt → Adapt → Build rule is mandatory. Before non-trivial implementation that introduces or replaces a component, abstraction, integration, dependency, or framework, perform and record the Existing Solutions Review. The same review is required before a new design, contract, architecture element, loop, component or framework adoption is proposed or recommended, including in conversation, design documents, contracts, issues and plans; see `AGENTS.md`. Start with reusable repository components/adapters/utilities, then standard-library/platform facilities and official/reference implementations, then mature maintained OSS behind a narrow AgentOS adapter. Build only with documented evidence that those candidates cannot satisfy the contract.

Never outsource AgentOS-owned owner state, Context/Memory authority, Grants/approvals, capability mediation, data/egress policy, Work/Event/Evidence, Artifact provenance, recovery, or revocation to a dependency.

If tool-specific instructions conflict with AGENTS.md or the Development Constitution, canonical repository governance wins.
