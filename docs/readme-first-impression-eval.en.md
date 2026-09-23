# README first-impression evaluation

This is a lightweight comprehension check for the public README, not a model-quality benchmark and not live user research.

## Goal

A first-time reader should be able to explain Personal AgentOS without knowing the terms Kernel, BDI, Grant or AgentPackage, and should want to try it.

After reading only the README (hero, "Install", "Then try these", "The settings you will need"), the reader should recover this mental model:

> My own AI assistant, running on my own machine, that can reach the files, mail, calendar, memory and public pages I allow. I pick the model. It stops and asks before anything consequential, keeps the result so I can continue later, and reports what actually happened rather than what the model claims.

The README deliberately stops after the settings; the evidence table, the product-direction scene, the comparison and the internals live on [docs/product-status.en.md](product-status.en.md) (Korean mirror: product-status.ko.md). A reader who follows the "More" links should understand that the household-purchase scene there is product direction, not a claim that autonomous checkout ships today.

## Synthetic first-reader prompt

Give a fresh reviewer only the README. Do not provide repository architecture or issue context. Ask:

1. What is this product, in one or two ordinary sentences?
2. Why would you want it instead of a hosted assistant such as the ones bundled with a chat app or a phone?
3. Give two examples of things you think a person could hand to it today.
4. How is it different from a personal task/knowledge workspace?
5. Is it real software today, a future vision, or both? What can you try right now?
6. Who controls data access and consequential actions?
7. Which part of what you read is clearly product direction rather than a current capability?
8. What terms or claims felt confusing, overly technical or stronger than the evidence?
9. Does this page merely make sense, or does it make the product feel worth trying? Name the weakest section.

Run the same exercise against EN/KO/JA/ZH-CN. Natural localized wording may differ; the recovered mental model should not.

## Pass criteria

- The answer starts from **own machine / own data / delegate real work**, not "AI kernel", "agent marketplace", "BDI framework" or development automation.
- The reviewer names a difference from a hosted assistant that is about where it runs and who decides, not about model quality.
- At least one example is an everyday-life task, and every example given is one of the five scenes shown as available today.
- The reviewer identifies owner permission/approval as a product distinction.
- The reviewer does not infer that autonomous purchasing or checkout is currently supported.
- The reviewer can distinguish the illustrative errand scene from the scenes available today.
- The reviewer understands that the model may be remote (local-first is not local-only).
- All four locales recover the same product promise.

## Failure signatures

Treat the copy as needing revision if a reviewer primarily describes the project as:

- a local LLM launcher;
- an agent marketplace;
- a multi-agent/swarm framework;
- a BDI implementation;
- a coding-agent harness;
- an autonomous purchasing bot;
- a fully offline or fully private assistant.

Those are either implementation details, future ecosystem directions or incorrect capability inferences.

## Evidence boundary

The README is documentation. The scenes shown as available today cite the synthetic first-user audit in #472, which used injected transports and explicitly did not run live providers. The "honest results" claim is scoped to merged behaviour (#476, #488) with its open remainder linked (#489, #490, #493, #494).

The parity verifier provides deterministic structural evidence only. It does not prove that a human finds the positioning attractive or clear.

Before a README redesign issue is closed, use the prompt above for an independent first-reader review of the PR. Record the reviewer, exactly which README revision was shown, the recovered mental model, and any blocking ambiguity. An implementer's own review is not independent review.
