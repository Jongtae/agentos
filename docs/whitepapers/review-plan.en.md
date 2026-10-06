# Whose Agent? — Editorial record and completed v0.3 review

- Follow-up: [WHITEPAPER-02 #1045](https://github.com/Jongtae/agentos/issues/1045).
- Manuscript: [Korean v0.3](whose-agent.ko.md).
- Review date: 2026-10-06.
- Method: **ten sequential role-based self-review passes by the same authoring assistant**; nine passes revised the manuscript and the tenth verified it without further edits.
- Final editor role: **APPROVED for publication as a non-normative industry/strategy discussion**.
- Final verifier role: **APPROVED within the source and evidence scope recorded below**.
- Independent human/expert review or separately launched reviewer agents: **NOT PERFORMED**.

These decisions do not certify the industrial hypothesis, product performance, legal compliance, protocol conformance or market demand. They are not GitHub review submissions under separate identities. No scheduler or background review process was started.

## Exact approved artifact

Both final roles approved the same manuscript bytes:

- Manuscript commit: `27834b2aaa1bfc697c799797946115d4365fb89e`.
- Git content blob: `19e8aa29d38316aa306f15147e4b028ad73bfe9c`.
- SHA-256 of UTF-8 file bytes: `0bae152ff20f37f02fb7ad922abacba5b5bc4e5cc9186f91374bac5ec2120916`.
- Size: 73,904 bytes; 13 numbered substantive chapters; 18 footnote definitions.
- [Immutable reviewed manuscript](https://github.com/Jongtae/agentos/blob/27834b2aaa1bfc697c799797946115d4365fb89e/docs/whitepapers/whose-agent.ko.md).

Approval binds to that artifact, not to whatever a branch later contains. A substantive manuscript or source change requires reconsidering the affected gate. GitHub PR state and required Checks remain the source of truth for repository execution; this record is an editorial audit, not a duplicate CI ledger.

## Provenance and historical boundary

The owner supplied the industrial thesis, examples and direction through a design discussion. The assistant integrated and edited the Korean manuscript. The first preserved version, v0.2, was published through [#1043](https://github.com/Jongtae/agentos/issues/1043) / [#1044](https://github.com/Jongtae/agentos/pull/1044), at baseline commit `435470d4f8a1b7a73ab9bd5e44e61aea6b2d6ef5`.

Its manuscript blob was `2b935c2b81816f6aae0f4dc7ccf035edfea2f316`. Its [original review plan](https://github.com/Jongtae/agentos/blob/435470d4f8a1b7a73ab9bd5e44e61aea6b2d6ef5/docs/whitepapers/review-plan.en.md) correctly said the ten rounds were unperformed then. The later owner instruction authorized preserving that draft on main, not retroactive expert approval. This follow-up actually performs the role-based review; it does not rewrite that history.

Only the intended whitepaper and public references are published. No raw private conversation, unrelated personal material, credentials, attachment dump or private-repository content is included. The already-public Presence research remains a historical report dated 2026-09-23, not a fresh runtime audit. Its observed blob is `60d4e5e52350f54d2887eb81ab7c608d0fe8bf8a`; v0.3 pins its repository citation to the baseline commit.

This document is English editorial governance for a Korean source manuscript. Neither it nor the manuscript changes `delivery-plan.yaml`, current pilot policy, canonical English implementation contracts, runtime behavior, permissions, dependencies or development priorities. Proposed product boundaries are not an implementation activation.

## Roles and acceptance criteria

All roles below were applied by the **same assistant**. Role separation structures criticism; it does not create reviewer independence or professional credentials. No separate model-setting change is asserted.

| Role | Review obligation |
|---|---|
| Developmental editor | Preserve the owner's industrial/business scope, reader, argument and depth; do not turn the paper into a feature backlog. |
| Industry-history reviewer | Distinguish functional separation from profit/control migration, and analogy from a universal forecast. |
| Agent architecture reviewer | Define model, worker and operating environment; test capability loss and continuity during a model change. |
| Memory/portability reviewer | Distinguish stored data, meaning, use and permission; test conflicting imports and rollback. |
| HCI/collaboration reviewer | Separate Presence from performance theatre; consider intervention, repair and conflicting edits. |
| Security/evidence reviewer | Distinguish request, observation, service attestation and registration proof; test completeness, ordering, attribution, key trust and privacy. |
| Business-model reviewer | Examine payer, incentives, adoption friction, provider cost and user effort without inventing market evidence. |
| Skeptical reviewer | Test the strongest alternative explanations and define comparisons that could weaken the thesis. |
| Final editor | Judge coherence, readability, substantive counterarguments and fidelity on the exact candidate; style cannot waive factual blockers. |
| Final verifier | Compare factual propositions with sources and periods, check evidence labels and reconfirm the editor's unchanged artifact; no unperformed experiment or independent approval claim. |

## Ten executed passes and revision identity

The first input is the v0.2 blob above. Each subsequent input is the preceding row's output. These are content identifiers for local snapshots, not claims that ten separate GitHub commits were made. Local full snapshots and unified diffs were saved as the passes ran. Findings below are concise editorial conclusions, not private reasoning transcripts. High/medium/low describe manuscript ambiguity, not discovered runtime vulnerabilities.

| Round | Lens | Result | Output Git content blob |
|---|---|---|---|
| 01 | Developmental editing | Reader and claim map added | `528afe1bf35676eb8cfd11983947e66ad4340015` |
| 02 | Industry history | Conditional separation mechanism added | `62ee255ecc2cdfd44f1c0235199ccb60d19cb783` |
| 03 | Architecture | Operating-environment and capability-gap boundaries clarified | `10ba6f377fde82ecdeebaedd9dd505321702e7a6` |
| 04 | Memory portability | Inspectable scope, conflict report and reversible transfer added | `fc9e48d799419c5748433e09fe652619da59b663` |
| 05 | HCI/collaboration | Useful autonomy and concurrent-edit handling clarified | `34476129d5f671d686c1dac1a10323c4f2ebcea2` |
| 06 | Security/evidence | Coverage, selected signing, external comparison and key trust clarified | `73fed22f6df352cdd486856368dfd13f78f0de01` |
| 07 | Business | Outcome-cost denominator and staged adoption added | `e9326643e27331404252d883fdaf65063b2dbf2a` |
| 08 | Skeptical cross-review | Overlapping scenarios, third-party limits and fair comparison added | `74071046f409f9610d6bb769dae44f36fa4d3d99` |
| 09 | Final editing | Summary tightened, v0.3 labels and pinned source prepared | `19e8aa29d38316aa306f15147e4b028ad73bfe9c` |
| 10 | Final verification and editor reconfirmation | No change needed within stated scope; both role gates approved same bytes | `19e8aa29d38316aa306f15147e4b028ad73bfe9c` |

### Findings, revisions and dispositions

| Finding | Severity / location | Finding and actual disposition |
|---|---|---|
| R01-01 | Medium; after summary | Audience and claim types were implicit. Added a reader map separating sourced cases, industrial hypotheses and design proposals. **Resolved.** |
| R02-01 | Medium; new 1.3 | Bundling could imply all network suppliers necessarily lost power. Distinguished online-service/network/application roles and functional versus economic change; added interface, switching and incentive conditions. **Resolved.** |
| R03-01 | Medium; chapter 2 | AgentOS could mean a replacement host OS and worker a separate assistant identity. Defined a logical operating environment and execution worker, preserving inspectable execution. **Resolved.** |
| R03-02 | High; 5.1 | Continuity did not explain a less-capable replacement model. Added capability-gap disclosure and viable alternatives while retaining state and user control; no output-equivalence promise. **Resolved.** |
| R04-01 | High; 4.1 | Memory portability could imply extraction of hidden training effects or automatic semantic fidelity. Limited the proposal to inspectable stored information and observable use after import. **Resolved.** |
| R04-02 | High; 4.3 | Import conflict, rollback and authority were underspecified. Added imported/excluded/conflicting/unknown categories, correction handling, no authority from imported text, no secrets in the memory bundle and reversible confirmation. **Resolved.** |
| R05-01 | Medium; 5.2 | Presence could be mistaken for more notifications or repeated approval. Cited the research's optional proactivity and preserved useful autonomy inside prior delegation. **Resolved.** |
| R05-02 | High; 6.2 | Shared state did not explain concurrent edits. Added a deletion-versus-quantity-change example and service-version/condition checks or re-observation, without blindly replaying stale plans. **Resolved as a proposal, not implemented proof.** |
| R06-01 | High; 7.2 | Two authentic events do not prove complete history or global ordering. Added target/time/coverage bounds and qualified explanation when completeness is unknown. **Resolved.** |
| R06-02 | Medium; 7.3 | HTTP integrity wording could imply all components are covered. Changed it to selected components, consistent with RFC 9421; business success remains separately defined. **Resolved.** |
| R06-03 | High; 7.4–7.5 | Hash chains and portable signatures lacked an explicit trust/retention boundary. Added independently retained comparison roots, original signed content, issuer/key linkage, verification time and key-compromise context; unknown revalidation is not current-state proof. **Resolved.** |
| R07-01 | Medium; 10.3 | Successful-outcome cost could hide failure/cancellation or zero successes. Included all attempt resources, a common observation window, success rate and separate user-effort valuation. **Resolved as proposed measurement.** |
| R07-02 | High; new 10.4 | Opportunity claims lacked an adoption path and merchant incentive counterweight. Added incremental value tests and participation costs instead of assuming universal cooperation. **Resolved; economics remain unmeasured.** |
| R08-01 | Medium; 11.4 | Three scenarios could appear mutually exclusive. Stated that an integrated product can also support user-controlled portability. **Resolved.** |
| R08-02 | High; new 11.5 | User control could imply authority over another service. Bounded it by actual access/delegation, allowed alternatives and unknown states, and the business consequences of persistent constraints. **Resolved.** |
| R08-03 | High; chapter 13 | Evaluation could credit architecture for model/task differences. Added controlled conditions, a useful integrated baseline, held-out cases, separate participant costs and predeclared criteria. **Resolved as an evaluation proposal.** |
| R09-01 | Low; summary | Opening and summary repeated the same question across several paragraphs. Condensed the summary lead while retaining Jarvis and all 13 chapters. **Resolved.** |
| R09-02 | Medium; header/references | Old draft labels and a mutable research citation did not identify the reviewed candidate. Added truthful v0.3 self-review labels, pinned historical research and specified source scope. **Resolved.** |
| R10-01 | Verification; whole candidate | Compared material factual propositions to the retrieved source set, inspected the cumulative revision and ran structural assertions. No additional factual blocker found within this scope. **No-change decision; preserve round 09 bytes.** |
| R10-02 | Decision; same candidate | Final editor reconfirmed the narrative and final verifier confirmed evidence boundaries on the unchanged artifact. **Both role-based gates approved; no independent review asserted.** |

## Claim-to-source audit

Public primary/official pages were retrieved on 2026-10-06; repository documents were read through the GitHub connector. The table identifies the material factual claim groups and relevant passages, not just working URLs. All 18 manuscript footnote keys are covered. Inferences and proposed requirements added in rounds 1–8 are labeled as such and are not attributed to the sources as measured findings.

| Footnote / manuscript location | Source and checked passage | What it supports; what it does not |
|---|---|---|
| compuserve / 1.1 | [Computer History Museum, CompuServe](https://www.computerhistory.org/revolution/the-web/20/400/2337), descriptive paragraph | Bundled user content, commercial services, email/chat; not the whole Korean market or quantified migration of profits. |
| cern / 1.1 | [CERN, The birth of the Web](https://home.cern/science/computing/the-birth-of-the-web/), release paragraph | 30 April 1993 public-domain release and later open licence; not proof of the AI thesis. |
| rfc3724 / summary, 1.1–1.3 | [RFC 3724](https://www.rfc-editor.org/rfc/rfc3724.html), March 2004, 4.1.1 and user-choice discussion | Informational end-to-end architecture and endpoint innovation; not a measured industry-power ranking. |
| apple2008 / summary, 1.2 | [Apple announcement](https://www.apple.com/newsroom/2008/03/06Apple-Announces-iPhone-2-0-Software-Beta/), 6 March 2008, SDK/distribution paragraphs | Developer access plus then-announced approval/exclusive distribution; not today's worldwide app policy. |
| cma2022 / 1.2 | [CMA announcement](https://www.gov.uk/government/news/cma-plans-market-investigation-into-mobile-browsers-and-cloud-gaming), 10 June 2022 | The regulator's dated mobile-ecosystem findings; retained as attributed UK-period evidence, not a present global assessment. |
| claude-memory / 4.2 | [Claude official help](https://support.claude.com/en/articles/12123587-import-and-export-your-memory-from-claude), import/export instructions and experimental limitation | Import/export exists and incorporation can fail; not complete context, task or authority migration. |
| presence / 5, 12 | [Pinned public research](https://github.com/Jongtae/agentos/blob/435470d4f8a1b7a73ab9bd5e44e61aea6b2d6ef5/docs/research/presence-and-settings-ux.ko.md), definition, Memory/Availability, optional proactivity, anti-patterns and reported dogfooding | What the 2026-09-23 report describes and proposes; not a fresh code audit, replicated HCI study or shipped capability. Secondary literature inside that report was not independently revalidated. |
| constitution / 3 | [Development Constitution](../development-constitution.en.md), status and development sequence; [AGENTS.md](../../AGENTS.md) | Canonical implementation/governance authority remains separate. No runtime activation or policy modification follows from the paper. |
| ucp / 6.2 | [UCP official documentation](https://ucp.dev/), capabilities overview | Catalog/cart/account-linking/checkout/order scope; no named retailer adoption, interoperability result or collaboration-quality claim. |
| vc / summary, 7.1 | [W3C VC Data Model 2.0](https://www.w3.org/TR/vc-data-model-2.0/), introduction and verification definition | Verifiability is not truth of claims; signatures are not business-quality or completeness guarantees. |
| outbox / 7.3 | [AWS Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html), implementation/issues sections | State/event same-database transaction and duplicate-handling need; not distributed exactly-once or issuer honesty. |
| http-signatures / 7.3 | [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html), February 2024, abstract and 7.2.1 | Integrity over covered components and insufficient-coverage risk; not all message content by default or workflow success. |
| nist-blockchain / 7.4 | [NIST Blockchain](https://www.nist.gov/blockchain), overview | Shared tamper-evident/resistant ledger characterization; not the truth of submitted business assertions. |
| ct / 7.4 | [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html), December 2021, proof sections and 11.3 | Merkle inclusion/consistency and detection of inconsistent views through comparison; not a cart-receipt format or a complete gossip implementation. |
| scitt / summary, 7.4–7.5 | [RFC 9943](https://www.rfc-editor.org/rfc/rfc9943.html), June 2026, 7.1, 8, 9.1–9.4 | Signed statements/registration, key/issuer trust, metadata privacy, ordering, false claims, selective participation and key compromise; not Agent business-completion semantics or mandatory blockchain. |
| skills / 8 | [Agent Skills overview](https://agentskills.io/home), format overview | SKILL.md plus supporting scripts/resources; not skill quality, maintenance success or revenue. |
| mcp / 9 | [MCP architecture, 2026-07-28](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture), scope paragraph | Context exchange does not prescribe host LLM use or context management; not personal-Agent ownership/portability certification. |
| a2a / 9 | [A2A official overview](https://a2a-protocol.org/latest/), purpose/features | Communication among heterogeneous agents; not user's ownership, complete migration or truth of task results. |

This was an author-performed material-claim audit, not independent peer review or a complete errata, security or conformance audit of the referenced standards. Mutable pages can change after the access date. New product claims must be checked again rather than inferred from this record.

## Final decisions on the same candidate

**Final editor role — APPROVED.** The Jarvis question leads to the actual industrial thesis. The historical analogy has explicit limits; memory, intelligence, Presence, collaboration, evidence and business form one argument. The revised text includes adoption friction, strong alternative scenarios and testable next questions without reducing the owner's thesis to implementation details. All 13 numbered chapters remain. Approval is for a vision/strategy discussion, not proof that its preferred structure wins.

**Final verifier role — APPROVED within scope.** The cited material facts have the relevant sources and periods above. Hypothetical shopping examples, reported historical project observations, original proposals and future evaluations remain distinct. Signatures, log inclusion, truth, completeness, actor attribution and current state are not conflated. No unperformed independent review, empirical test or live capability is represented as completed. No unresolved factual blocker was identified in this audit; accepted research limitations remain explicit.

Both decisions apply to blob `19e8aa29d38316aa306f15147e4b028ad73bfe9c`. Round 10's editor reconfirmation used exactly the same bytes as its verifier review. The GitHub write returned that same content SHA. These are two role judgments by one assistant, not two independent authorities.

## Observed checks and limits

The locally reconstructed v0.2 file matched the GitHub blob exactly before revision. Each round saved an input/output identity, concrete findings, a full output snapshot and a unified diff; round 10's diff is intentionally empty. Local assertions confirmed consecutive chapter numbers 1–13, 18 unique footnote definitions, no unresolved or unused footnote keys, absence of conversation-only citation markers/placeholders, UTF-8/LF formatting and the final blob/SHA-256 above.

These checks do not constitute automated verification of every external link, a full Markdown renderer test, complete repository tests or a live AgentOS evaluation. A public git checkout attempt failed because the container could not resolve github.com; the live GitHub connector was used instead. Required exact-head GitHub validation remains a merge gate and its observed outcome belongs in the PR discussion, not as an unobserved claim here.

## Remaining work, deliberately not relabeled complete

Independent human/expert or separate-agent review, empirical portability/collaboration studies, representative user research, economic validation, protocol implementation/conformance, full RFC errata review, English manuscript translation and PDF layout are not performed by these editorial passes. They are not silently activated. The ten-role editorial task is complete within its disclosed method; these limitations prevent stronger claims, not preservation of a clearly labeled strategy whitepaper.
