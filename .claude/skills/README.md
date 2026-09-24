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

## Reviewed but not adopted

- `nextlevelbuilder/ui-ux-pro-max-skill` (`dcc40ff`, MIT): large Python/CSV dataset
  weighted toward landing pages and styles; its form rules largely overlap the Vercel
  guidelines. Deferred.
