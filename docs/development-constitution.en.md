# Personal AgentOS Development Constitution

## Status

This is the canonical development-constitution layer for repository work. It defines durable engineering principles that every new specification, plan, issue, implementation and review must preserve unless the owner explicitly changes the constitution in a dedicated governance issue.

It adapts useful patterns from spec-driven development and explicit state/authority governance. It is a **development process contract**, not a Personal AgentOS runtime dependency and not evidence of live autonomous operation.

## Development sequence

Every material product change should progress through:

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`

- **Constitution**: confirm the change does not violate durable product/security principles.
- **Spec**: state owner outcome, behavior, boundaries, non-goals and acceptance criteria without prematurely selecting an implementation.
- **Authority/Threat Model**: state what data, permissions, runtimes, packages, networks, secrets and external effects are involved; identify abuse/failure paths.
- **Plan**: choose architecture, compatibility/migration strategy, implementation sequence and evidence plan.
- **Tasks**: create bounded issue-linked work units with dependencies and explicit stopping rules.
- **Implement**: change only the activated bounded goal, preserving existing state/evidence.
- **Verify**: map every acceptance criterion to current automated/operating evidence, including negative tests where authority/security is involved.
- **Converge**: independently review contradictions, stale docs/plans, open findings and current GitHub state before merge/closeout.

Issue creation, planning documents, or passing local tests alone do not activate or complete a goal.

## Constitutional principles

### C1. One owner, one durable personal state

Canonical owner Context/Memory, Grants, Work state, Artifacts, approvals, Evidence and recovery belong to the owner-controlled AgentOS domain. A model, AgentPackage, runtime, connector, Registry, Marketplace or development framework must not silently become the source of truth for that state.

### C2. The kernel is agent-independent

Product UX may present installable agents, but kernel semantics are Owner, Context, Memory, Artifact, Capability, Runtime, Grant, Work, Event and Evidence. No feature may require a particular agent framework merely to preserve owner state or authority semantics.

### C3. Install is not authorization

`downloaded != installed != enabled != connected != authorized-for-action`.

Installing, updating, enabling, connecting or discovering a package does not imply action authority. Grants come from current owner/policy decisions and are evaluated for the exact Work/resource/action/destination/revision as required by the contract.

### C4. Minimum authority and explicit external boundaries

Packages, runtimes, tools, connectors and nested agents receive only task-required authority. File, network, secret, external-recipient and consequential-action boundaries are explicit. Read authority never silently implies write/delete/send/privilege/payment authority.

### C5. Context is not automatic Memory

Task Context is bounded and attributable. Complete conversation history or package-local state does not automatically become canonical owner Memory. Third-party durable-memory writes are candidate/review based unless a separately reviewed policy explicitly permits more.

### C6. Evidence before capability claims

Designs, issues, mocks, fixtures, signatures, static scans, local tests, CI and live operating observations are different evidence classes. Claims must name the exact evidence class. A package listing, successful install, or passing mock does not prove live safe operation.

### C7. Exact revision and provenance

Security- or behavior-relevant evidence identifies exact code/package/runtime revision where possible. Package/update work must record digest/version and permission/data/egress changes. Mutable names such as `latest` cannot serve as completion evidence.

### C8. Recoverable and idempotent Work

Long-running Work must have bounded ownership/lease, cancellation, checkpoints, retry limits and recovery semantics appropriate to the capability. Restart or retry must not duplicate consequential external effects. Failures remain explicit rather than being rewritten as completion.

### C9. Trust is multidimensional

Publisher identity, signature/integrity, build provenance, static validation, behavioral conformance, permission risk, incident history, popularity, user reviews and curation are separate signals. `Verified` must always state what was verified. Popularity never grants permission.

### C10. Safe update, rollback, disable and removal

An update that expands permissions, data destinations, memory/background behavior, dependencies, budgets or consequential actions requires new authority. Failed updates preserve/recover a known-good state where supported. Disable/quarantine/uninstall removes package authority without deleting owner-owned Artifacts or retained Evidence unless an explicit owner data-deletion decision says otherwise.

### C11. Framework and runtime replaceability

Spec Kit, BuilderMethods Agent OS, Open AgentOS-style governance, Ruflo, MCP, A2A, Codex, Claude Code or future frameworks may contribute patterns/adapters. None gains implicit authority over Personal AgentOS kernel state merely because the repository uses or supports it.

### C12. Historical authority is immutable evidence

Closed/historical contracts describe what was authorized and proved at that time. New architecture extends them through successor issues/contracts. Do not retroactively widen old scopes to make a new feature appear previously implemented.

### C13. No automatic successor selection

Completing a substep or program does not authorize the next feature. Only an explicitly owner-activated goal-ready issue/program may execute. Planned issue lists and roadmap order express dependency/intention, not standing execution authority.

### C14. Human gates remain real gates

Identity verification, MFA/CAPTCHA, legal/vendor agreement acceptance, payment, sensitive external-action approval, material product-policy expansion and other declared owner-only decisions cannot be simulated or silently bypassed to preserve automation.

## AgentPackage-specific review checklist

Any PR that changes package/runtime/distribution behavior must answer:

1. What exact package/runtime revisions are involved?
2. What permissions, owner-data scopes and external destinations changed?
3. What Memory read/write behavior changed?
4. What Event/background subscriptions changed?
5. What secret/credential boundary changed?
6. What supply-chain/signature/provenance evidence exists?
7. What update/rollback/uninstall behavior changed?
8. What current negative tests prove undeclared/excess authority is denied?
9. What evidence class supports the capability claim?
10. Does the change preserve kernel authority and portability?

## Change policy

A material change to these constitutional principles requires:

- a dedicated issue stating why an existing principle is insufficient or wrong;
- impact analysis across architecture, security, existing contracts and historical evidence;
- independent review;
- repository-required CI;
- explicit owner approval before merge when the change expands durable authority or weakens an existing safety invariant.
