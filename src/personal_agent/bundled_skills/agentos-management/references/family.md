# A family member's assistant

A family assistant is a separate AgentOS on this Mac with its own Telegram bot. It uses the owner's AI subscription and keeps its own memory, conversations and sign-ins.

## Before creating one

1. Call `settings_read` with category `family`. `share_site.assistants` lists every other assistant on this Mac, with its Telegram name, instance id and state.
2. If an assistant with the requested name is already **연결됨** (paired), it exists. Do not create another one. Tell the owner it is already there. If they mean a different person, ask for a different name.
3. An assistant that is **설정 중** (setting up) or **연결 안 됨** (not connected) is an unfinished setup. Asking again reuses that instance. It does not add a new one.

## Creating

Propose `settings_change` with category `family`, setting `add`, and the new assistant's Telegram name as the value. After the owner confirms, AgentOS prepares the instance and sends the owner a setup link on Telegram to forward. Report this as **requested**, not finished.

## Keep these states apart

- **Prepared:** the instance exists and the setup link is being made.
- **Link sent:** the owner received a link to forward. It is open for a limited time.
- **Paired:** the family member made their bot and started talking to it. Only now is the assistant ready to use.

An **expired link** only means that setup did not finish in time. It does not mean an already paired assistant is disconnected. To finish a setup, the owner simply asks again; the unfinished instance is reused.

## Never

- Create two assistants for one request.
- Say the family member can use their assistant before it is paired.
- Move the owner's memory, conversations or credentials to a family assistant.
- Delete a family assistant or its data. That is not a conversation action.
