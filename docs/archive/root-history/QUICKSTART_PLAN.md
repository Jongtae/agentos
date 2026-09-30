# Self-hosted quickstart — current implementation slice

The first audience can run a small server. The product experience is launch → browser setup → model connection → personal chat → Telegram.

- Primary path: Python 3.12+ standard library, one launcher, no Docker/Kubernetes dependency.
- Optional container packaging uses the same application. Kubernetes remains a deployment option, not a prerequisite.
- First claim uses a one-time local bootstrap link. Set an administrator password in the browser.
- Configure Ollama, an OpenAI-compatible endpoint, or Anthropic through the UI. Keep secrets outside user conversation records.
- Web and one allowlisted private Telegram user share one personal conversation. Persist updates and avoid automatic retries of ambiguous external sends.
- Built-in bounded operations: save a personal note, list notes, summarize notes through the configured model. No autonomous shell or external business writes in this slice.
- Verify against local fake provider/Telegram servers, real HTTP authentication, restart persistence and a container smoke check if available.
- Live provider and Telegram completion are only claimed after observed execution with user-configured credentials.

Next: additional tool adapters, explicit approval execution, background jobs and packaging for supported hosts. Existing Kubernetes proof remains separate.
