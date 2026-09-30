# AgentOS 0.2.2 verification

Verified on 2026-09-06, macOS, using the Homebrew-installed runtime.
Configured and returned model: `minimax/minimax-m2.7:free` through OpenRouter.

| Same-conversation case | Result | Successful tools |
|---|---|---|
| search | PASS | web_search |
| files | PASS | find_files, read_file |
| delegate | PASS | delegate_agent, find_files, list_agents, list_notes, read_file |
| general | PASS | none |
| memory | PASS | save_note |

- 42 automated tests passed, including file boundaries, provider tool-result conversion,
  corrected arguments, note deduplication, topic switching, and rate-limit rerouting.
- Installed CLI startup, HTTP setup/authentication, note persistence across restart,
  and single-instance lock passed.
- Installed runtime/UI files matched the tested source.
- A browser request in the existing personal conversation called `web_search` and
  returned Kubernetes documentation links. The UI showed its actual execution status.
- Final local URL is http://127.0.0.1:8788/ because 8787 is occupied by a separate
  Docker preview. That Docker process was left running.

## Limits and non-passing runs

`openrouter/free` automatic routing did not pass all acceptance cases. Some selected
models answered without calling requested tools; rate limits and malformed responses
were also observed during development. The current personal installation uses the
specific free model above. A passing run does not guarantee all prompts or availability.

Specialists are built-in researcher/reviewer conversations using the selected provider,
not external Codex/Claude Code engines. Live Ollama and Anthropic execution was not
verified; their native tool message conversions were tested with simulated responses.
Connected files currently support bounded UTF-8 text reading, not PDF/Office or editing.

Reproduce with `python3 scripts/verify_general_agent.py --installed --model minimax/minimax-m2.7:free`.
The script uses a synthetic document and a temporary store, retaining results in
`GENERAL_AGENT_ACCEPTANCE.json` without altering personal notes or conversation.
