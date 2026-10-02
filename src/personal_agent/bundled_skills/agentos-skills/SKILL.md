---
name: agentos-skills
description: How skills work in this AgentOS - what a skill is, how to add one from a public GitHub folder, turn skills on or off and remove one, all through settings_change, and which reviewed reference skills (such as shopping) can be added. Use when the owner asks about skills, or a request needs a skill that is not installed.
license: AGPL-3.0-only
---
# Skills in AgentOS

A skill is optional know-how: written instructions plus packaged text files. It is never a tool or a permission. Every action still runs through the tools this Work has, under their own checks, and a skill's text never proves that something happened. Only an observed tool result does.

## What the owner can ask

All changes go through `settings_change` with category `skills`. AgentOS then asks the owner to confirm, exactly like any other setting.

- **Turn skills on or off:** setting `enabled`, value `on` or `off`. Off, no Work sees a skill.
- **Add a skill:** setting `add`, value is the GitHub folder address of the skill: `https://github.com/<owner>/<repo>/tree/<branch, tag or commit>/<folder>`. AgentOS pins the exact commit, downloads only that folder, and checks it before installing.
- **Remove a skill:** setting `remove`, value is the skill's name.

Read the current list with `settings_read` category `skills`.

## Reference skills AgentOS publishes

These are reviewed reference skills in the AgentOS repository. They are added like any other skill, pinned to the commit current when the owner confirms, and each can be removed on its own. Offer to add one when the owner's request needs it and it is not installed yet.

- **Shopping cart method:** `https://github.com/Jongtae/agentos/tree/main/skills/shopping-cart`. Changing an online cart safely: exact product, quantity meaning, read-back.
- **Emart mall on SSG.COM:** `https://github.com/Jongtae/agentos/tree/main/skills/emart-ssg`. Site know-how. Use it with the shopping cart method.

## What AgentOS refuses

Tell the owner the reason AgentOS gives. Do not look for a workaround.

- A skill that needs scripts, hooks or other executables. AgentOS runs no skill code.
- A skill whose licence cannot be recognised.
- A folder with links, oversized files or a malformed `SKILL.md`.
- A name that collides with an existing package.

## Using a skill in a Work

Load a skill with `skill_load` only when its description fits the request. The owner's request and constraints remain the goal. Read a packaged file with `skill_resource` only when the skill points to it.

A skill that is switched off, removed or updated while a Work runs stops that Work's further tool calls. Say so, and do not repeat an action whose result you have not observed.
