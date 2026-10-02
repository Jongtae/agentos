# Sharing a signed-in site with another assistant

Sharing passes the owner's current sign-in session for one site to another assistant on this Mac. No password is passed. The receiving assistant can browse and add to a cart there, but only the account owner can pay. This is a shared session, not a separate credential issued by the site.

## Steps

1. Call `settings_read` with category `family`.
   - `share_site.signed_in_sites` lists the sites this assistant is signed in to.
   - `share_site.assistants` lists the possible receivers. The owner's own main assistant is among them when you are a family assistant.
   - `share_site.shared` lists the current shares.
   - `share_site.received_sites` lists sites this assistant itself received from the account owner. Those cannot be passed on.
2. Resolve the receiver to one instance and the site to one listed domain. Turn a nickname into the site's domain yourself. If the site is not in `signed_in_sites`, say the owner must sign in to it here first.
3. To share, propose `settings_change` with category `family`, setting `share_site`, value `<assistant name or instance id>|<site domain>`. To stop, use setting `unshare_site` with the same value, or with the site domain alone when only one assistant has it.

## Report what the result says

- **Delivered:** the receiving assistant has the session now.
- **Pending (전달 대기):** the receiver did not answer. AgentOS keeps retrying, and the share takes effect when that assistant is running.
- **Receiver already signed in:** the receiver keeps its own sign-in and nothing was shared.
- **Stopping:** the share is fully stopped only when the result says so. If the receiver was not reachable, the session is removed when it comes back. Say that instead of claiming it is gone now.

## Never

- Pass on a site this assistant received from someone else.
- Put cookies, tokens or passwords into a message or a memory.
- Call sharing a payment permission.
- Use sharing to reach another person's account.
