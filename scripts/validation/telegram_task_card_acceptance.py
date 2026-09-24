"""Historical Telegram task-card acceptance evidence.

Moved out of the installed personal_agent runtime by CLEANUP-LEGACY-01 / #532.
The current product UI no longer consumes this acceptance read model; it remains
available to repository validation scripts and tests.
"""
from collections import Counter


def report(store, web_confirmed=None, restart_confirmed=None):
    """Return only aggregate evidence; never return messages, ids, or secrets."""
    telegram=store.config('telegram', {})
    attestation=store.config('telegram_task_card_acceptance', {})
    if web_confirmed is None:web_confirmed=bool(attestation.get('web_confirmed'))
    if restart_confirmed is None:restart_confirmed=bool(attestation.get('restart_confirmed'))
    with store.db() as db:
        cards=Counter(row['state'] for row in db.execute('SELECT state FROM telegram_task_cards'))
        notifications=Counter(
            (row['kind'], row['state'])
            for row in db.execute('SELECT kind,state FROM telegram_notifications')
        )
        telegram_messages=db.execute(
            "SELECT count(*) FROM messages WHERE channel LIKE 'telegram:%'"
        ).fetchone()[0]
        web_messages=db.execute(
            "SELECT count(*) FROM messages WHERE channel='web'"
        ).fetchone()[0]
        terminal=db.execute("SELECT count(*) FROM jobs WHERE channel LIKE 'telegram:%' AND status IN ('succeeded','partial','failed') AND delivery='sent'").fetchone()[0] > 0

    paired=bool(telegram.get('enabled') and isinstance(telegram.get('user_id'), int)
                and isinstance(telegram.get('generation'), str))
    cancellation=cards['cancelled'] > 0
    approval=any(kind == 'approval_needed' and state in ('approved', 'denied')
                 for kind, state in notifications)
    checks={
        'paired_private_owner': paired,
        'task_card_cancellation': cancellation,
        'document_approval_callback': approval,
        'terminal_notification': terminal,
        'shared_web_evidence_observed': bool(web_confirmed and telegram_messages and web_messages),
        'restart_continuity_observed': bool(restart_confirmed),
    }
    return {
        'paired_private_owner': paired,
        'task_cards_by_state': dict(sorted(cards.items())),
        'notifications_by_kind_and_state': {
            f'{kind}:{state}': count for (kind, state), count in sorted(notifications.items())
        },
        'message_channels': {'telegram': telegram_messages, 'web': web_messages},
        'checks': checks,
        'passed': all(checks.values()),
    }
