# Security Notes

AgentOS keeps public code and public images secret-free.

Never commit:

- `.env`
- Telegram bot tokens
- OpenAI or other provider API keys
- generated ISO artifacts
- runtime workspace artifacts containing local state
- real conversation logs

Runtime setup should write user-provided secrets to local runtime env files, not
to committed artifacts.

Common runtime variables:

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

## Public Repo Rule

The public repository should contain source, docs, tests, and sanitized examples.
It should not contain personal workspace state, real setup artifacts, release
ISOs, VM logs, or screenshots that expose credentials, private IPs, private
hosts, email addresses, tokens, or real conversations.
