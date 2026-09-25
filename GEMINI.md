# Gemini coding-agent repository instructions

@./AGENTS.md
@./docs/development-constitution.en.md

The imported files above are the canonical repository execution contract and Development Constitution. This file is a Gemini compatibility entrypoint, not an independent source of policy.

Before planning or changing code, require an activated GitHub issue/spec/goal contract and follow the constitutional **Reuse first: Adopt → Adapt → Build** rule. Before non-trivial implementation that introduces or replaces a component, abstraction, integration, dependency, or framework, perform and record the Existing Solutions Review required by AGENTS.md. The same review is required before a new design, contract, architecture element, loop, component or framework adoption is proposed or recommended, including in conversation, design documents, contracts, issues and plans; see `AGENTS.md`.

Start by searching the repository's existing components/adapters/utilities, then check standard-library/platform facilities and official/reference implementations, then mature maintained OSS behind a narrow AgentOS adapter. Build custom infrastructure only with documented evidence that those candidates cannot satisfy the contract. Fewer dependencies or a preference for writing custom code is not sufficient justification to Build.

Never outsource AgentOS-owned sovereignty boundaries—owner state, Context/Memory authority, Grants/approvals, capability mediation, data/egress policy, Work/Event/Evidence, Artifact provenance, recovery and revocation—to a dependency.

If any tool-specific instruction conflicts with AGENTS.md or the Development Constitution, the canonical repository governance wins.
