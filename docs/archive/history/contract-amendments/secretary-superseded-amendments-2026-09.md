# Secretary Agency — superseded amendment history

These blocks were extracted from the canonical [Secretary Agency Contract](../../../secretary-agency-contract.en.md) by DOCS-CONSOLIDATE-02 (#1053). They are preserved as decision history and are **not current policy except where the canonical contract explicitly points back to a still-live sub-rule**. The canonical current-rule index controls precedence.

## Source: #836 and #818 owner-AI Memory ask history

The owner's own AI path described in these amendments was superseded by #918 slice (a), which saves directly and tells with undo. The third-party/delegated candidate boundary remains current and is summarized in the canonical contract.

## Amendment — #836 (2026-09-28)

PRESENCE-MEM-01 amends the #818 amendment below after owner feedback: "두 번 물어봤고, 첫 번째에 답을 하면 그 뒤에 것도 처리가 되어야 함. 그리고 AgentOS가 라면서 시스템 툴을 다루듯이 했는데, 우리의 컨셉은 presence잖아." The owner-facing rules are in the [Presence Experience Contract](presence-experience-contract.en.md) amendment of the same number.
- **One ask per Work.** The reply's ask (`memory_candidates`) is bound when it is sent to every candidate of the Work still pending then, up to five. #805 upkeep queues no separate prompt (`memory_candidates_upkeep` rows sent before still work and expire). After upkeep, `join_memory_prompt` handles the Work's ask:
  - No ask yet, or an ask cancelled because nothing was pending: this becomes the first ask.
  - An ask still queued: its binding at send time includes the new candidates.
  - An open or list-only ask: the new candidates are added by editing the message. They are bound only when the edit is confirmed, so a tap never covers a fact the owner was not shown.
  - An answered ask: one answer settles them. A no rejects. A yes accepts through `issue_candidate_memory_approval` → `accept_memory_candidate` when the ask can show the value complete and it replaces no current Memory. The binding lists them under `by_answer` (provenance: the owner's answer to that Work's ask), and the edit shows them.
  - Mixed answers, or a yes that would replace a Memory the owner was not shown: the ask reopens with the new facts and fresh buttons.
  - An expired ask, or one with unknown delivery: the candidates stay in 내 기록.
  The web list reads the same store state.
- **Upkeep dedupe.** The proposal judgment gets `already_noted`: what the Work already wrote or proposed, as owner words, with secrets redacted. The question says never to propose what it covers. AgentOS also drops a proposal under a key the Work already used.
- **Wording.** The ask shows values, never keys. A value written like a key (`food_preference.rolls_and_rolls_sushi`) is shown as its words, and a tap needs that shown value complete and unredacted. Once answered, the first line is "기억해 둘게요." / "기억하지 않을게요." / "말씀하신 것만 기억해 둘게요.". The Telegram "기억은 아직 저장되지 않았어요…" line and the "기억한 내용은 내 기록에서 고치거나 지울 수 있습니다" footer are removed. The web keeps "기억해 둘지는 내 기록에서 골라 주세요." until nothing of that Work is pending.
- **Worker view.** A held `save_memory` reaches the worker, on the direct loop and the MCP bridge alike, as `{remembered: false, content, next}` (`worker_result`), with no AgentOS, approval, candidate or storage wording. AgentOS keeps the full result for Evidence and the trail. The `save_memory` description and the core instructions follow suit ("Speak as the owner's secretary: never narrate AgentOS, tools, approvals, candidates or other internal states").
- **Kept.** #597 authority, secrets exclusion and truthfulness. No task-specific code (C16).


## Amendment — #818 (2026-09-28)

OWNER-MODEL-04 follows owner feedback on Works `18c91ca7` and `7767e7da`, where a stated fact became a pending MemoryCandidate and the owner saw only a failure:
- **A proposed memory is not a failed action.** A `save_memory` that #597 holds as a pending MemoryCandidate is a recorded proposal (trail state `proposed`). It neither withholds the answer (#752 `answer_withheld`) nor makes the Work partial or failed, and it is not evidence of the goal. The #488/#752 rule is unchanged for every other tool, for calendar drafts and for a memory write that errored.
- **The reply never reads as if Memory changed.** (Telegram line removed by #836; see above.) AgentOS does not inspect the model's prose. When a Work has pending candidates, AgentOS appends its own line to the reply: on Telegram "기억은 아직 저장되지 않았어요. 아래에서 확인하시면 저장돼요.", and on the web the same line pointing to 내 기록. The web line disappears once nothing of that Work is pending.
- **The owner confirms in one tap, and approves only what was shown.** One message lists the Work's pending candidates after its reply was delivered `sent` (never after an `unknown` delivery).
  - A candidate gets its own [👍] [👎] buttons (#881; formerly [기억하기] [아니요]) only when the message shows its key and value complete and unchanged: within the display bound and untouched by whitespace folding or secret redaction. Any other candidate is listed with "내 기록에서 확인해 주세요" and no button, and a message with nothing tappable is only a list. "All" buttons appear when more than one tappable candidate is open.
  - A value it would replace is shown as "(현재: …)".
  - The message follows the #659 pattern: this notification, sent, the paired private chat, its generation and message. It is bound at send time to the shown candidate ids, their content digests and the current Memory under each key. At a tap, each targeted candidate must still be pending with that content, and for a yes the current Memory under its key must be unchanged. Otherwise it is shown as outdated and nothing is written.
  - The buttons expire after 24 hours: taps are then refused and the buttons removed.
  - A yes goes through the existing owner approval path (`issue_candidate_memory_approval` → `accept_memory_candidate`); a no is the existing reject. The web keeps 내 기록.
- **Candidates from #805 upkeep.** (Superseded by #836: they join the Work's one ask.) Upkeep runs after the reply. When it leaves new pending candidates on a Telegram Work whose reply was delivered `sent`, it queues one later prompt for the candidates no earlier prompt listed. The prompt uses the same bindings, TTL and buttons, with at most one upkeep prompt per Work. Candidates added after that are left to 내 기록.
- **Guidance only (C16).** `save_memory` content is the value in the owner's own words, and the key names the attribute. When the owner tells AgentOS something rather than asking, the plan question and the core instructions ask for a secretary's response: acknowledge it, update what AgentOS knows, and act on what it changes. No task logic.


## Source: #701 and #705 private-read/native-search separation history

These search/private-read separation rules were superseded by #826 EGRESS-OPEN-01. Other #701 CLI/browser/turn-record facts that remain relevant are retained in the canonical contract rather than copied here.

## Amendment — #701 (2026-09-27)

SEC-CLI-01 makes the loop work on the owner's subscription CLI route (Codex or Claude Code, trusted-local profile):
- **Legacy provenance.** Works recorded before #605 are classified once from durable signals only (private tool events, the document-job list, context attachments, saved notes, the notes-summary command, turn records, whether a model produced the reply). A clean one is recorded as owner conversation; any private signal keeps it unrecorded. No judgment about text.
- **Native-search gate (owner decision on #701; superseded by #705).** The #678 gate read only what the shown messages' own Works read themselves, not the inherited `history:*` chain, so a Work that read notes blocked the CLI's own search while its messages were in the shown 16-message window. Since #705 the gate ignores prior conversation entirely (see the #705 amendment). Mediated browser output (`owner-browser-session`) never blocked it. The #605 inheritance rule, including the browser-session label, is unchanged for public-lookup composition and turn-record storage.
- **Search.** On a turn where the CLI's own web search is on, the bridge's `web_search` and `bounded_public_research` are not offered, so the CLI's own search answers. When it is off, the bridge search tools say why and name each provider's own caveat.
- **Browser.** The five browser tools are offered on the trusted-local CLI route. The bridge only relays each call to the AgentOS service, which runs it through the same `BrowserSession` as the direct route: mediation, the label-independent payment guard, approvals, budget, repeat key, loopback refusal, the one profile lock and the encrypted jar are unchanged. The strict-isolated and isolated profiles never offer them. On a native-search turn the browser tools stay; the pre-turn gate alone decides native search.
- **Turn records.** The local prompt envelope is kept after deterministic redaction of the Work's lookup-exclusion set (its Memory candidates, notes and calendar drafts), stored secret values and credential shapes. Profile values have no identifier marker and are kept as sent. Only a turn that carried a private store (notes, documents, Drive, context inbox, Memory reads, calendar, the browser session and the other private stores, including ones inherited from shown history under #605) keeps size and digest only. Turn records stay out of export and backup.
- **Settings** shows, per Main AI route, whether its own web search and the browser tools are available, and why not (including a CLI that is not installed or not signed in).

## Amendment — #705 (2026-09-27)

SEC-SEARCH-03, by owner direction under the pilot posture (#705; runtime-only scope under #707):
- **Native-search gate.** Prior conversation history no longer turns the CLI's own web search off. The gate is off only when the **current turn** carries an explicit private splice (a document, Drive file, context inbox, `/summarize` or notes pasted into the prompt at turn start), when the profile is strict-isolated or the isolated sidecar, or when the CLI's refusal is remembered. A shown earlier Work that read notes, Codex's own `list_notes` call, `unrecorded` legacy rows, `engine-unmediated-read` and `owner-browser-session` no longer matter to this gate.
- **Why.** The CLI's own search runs at the owner's configured AI provider (OpenAI for Codex, Anthropic for Claude Code), and the pilot posture already accepts egress to that provider. Offering `/new` to reset context was rejected for ordinary users (#704).
- **Accepted egress change.** Private material from earlier turns that the CLI is shown can now appear in the CLI model's own search queries to that provider. AgentOS does not compose or redact those queries. This weakens the #678 boundary by owner direction and takes independent review.
- **Unchanged.** The private-read bridge tools (`list_notes` and the other private-store reads) are still not offered on a native-search turn, so the model cannot read a store and search in the same turn. Notes reach a CLI turn as an explicit splice (`/summarize`) or through a search-off turn's `list_notes`, and search is off for that turn only. Stored secrets never enter prompts. The #605 inheritance rule is unchanged for AgentOS-composed third-party lookups (Bing, Brave) and for turn-record storage.

