# Adopted development skills

These are **development aids** for coding assistants working on this repository
(DEV-UI-SKILLS-01 #548). They are not part of the Personal AgentOS product runtime,
do not grant authority, and are subordinate to `AGENTS.md`, the Development
Constitution, `src/personal_agent/web/AGENTS.md` and the
[Presence Experience Contract](../../docs/presence-experience-contract.en.md).
Where a skill conflicts with those, the repository contract wins.

Skill text is instruction content, so every skill here is vendored at an exact
upstream commit and reviewed before merge. Do not replace a pinned copy with a live
fetch. To update, open a new issue/PR with the new commit, the upstream diff and a
licence check.

| Skill | Upstream | Commit (date) | Licence | Local changes |
| --- | --- | --- | --- | --- |
| `web-interface-guidelines` | [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) `command.md` | `e3d624baaf29dc1fc645aff3e38f03e564d2d6b1` (2026-08-17) | MIT | Rules kept verbatim as `upstream-command.md`; AgentOS-authored `SKILL.md` wrapper adds the review order and non-applicable rules |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) `skills/frontend-design/` | `34040c9c568585f6929bedeaad110ad08f079624` (2026-09-10) | Apache-2.0 | None (verbatim) |

## Why not the upstream install paths

- `vercel-labs/agent-skills` `web-design-guidelines` (`063bee9`) tells the assistant to
  fetch the rules from `main` before every review, so the instructions can change
  without review (conflicts with Constitution C7).
- `web-interface-guidelines/install.sh` downloads from `main` into `~/.claude`.

## Applying `frontend-design` to this product

It is written for new, distinctive designs. For the local web management utility,
use its typography, restraint, self-critique and writing guidance. Do not add a hero,
dashboard panel, marketing copy or decoration that `src/personal_agent/web/AGENTS.md`
excludes.

## Immutable content review — #1026

The [frontend-design change-impact review](../../docs/upstream-knowledge-review.en.md)
records exact source/file/tree identities, the genuine historical revision diff,
licence conditions, acceptance examples, and recovery evidence. The active pin
above remains unchanged. The local interpretation is `frontend-design-review-v1`;
the upstream files remain verbatim. The historical source is preserved under
[`tests/fixtures/skills/frontend-design/`](../../tests/fixtures/skills/frontend-design/).

The actual consumer is the coding-assistant UI review workflow required by
[`src/personal_agent/web/AGENTS.md`](../../src/personal_agent/web/AGENTS.md).
Loading these bytes through a temporary product store is compatibility evidence;
it does not install this development aid into the owner runtime or measure design
quality.

Discovery stays manual: `.github/dependabot.yml` covers `uv` and GitHub Actions,
not copied Markdown directories. Before an update, a contributor follows the
review's disposable-clone commands to resolve upstream main once, then compares
the active pin to that immutable commit. Record unchanged bytes as unchanged.
For changed content, review every diff, source/licence/notice change and local
contract conflict, preserve historical bytes, and run the existing loader and
focused compatibility tests in the issue worktree. Submit the normal issue/PR
with the immutable targets and decisions. Promotion occurs only after the
repository's review and required exact-head CI; no live fetch or bot pin change
approves new instructions.

## Reviewed but not adopted

- `nextlevelbuilder/ui-ux-pro-max-skill` (`dcc40ff`, MIT): large Python/CSV dataset
  weighted toward landing pages and styles; its form rules largely overlap the Vercel
  guidelines. Deferred.
