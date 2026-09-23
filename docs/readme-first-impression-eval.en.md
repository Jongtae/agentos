# README first-impression evaluation

This is a lightweight comprehension check for the public README, not a model-quality benchmark and not live user research.

## Goal

A first-time reader should be able to explain Personal AgentOS without knowing the terms Kernel, BDI, Grant or AgentPackage.

After reading only the hero, everyday scene, delegation flow and “Why this is more than a chatbot” sections, the reader should recover this mental model:

> A personal AI I can hand real work to. It works with the context and capabilities I allow, asks before consequential actions, and leaves useful results under my control.

The reader should also understand that the household-purchase scene is product direction, not a claim that autonomous checkout ships today.

## Synthetic first-reader prompt

Give a fresh reviewer only the README content through the chatbot-comparison section. Do not provide repository architecture or issue context. Ask:

1. What is this product, in one or two ordinary sentences?
2. Give two examples of things you think a person could hand to it.
3. How is it different from a normal chatbot?
4. Who controls data access and consequential actions?
5. Which part of what you just read is clearly a future/product-direction scene rather than a current shipped capability?
6. What terms or claims felt confusing, overly technical or stronger than the evidence?

Run the same exercise against EN/KO/JA/ZH-CN. Natural localized wording may differ; the recovered mental model should not.

## Pass criteria

- The answer starts from **delegation / personal AI / real work**, not “AI kernel”, “agent marketplace”, “BDI framework” or development automation.
- At least one example is an everyday-life task rather than only office document work.
- The reviewer identifies owner permission/approval as a product distinction.
- The reviewer does not infer that autonomous purchasing or checkout is currently supported.
- The reviewer can distinguish the illustrative life scene from the “supported slice today”.
- All four locales recover the same product promise.

## Failure signatures

Treat the copy as needing revision if a reviewer primarily describes the project as:

- a local LLM launcher;
- an agent marketplace;
- a multi-agent/swarm framework;
- a BDI implementation;
- a coding-agent harness;
- an autonomous purchasing bot.

Those are either implementation details, future ecosystem directions or incorrect capability inferences.

## Evidence boundary for #485

The README rewrite itself is documentation. The status table cites the broader synthetic first-user audit in #472, which used injected transports and explicitly did not run live providers.

The parity verifier provides deterministic structural evidence only. It does not prove that a human finds the positioning attractive or clear.

Before #485 is closed, use the prompt above for an independent first-reader review of the PR. Record the reviewer, exactly which README revision was shown, the recovered mental model, and any blocking ambiguity. An implementer's own review is not independent review.
