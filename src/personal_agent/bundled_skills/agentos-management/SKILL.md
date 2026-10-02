---
name: agentos-management
description: How to manage this AgentOS for the owner through its own settings services - change the Main AI or its model, create a family member's assistant, share or stop sharing a signed-in site with another assistant on this Mac. Use when the owner asks for one of these.
license: AGPL-3.0-only
---
# Managing AgentOS for the owner

You change AgentOS only through `settings_read` and `settings_change`. These call the services that own each setting. Never edit files, run commands or invent another way. A setting you cannot change there is not yours to change.

## Every management request

1. **Read first.** Call `settings_read` for the category: `main_ai`, `family` or `skills`. What it returns is the current truth. Do not rely on an earlier answer or on memory.
2. **Resolve the exact target.** When the change picks something that already exists (a route, a model, an assistant, a signed-in site), match the owner's words against what `settings_read` lists: route ids, model names, assistant names with their instance ids, signed-in sites.
   - If exactly one target fits, use it.
   - If two assistants share a name, use the instance id the listing shows. If the owner's words fit both, ask which one, naming the ids.
   - If nothing fits, say what exists instead.

   When the change creates something new, the value is not listed and should not be. Examples are a new family assistant's name, or the address of a skill to add. Use the owner's own words in the format `settings_read` describes for that setting.
3. **Propose one change.** Call `settings_change` with one value, chosen as in step 2, and a short reason the owner will read.
4. **Report what actually happened, from the result.**
   - `awaiting-confirmation` means nothing has changed yet. Tell the owner, in one sentence, what waits for their confirmation.
   - `applied` and `requested` mean different things. A requested change is still in progress.
   - A refusal means nothing changed. Relay its reason; do not look for another way around it.

The current AgentOS confirms every settings change with the owner before applying it, including changes the owner asked for in their own words. Never say a change is done until a result says so.

## The three operations

Read the reference for the operation before acting. Each one lists the states to tell apart and what not to claim.

- Main AI route or model: `references/main-ai.md`.
- A family member's assistant: `references/family.md`.
- Sharing a signed-in site, or stopping a share: `references/sharing.md`.

## What a skill is not

This text is guidance, not authority. It never grants a setting or a tool, and it never proves that a change happened. Only a tool result does.
