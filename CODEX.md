# Codex repository instructions

This file is a compatibility entrypoint for a coding tool. It is **not** an independent source of repository policy.

Before planning or changing code, read and follow:

1. [AGENTS.md](AGENTS.md) — common repository execution contract and the primary Codex instruction surface.
2. [Personal AgentOS Development Constitution](docs/development-constitution.en.md) — canonical durable engineering principles.
3. The activated GitHub issue/spec/goal contract for the work.

In particular, the constitutional **Reuse first: Adopt → Adapt → Build** rule is mandatory. Before non-trivial implementation that introduces or replaces a component, abstraction, integration, dependency, or framework, perform and record the Existing Solutions Review required by AGENTS.md. Start by searching the repository's existing components/adapters/utilities, then check standard-library/platform facilities and official/reference implementations, then mature maintained OSS behind a narrow AgentOS adapter. Build custom infrastructure only with documented evidence that those candidates cannot satisfy the contract.

Do not treat a preference for fewer dependencies or writing custom code as sufficient justification to Build. Do not outsource AgentOS-owned sovereignty boundaries—owner state, Context/Memory authority, Grants/approvals, capability mediation, data/egress policy, Work/Event/Evidence, Artifact provenance, recovery and revocation—to a dependency.

If this file conflicts with AGENTS.md or the Development Constitution, the canonical repository governance wins. If a future coding tool does not recognize this filename, the same repository rules still apply.
