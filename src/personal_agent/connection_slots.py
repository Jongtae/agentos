"""AgentOS-held connections as read-only ``api_request`` slots (CONN-API).

The owner's AI decides at request time what it needs from a connected
service - one event in full, a message body, a file's revisions - and calls
the provider's own API through ``api_request``.  AgentOS keeps what an AI
must not own: the token (resolved, renewed and revision-checked per call by
the connector's existing machinery, never shown), the provider API host and
path prefix the token may reach, and read-only methods for a read grant.
No field list, endpoint list or question is defined here (C16).

The tools that already exist for these services (``calendar_query``,
``drive_search``/``drive_read``) stay; this only removes the blocker that
anything outside their fixed shape was unreachable except by the browser.
"""

#: Connector id -> the slot it serves: provider API hosts, path prefixes and a note for the AI.
#: Every one is a read grant, so only GET/HEAD are allowed.
SLOT_SPECS = {
    'google-calendar': {'hosts': ('www.googleapis.com',), 'paths': ('/calendar/v3/',),
                        'note': "the owner's Google Calendar, read-only (Calendar API v3, e.g. "
                                "/calendar/v3/calendars/{calendarId}/events/{eventId})"},
    'google-drive': {'hosts': ('www.googleapis.com',), 'paths': ('/drive/v3/',),
                     'note': "the owner's Google Drive, read-only (Drive API v3)"},
    'gmail': {'hosts': ('gmail.googleapis.com',), 'paths': ('/gmail/v1/users/me/',),
              'note': "the owner's Gmail, read-only (Gmail API v1, users/me)"},
}


def _slot(name, token):
    spec = SLOT_SPECS[name]
    return {'name': name, 'note': spec['note'], 'hosts': tuple(spec['hosts']), 'paths': tuple(spec['paths']),
            'header': 'Authorization', 'scheme': 'Bearer', 'subject': None, 'revision': 1,
            'max_age_seconds': 900, 'read_only': True, 'connection': name, 'token': token}


def _oauth_token(oauth, owner_id, grant, exchange):
    """A current access token for one ``CalendarOAuth`` grant, renewed first when expired (as the transports do)."""
    from .calendar_oauth import CalendarOAuthError, _authorization_context

    def token():
        if not oauth.credential_current(owner_id, grant=grant):
            try:
                oauth.refresh(owner_id, exchange, grant=grant)
            except CalendarOAuthError:
                pass
        access_token, _revision = _authorization_context(oauth.store, oauth.registry, owner_id, grant, oauth.now)
        return access_token
    return token


def build(service, owner_id):
    """The connection slots this owner can use now: one per connected read connector, else none."""
    from .calendar import CALENDAR_CONNECTOR_ID
    from .calendar_oauth import DRIVE_GRANT, READ_GRANT
    from .connector_contract import ConnectorState
    from .google_drive_read import DRIVE_CONNECTOR_ID
    registry = getattr(service, 'connector_registry', None)
    if registry is None:
        return {}

    def connected(connector_id):
        try:
            return registry.status(owner_id, connector_id).state is ConnectorState.CONNECTED
        except Exception:
            return False
    slots = {}
    calendar_oauth = getattr(service, 'calendar_oauth', None)
    if calendar_oauth is not None and connected(CALENDAR_CONNECTOR_ID):
        slots['google-calendar'] = _slot('google-calendar', _oauth_token(
            calendar_oauth, owner_id, READ_GRANT, getattr(service, 'calendar_token_exchange', None)))
    drive_oauth = getattr(service, 'drive_oauth', None)
    if drive_oauth is not None and connected(DRIVE_CONNECTOR_ID):
        slots['google-drive'] = _slot('google-drive', _oauth_token(
            drive_oauth, owner_id, DRIVE_GRANT, getattr(service, 'drive_read_token_exchange', None)))
    gmail = getattr(service, 'gmail', None)
    if gmail is not None:
        from .gmail import GMAIL_CONNECTOR_ID
        if connected(GMAIL_CONNECTOR_ID):
            slots['gmail'] = _slot('gmail', lambda: gmail._authorization_context(owner_id)[2])
    return slots
