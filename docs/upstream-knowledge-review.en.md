# UPSTREAM-KNOWLEDGE-01 — frontend-design content review

Issue: [#1026](https://github.com/Jongtae/agentos/issues/1026), under
UPSTREAM-01 #1022. Selection: the U14 pilot in the
[upstream relationship map](upstream-relationship-map.en.md#selected-non-code-pilot-for-1026-frontend-design-revision-impact).
Review date: 2026-10-06. This record supplements the existing development-skill
source register; it creates no package registry or runtime source of truth.

## Consumer, outcome and reuse

The external author/source is [anthropics/skills](https://github.com/anthropics/skills),
path `skills/frontend-design/`. The actual operational consumer is a repository
coding assistant carrying out the UI reviews required by
[`src/personal_agent/web/AGENTS.md`](../src/personal_agent/web/AGENTS.md), using the
vendored [SKILL.md](../.claude/skills/frontend-design/SKILL.md) under
[the development-skill rules](../.claude/skills/README.md), AGENTS.md and the
[Presence contract](presence-experience-contract.en.md). This is development
evidence. It is outside the product runtime and does not grant tools or authority.

The owner outcome is an attributable, repeatable review of instruction changes
that might otherwise silently alter coding decisions. The worker AI interprets
the guidance; AgentOS does not script a design task or introduce a role router.
Disposable loading tests observe byte delivery and existing authority controls.
They do not demonstrate that an AI made better design decisions.

**Adopt** the existing Agent Skills representation, `inspect_skill`,
`SkillLibrary`, `SkillBinding`, `Capabilities`, `AgentOSMcpTools` and their source,
parser, resource, evidence and revocation paths. **Adapt** source/provenance and
focused test evidence. The internal search covered `skills.py`, `manifests.py`,
`bounded_execution.py`, `agent_runtime.py`, `test_skill_supply.py`, the
`.claude/skills` register and #960/#961's
[existing solutions review](skill-prep-01-interface-decision.en.md#4-existing-solutions-review--adopt--adapt--build).
Its PyYAML SafeLoader and framework comparison are reused; this delivery changes
neither parser requirements nor installed versions. Standard-library `hashlib`,
`json`, `tarfile`, temporary directories and `unittest` already cover the evidence
seam. The test uses the existing fake GitHub transport and injected worker,
avoiding a duplicate loader, dispatcher or semantic evaluator.

Dependabot selected by #1024 covers `uv` and GitHub Actions. It does not discover
this vendored directory. A Renovate custom manager can detect declared revisions,
but cannot decide copied-byte, local-contract or semantic compatibility. The
[existing updater decision](upstream-relationship-map.en.md#update-and-rejoin-ownership)
and the manual procedure below satisfy this boundary without adding a second
updater. The selected upstream repository remains maintained: inspected main
exists at the immutable observation below. This is commit/content discovery,
not an invented skill release stream. The source is text-only, platform-neutral,
Apache-2.0 content; it adds no installed dependency, executable, network authority
or canonical owner-state ownership.

## Immutable identities and local adaptation

The selected folder has exactly `SKILL.md` and `LICENSE.txt` in all four inspected
revisions. Direct immutable raw-file reads and GitHub directory inventories were
checked on 2026-10-06. The active copy remains the #548 pin. Both selected files
are byte-identical to the accepted content revision and observed upstream main.

| Purpose | Immutable revision | Local inspectable target |
| --- | --- | --- |
| Historical base | [`2235be7c60b551f5de82ade908fd3816455afcda`](https://github.com/anthropics/skills/tree/2235be7c60b551f5de82ade908fd3816455afcda/skills/frontend-design) | [historical fixture](../tests/fixtures/skills/frontend-design/2235be7c60b551f5de82ade908fd3816455afcda/frontend-design/SKILL.md) |
| Accepted content change | [`41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`](https://github.com/anthropics/skills/tree/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/frontend-design) | [current verbatim copy](../.claude/skills/frontend-design/SKILL.md), identical selected bytes |
| Active reviewed source pin | [`34040c9c568585f6929bedeaad110ad08f079624`](https://github.com/anthropics/skills/tree/34040c9c568585f6929bedeaad110ad08f079624/skills/frontend-design) | Existing development-skill register |
| Main observed on review date | [`683bc88e56f3e09ba94f7055977f3d3aa499f202`](https://github.com/anthropics/skills/tree/683bc88e56f3e09ba94f7055977f3d3aa499f202/skills/frontend-design) | Immutable observation only; no new pin or promotion |

| Bytes | SHA-256 |
| --- | --- |
| Historical `SKILL.md` (8,260 bytes) | `1608ea77fbb6fc30d13a97d12cfa8ebf31358d40f0dd97beed24829d6b3f45dd` |
| Accepted/current/observed `SKILL.md` (9,390 bytes) | `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3` |
| `LICENSE.txt`, all four revisions (10,174 bytes) | `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594` |
| Historical folder digest | `393d62282755428dec622372ebbc22c10c5925516c9d6c1aa2da7a5d4274ba8f` |
| Accepted/current/observed folder digest | `98e239f3f6a8e0a6391affe6ab96f1e7ed56072132bfd152ebcd761e79c45dc4` |

Folder digests use the existing `tree_digest`: SHA-256 of Python
`json.dumps({relative_path: file_sha256}, sort_keys=True).encode()`.
Local adaptation revision: **`frontend-design-review-v1`**. Source files have
zero byte modifications; adaptation consists of the existing subordinate-use
rules and the explicit interpretation decisions in this record. The temporary
`SkillLibrary.install` declaration retains its existing numeric `adaptation: 1`;
that loader value is separate from this development interpretation revision.

## Genuine revision impact and decisions

Compare [the two upstream commits](https://github.com/anthropics/skills/compare/2235be7c60b551f5de82ade908fd3816455afcda...41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f),
scoped to the selected folder. This is a retrospective review of the real change
already contained in the active pin. Unchanged main content is not a new update.
Both frontmatters retain the same name, description and licence reference; the
changed body is behavior-relevant even though both versions parse successfully.

| Changed guidance or assumption | Decision for this consumer | Expected observation / rejected interpretation |
| --- | --- | --- |
| Old text told the worker to choose and state a missing subject; new text asks it to confirm an unspecified subject with the client and gives contrasting audience examples. | Accept confirmation only when a material subject is actually missing. AgentOS's product, owner and management purpose are already canonical. | An assistant uses the known brief for a Settings fix; asking the owner to choose the product subject again is rejected. Examples illustrate audience dependence, not new user categories or product routing. |
| A prescribed display/body pairing and 2+ type roles become one or two families with explicit roles. | Accept the relaxed family count and intentional hierarchy under current UI constraints. | One existing family can serve headings and body. Fetching fonts, adding branding or changing authority to satisfy the prose is rejected. |
| New typography-book reference, sub-80-character default, serif spacing caveat and checks for accented words, all-caps and unnecessary labels. | Accept contextual readability and restraint guidance; keep language, accessibility and existing layout requirements controlling. | Review relevant text width and hierarchy. An automatic 80-character validator, forced removal of useful emphasis, or a new typography dependency is rejected. |
| Hero framing is reworded; structural numbering is clarified; the broad complexity-to-vision instruction is removed. | Retain useful semantic structure. Hero and marketing directions remain inapplicable to the management utility. | Numbered content represents a sequence. A hero, dashboard decoration or elaborate styling unsupported by the selected task is rejected. |
| Broad animation exploration becomes sparse unsolicited motion and motion that explains user actions. | Accept the narrowed scope with existing reduced-motion and accessibility rules. | Existing expand/confirm interactions may show state changes. Ambient effects, repeated entrances or motion added only for a distinctive appearance are rejected. |
| Three generic visual looks expand to five groups, adding card-kit and template-chrome examples; the real brief still wins. | Accept them as review prompts, not categorical bans or new design styles to implement. | Inspect whether a treatment serves actual content. Replacing legitimate cards or rewriting stable CSS solely because a style appears in the list is rejected. |
| Planning changes from a signature-focused paragraph to roles, layout/alignment and principles; advice about privately pursuing a delightful outcome is removed. | Accept proportionate planning and critique against the bounded brief. | A small UI fix remains a small fix. A fresh token framework, lengthy planning artifact or unrelated redesign is rejected. |
| Restraint adds visual accessibility and harmonious palettes, removes mandatory risk-taking language, and retains screenshot and memory/note suggestions. | Accept accessibility and measured critique. Suggestions invoke only tools and storage already permitted for the contribution. | Existing screenshot evidence may inform review. New owner-data persistence, canonical Memory writes or unrestricted screenshots are rejected. |
| Writing emphasizes clear names for new users, explicit actions, consistent outcomes and single-purpose text; placeholder copy is explicitly mentioned. | Accept clear, consistent copy under observed product behavior and locale parity. | A button accurately names its effect. Inventing readiness, data, functionality or successful outcomes as placeholder copy is rejected. |

No new tool requirement or approval semantic is introduced by the accepted
interpretation. Screenshots, notes, memory, typefaces and animation are advice,
not capability requests. Existing owner goals, independent tool availability,
Grants, payment approval, secrets, Memory authority and Evidence remain
controlling. No per-call ontology fetch or mandatory role route is selected.

Targeted acceptance examples: for an already specified local Settings correction,
use the known subject and existing typography while accurately describing the
observed action; reject an unnecessary subject-confirmation question, hero or
external font fetch. For a draft without a defined subject, request the missing
subject only when the answer changes the authorized design. These are human
interpretation criteria, not a claim that an injected worker makes those
judgments correctly. Live model quality needs a separate explicit scope/budget.

## Reference, mapping, validation and operational distinctions

| Relation | Exact consumer and version | Evidence limit |
| --- | --- | --- |
| Development instruction use | Coding-assistant review; active commit and local interpretation above | Actual repository instruction reference; no claim of a measured successful design task |
| Product compatibility | Existing parser/library/binding/MCP tools in disposable stores | Exact source/resource delivery with injected transport; no owner runtime installation |
| Agent Skills format | #960 reference `agentskills/agentskills@69ef37e9424c0a7ea9dd2293b559e43ec8176379`, `docs/specification.mdx`; parser consumes name, description, licence reference and body | Existing subset compatibility, not certification of every spec feature |
| Typography reference | *The Elements of Typographic Style*, named in the changed body | Upstream names no edition. Unversioned conceptual guidance; no imported book content, validation or executable rule |
| Mapping | Existing package source fields, file/tree digest and Work identity | Local provenance fields; no new RDF/PROV field mapping or competing owner-state model |
| Schema validation | Existing `parse_frontmatter`, `inspect_skill`, `manifests.validate_package` | Parser and semantic checks; this does not introduce JSON Schema validation against an ontology |
| Ontology reference/import | W3C PROV-O 2013-04-30, OWL 2 2012-12-11, SKOS 2009-08-18 and SHACL 2017-07-20 remain the U13 reference-only register | Selected skill uses none of their axioms; no RDF store, ontology import, SHACL validator or reasoner |
| Product/live operation | Absent in this delivery | No live model/account call, deployment, package application, automatic promotion or professional qualification claim |

## Licence and attribution

The source frontmatter points to its packaged `LICENSE.txt`, which contains the
Apache License 2.0 terms. The two-file selected directory was inspected at all
four immutable revisions. Both local versions preserve its complete identical
licence bytes and every original source byte. Attribution is to the externally
authored `anthropics/skills` dependency; this is not an AgentOS-authored skill.
The upstream selected folder contains no separate NOTICE file. The repository's
[historical third-party register](https://github.com/anthropics/skills/blob/2235be7c60b551f5de82ade908fd3816455afcda/THIRD_PARTY_NOTICES.md)
and accepted revision's register were inspected: their notices concern imageio,
FFmpeg, Pillow and font assets absent from this two-file dependency. No such
component or applicable notice is incorporated here.

Redistribution follows [Apache-2.0 section 4](https://www.apache.org/licenses/LICENSE-2.0):
include the licence and retain applicable notices; changed source files must
identify modifications and any applicable upstream NOTICE must accompany them.
Here the copied files are unmodified. The local interpretation record explicitly
identifies AgentOS's separate adaptation. Apache-2.0 source is retained under its
own terms alongside the repository's AGPL-3.0-only contributions; the copy does
not relicense upstream content or grant trademark permission. Public access and
the loader's licence recognizer alone are not redistribution review.

## Repeatable manual discovery and review

Run these contributor commands from the issue worktree. They clone public
upstream into a disposable directory and resolve the moving discovery head once.
Subsequent comparisons use immutable variables. They do not modify active skills
or the owner installation.

```sh
knowledge_review_dir=$(mktemp -d)
git clone --filter=blob:none --no-checkout https://github.com/anthropics/skills.git "$knowledge_review_dir/source"
knowledge_review_pin=34040c9c568585f6929bedeaad110ad08f079624
knowledge_review_base=2235be7c60b551f5de82ade908fd3816455afcda
knowledge_review_accepted=41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f
knowledge_review_candidate=$(git -C "$knowledge_review_dir/source" rev-parse refs/remotes/origin/main)
git -C "$knowledge_review_dir/source" log --format='%H %cs %s' "$knowledge_review_pin..$knowledge_review_candidate" -- skills/frontend-design
git -C "$knowledge_review_dir/source" diff "$knowledge_review_pin" "$knowledge_review_candidate" -- skills/frontend-design THIRD_PARTY_NOTICES.md
git -C "$knowledge_review_dir/source" diff "$knowledge_review_base" "$knowledge_review_accepted" -- skills/frontend-design
git -C "$knowledge_review_dir/source" ls-tree -r "$knowledge_review_candidate" -- skills/frontend-design
git -C "$knowledge_review_dir/source" show "$knowledge_review_candidate:skills/frontend-design/SKILL.md" > "$knowledge_review_dir/candidate-SKILL.md"
git -C "$knowledge_review_dir/source" show "$knowledge_review_candidate:skills/frontend-design/LICENSE.txt" > "$knowledge_review_dir/candidate-LICENSE.txt"
shasum -a 256 "$knowledge_review_dir/candidate-SKILL.md" "$knowledge_review_dir/candidate-LICENSE.txt"
cmp .claude/skills/frontend-design/SKILL.md "$knowledge_review_dir/candidate-SKILL.md"
cmp .claude/skills/frontend-design/LICENSE.txt "$knowledge_review_dir/candidate-LICENSE.txt"
PYTHONPATH=src python3 -m pytest -q tests/test_upstream_knowledge.py tests/test_skill_supply.py
```

Record the resolved candidate SHA, selected file inventory and hashes, any source
or licence change, the complete semantic diff and its accept/reject rationale in
the issue/PR. A nonzero `cmp` identifies changed bytes requiring review, not an
instruction to overwrite them. Preserve existing reviewed bytes before proposing
an accepted change. Use required exact-head CI and material-boundary review when
triggered. No result from these commands grants promotion authority. Future
network/source failure is reported as unavailable; it does not replace usable
content or prove unchanged upstream. The contributor may remove the disposable
clone after preserving the review evidence; historical source fixtures stay.

## Rejection, rollback and history

A semantic incompatibility is a contributor review disposition recorded with
immutable target and reason. It is not decided by keyword checks in AgentOS.
For example, an interpretation that demands a management-page hero is rejected
against the existing UI contract while the active reviewed pin stays usable.
No pending or rejected source can overwrite that pin merely because it parses.

For runtime compatibility evidence, the same-package unsupported-script candidate
is deliberately synthetic negative data, not a third upstream release. Existing
`SkillLibrary.install` stages and inspects before its atomic declaration replace;
refusal preserves the usable declaration, immutable folder and existing evidence.
Temporary source-outage and digest-mismatch tests likewise do not mutate the
approved upstream artifacts. The real old/current pair exercises update and
retention of historical content through the existing library. The unchanged
`test_skill_supply.py` lifecycle cases exercise withdrawal, restart and rollback.
Once a Work observes withdrawal,
`SkillBinding.revoked` and persisted failed events keep it stopped, including
after restart or restoring older content. A fresh Work may use the restored
version under current settings; an old Work gains no revived authority.

Historical source remains inspectable at the fixture and immutable upstream
links above; accepted source remains at the unchanged local copy, its immutable
upstream links and repository Git history. The development register and this
review preserve the reviewed identity even when a future active pin changes.
`internal-comms@8a1541c4` remains the existing product fixture; its test-only
`NEWER` value does not establish a real upstream content update.

## Requirement-to-evidence audit

This table names current artifacts and the validation needed for delivery.
GitHub PR/Checks supply authoritative execution status; this document does not
copy merge/check outcomes. Tests listed here must pass on the eventual exact
head before completion is claimed.

| #1026 acceptance | Artifact / evidence boundary |
| --- | --- |
| Real external dependency, immutable version, consumer, repeatable review | Identity table, development register, `web/AGENTS.md`, manual procedure |
| Genuine behavioral/semantic comparison with disposition | Preserved historical source, unchanged accepted source, real commit diff and decision table |
| Existing parser/loader/resource boundary and delivered content | `tests/test_upstream_knowledge.py`: real install/binding/MCP/injected-worker delivery; complete instruction/resource byte assertions |
| Reuse unchanged sources; no continued or revived Work authority | Existing `test_skill_supply.py` withdrawal/restart/rollback tests, retained `internal-comms` fixture; selected real-revision update/history checks |
| Separate reference/mapping/schema/ontology/development/product claims | Relation table; no ontology/runtime promotion claim |
| Attribution and redistribution conditions | Both original `LICENSE.txt` copies, exact hashes, inspected inventories and applicable-notice disposition |
| Incompatible update preserves usable version and reason/history | Existing staged install plus same-package unsupported-script refusal, semantic rejection disposition, immutable folders and persisted evidence checks |
| Required exact-head CI and triggered review | Required GitHub Checks and PR review on the delivery head; active bytes, runtime authority and supply trust are unchanged, so this bounded evidence change does not itself trigger mandatory independent authority review |

## Requested and observable model settings

Primary selection: current Codex/high as recorded in issue #1026; exact applied
receipt is unavailable. Phase A read-only research requested `gpt-6.1-sol/high`
for two delegated tasks; dispatch was accepted and actual applied settings were
not exposed. The updater follow-up reused an existing agent thread, without a
separately selectable or observable setting. Phase B assigned this document,
development register, provenance and historical fixture exclusively to the
existing same-config agent: requested `gpt-6.1-sol/high`, dispatch accepted,
applied setting unobservable. A second existing same-config agent exclusively
owned the dedicated test file with the same requested, accepted and
unobservable-applied record. The active skill files and product source receive
no changes. These records do not claim a tool-observed model switch or
model-quality evaluation.
