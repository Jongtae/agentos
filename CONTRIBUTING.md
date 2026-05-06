# Contributing

AgentOS uses an issue-first workflow.

Before making changes:

1. Open or select a GitHub issue.
2. Create a matching branch such as `feature/<slug>`, `fix/<slug>`, `docs/<slug>`, `build/<slug>`, or `experiment/<slug>`.
3. Keep commits focused.
4. Open a pull request before merging.
5. Run targeted validation and document the result in the PR.
6. Keep generated artifacts and secrets out of Git.

The full contributor workflow is in `AGENTS.md`.

Generated paths such as `build-output/`, runtime workspace artifacts, `.env`, generated ISOs, and local secrets must not be committed.

Please avoid naming public branches, pull requests, or commits after the AI or
automation tool used to make the change. Public history should describe the
product intent and validation path.
