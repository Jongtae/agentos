# Skill fixtures

`internal-comms/` is a byte-for-byte copy of `skills/internal-comms` from
[anthropics/skills](https://github.com/anthropics/skills) at commit
`8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`. It is licensed under Apache-2.0;
see its own `LICENSE.txt`. It was not authored for AgentOS.
`tests/test_skill_supply.py` checks the files against the pinned sha256 digests
(SKILL-SUPPLY-02 #961; decision record #960, section 7).

## frontend-design historical revision — #1026

`frontend-design/2235be7c60b551f5de82ade908fd3816455afcda/frontend-design/`
is a byte-for-byte copy of the two-file `skills/frontend-design` directory at
[anthropics/skills@2235be7c60b551f5de82ade908fd3816455afcda](https://github.com/anthropics/skills/tree/2235be7c60b551f5de82ade908fd3816455afcda/skills/frontend-design).
It was fetched from immutable raw GitHub URLs on 2026-10-06, not authored for
AgentOS. Apache-2.0 applies; the complete upstream `LICENSE.txt` is preserved.
No source byte or newline was adapted. The upstream folder contains no separate
NOTICE; the repository third-party register covers components absent from this
two-file dependency, as recorded in the licence review below.

| File | SHA-256 |
| --- | --- |
| `SKILL.md` | `1608ea77fbb6fc30d13a97d12cfa8ebf31358d40f0dd97beed24829d6b3f45dd` |
| `LICENSE.txt` | `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594` |

The existing loader's tree digest is
`393d62282755428dec622372ebbc22c10c5925516c9d6c1aa2da7a5d4274ba8f`.
The candidate is legitimate upstream commit
`41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`; its selected bytes are already the
verbatim `.claude/skills/frontend-design` copy pinned at
`34040c9c568585f6929bedeaad110ad08f079624`. Tests reuse that copy instead of
duplicating the accepted content. Full identities, genuine semantic changes,
notice conditions and `frontend-design-review-v1` local interpretation are in
[`docs/upstream-knowledge-review.en.md`](../../../docs/upstream-knowledge-review.en.md).

`tests/test_upstream_knowledge.py` exercises these sources through the existing
parser, library, binding, MCP boundary and injected worker in disposable stores.
This is loading/resource compatibility evidence. The actual operational consumer
remains the repository development workflow; it is not owner runtime installation
or model design-quality evidence. Unsupported-script variants are synthetic
negative data and never represented as legitimate upstream revisions.
