# AgentOS reference skills

This folder holds the reference skills AgentOS publishes. Each one is an [Agent Skills](https://agentskills.io/specification) folder, licensed AGPL-3.0-only like the rest of the repository.

They are not bundled into AgentOS. The owner adds one in conversation ("장보기 스킬 추가해줘"). AgentOS then pins it to an exact commit and checks it like any external skill before installing it, and each skill can be removed on its own (Constitution C16, #974).

| Skill | What it is |
| --- | --- |
| `shopping-cart` | A method for changing an online cart safely: exact product, quantity meaning, change only what was asked, read the cart back |
| `emart-ssg` | Site know-how for Emart mall on SSG.COM, from redacted AgentOS observations. Use it with `shopping-cart` |

Site hints are observations, not guarantees. Pages change, and the method tells the AI to check each hint on the page.
