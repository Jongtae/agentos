# Product validation gate

Run this gate from a clean product checkout before claiming that a release
meets the maintained Personal AgentOS v1 baseline:

```sh
python3 scripts/product_validate.py --unit --homebrew \
  --output /tmp/agentos-product-validation.json \
  --markdown /tmp/agentos-product-validation.md
```

The report distinguishes four states: `passed` has direct evidence, `failed`
needs a repair issue, `blocked` needs an unavailable external prerequisite,
and `gap` is an intentional post-v1 product-vision item. Reports contain no
API keys, Telegram tokens, document contents, or model transcripts.

Use existing credentials for the live checks only when the owner is present:

```sh
python3 scripts/product_validate.py --live-model --live-telegram
```

`--live-telegram` records the required paired-account acceptance check. The
maintainer sends a new Telegram request after restarting AgentOS and verifies
the shared web history and the delivery trace; no bot token is printed or
stored in the report.

The gate is a maintained v1 release decision aid, not the Hub v2 product gate. Hub v2 consumer installation, subscription engines, owner-created BotFather personal bots, and context capture each require their own named acceptance evidence.
