# P7-03 paired Telegram task-card continuity acceptance

Status: awaiting an owner-run live acceptance. This file is a procedure, not
evidence that a Telegram account has been exercised. The release loop stays
blocked until the authenticated owner records the completed observations.

Successor note (PRESENCE-CONV-01 / #510, 2026-09-24): the task card is now the
acknowledgement for *long-running* Work only. A request that finishes within
`TELEGRAM_ACK_AFTER_SECONDS` answers in a single bubble and shows no card; a
request still queued or running after that delay gets the card described
below once, with the same cancel-while-queued and 진행 보기 behavior. Step 1
therefore observes the card only when the Work takes long enough (for example
while another request is still running). The original procedure is preserved
unchanged as historical scope.

Run this only with the already paired private Telegram account and an existing
verified model. Do not paste bot tokens, pairing links, task text, document
contents, API keys, message IDs, screenshots containing them, or database
copies into an issue, commit, or report.

1. In the paired private chat, send an ordinary natural-language request and
   observe one status-only task card. Press its cancellation button while it is
   queued; observe the card change to cancelled. Send a separate request that
   completes, and observe its terminal notification.
2. With a connected work folder and an external model that has not yet been
   approved for the current model/folder scope, request a document lookup.
   Observe the approval notification, choose either approval result, and
   confirm the button becomes inactive. The notification must not show a
   document excerpt.
3. In the authenticated local web UI, confirm Telegram conversation entries
   and the terminal result are present. Send one harmless web message as well,
   so the shared-store observation includes both channels.
4. Restart AgentOS using the normal local service command. Send another
   harmless paired Telegram request and confirm its card, completion, and web
   history continue after restart. If a send was interrupted, leave its state
   as unknown; do not retry it automatically.
5. Return to the authenticated AgentOS web page. When its Telegram acceptance
   panel offers **실제 Telegram 흐름 확인 기록**, click it only after completing
   the observations above. It records no messages, tokens, IDs, document text,
   or model output. The six-hour delivery loop then runs the local redacted
   verifier; no shell command is required for the owner.

   Developers can inspect the same read-only report manually:

   ```sh
   python3 scripts/verify_telegram_task_card_acceptance.py
   ```

   기본 경로는 `~/.local/share/agentos`이며, 다른 데이터 폴더를 검증할 때만 `--data-dir`를 지정합니다.

The report passes only when it sees a paired owner, a cancelled card, a
resolved document-approval notification, a sent terminal notification, both
web and Telegram history rows, and the two explicit owner observations. It
contains counts and state names only; it never prints secrets, identifiers, or
message/document content.
