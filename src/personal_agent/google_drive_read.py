"""Read-only Google Drive data plane for the owner's AI (DRIVE-CONNECT-01 #1172).

Two reads, nothing else: ``search`` (Drive v3 ``files.list``) and ``read``
(``files.get`` metadata, then ``files.export`` for Google Docs/Sheets/Slides or
``alt=media`` for an ordinary file).  Ordinary file bytes go through the same
bounded extractor connected folders use (:mod:`personal_agent.document_reader`),
so a PDF in Drive and a PDF in a connected folder read identically.

This module holds no credential.  It is handed a ``transport(url) -> bytes``
that owns the token: :func:`personal_agent.calendar_oauth.drive_transport`
re-resolves, refreshes and revision-pins it on every call and refuses any
destination outside :data:`DRIVE_API`.  That mirrors the Calendar split
(``google_calendar`` data plane, ``calendar_oauth`` credential transport).

The connector is the ``drive.readonly`` successor that #440 retired with the
``drive.file`` + Picker handoff (``drive_web_oauth``) as the narrower option;
the owner chose full-Drive read on 2026-10-08 (#1172).  That handoff is left
unchanged and is a different connector id.
"""
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode

from .connector_contract import ConnectorSpec
from .document_reader import MAX_FILE_BYTES, SUPPORTED_SUFFIXES, read as read_document

DRIVE_CONNECTOR_ID = 'google-drive'
DRIVE_READONLY_SCOPE = 'https://www.googleapis.com/auth/drive.readonly'
DRIVE_SPEC = ConnectorSpec(DRIVE_CONNECTOR_ID, (DRIVE_READONLY_SCOPE,))
DRIVE_API = 'https://www.googleapis.com/drive/v3'

#: Text handed back to the model per read, the same bound ``read_file`` uses.
MAX_CONTENT_CHARS = 24_000
MAX_RESULTS = 20
_FILE_ID = re.compile(r'[A-Za-z0-9_-]{10,200}\Z')
_FIELDS = 'id,name,mimeType,modifiedTime,size,webViewLink'
#: Google-native files and the plain format each is exported as.
_EXPORTS = {
    'application/vnd.google-apps.document': ('text/plain', '.txt'),
    # XLSX, not CSV: Drive exports only the first sheet as CSV.
    'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation': ('text/plain', '.txt'),
}
#: Ordinary files the local extractor reads, by MIME type.
_SUFFIX_BY_MIME = {
    'application/pdf': '.pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'text/markdown': '.md',
}


class DriveReadError(ValueError):
    """A refused or failed Drive read; the text never carries owner data."""

    def __init__(self, reason, message='Google Drive 파일을 읽지 못했습니다.'):
        super().__init__(message)
        self.reason = reason


class DriveHTTPError(Exception):
    """A non-success status from the Drive API, raised by the transport."""

    def __init__(self, status):
        super().__init__(f'Google Drive API returned {status}')
        self.status = status


def _quoted(text):
    # Drive query string literals escape backslash and single quote.
    return "'" + text.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _row(item):
    return {'file_id': item.get('id', ''), 'name': item.get('name', ''), 'mime_type': item.get('mimeType', ''),
            'modified': item.get('modifiedTime', ''), 'link': item.get('webViewLink', '')}


class GoogleDriveReader:
    """Search and read the owner's Drive through a credential-owning transport."""

    def __init__(self, transport):
        if not callable(transport):
            raise ValueError('A Drive transport is required.')
        self.transport = transport

    def _json(self, path, params):
        raw = self.transport(f'{DRIVE_API}/{path}?{urlencode(params)}')
        try:
            value = json.loads(raw or b'{}')
        except (TypeError, ValueError):
            raise DriveReadError('invalid_provider_response') from None
        if not isinstance(value, dict):
            raise DriveReadError('invalid_provider_response')
        return value

    def search(self, query='', limit=MAX_RESULTS):
        """Files whose name or text matches ``query``; the most recent files when it is empty."""
        if not isinstance(query, str) or len(query) > 200:
            raise DriveReadError('invalid_query', '검색어는 200자 이하로 입력하세요.')
        limit = max(1, min(int(limit or MAX_RESULTS), MAX_RESULTS))
        clauses = ['trashed = false', "mimeType != 'application/vnd.google-apps.folder'"]
        text = query.strip()
        if text:
            clauses.append(f'(name contains {_quoted(text)} or fullText contains {_quoted(text)})')
        params = {'q': ' and '.join(clauses), 'pageSize': limit, 'fields': f'files({_FIELDS})',
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
        # Drive refuses orderBy together with a fullText query.
        if not text:
            params['orderBy'] = 'modifiedTime desc'
        files = self._json('files', params).get('files')
        rows = [_row(item) for item in files if isinstance(item, dict)] if isinstance(files, list) else []
        return {'files': rows[:limit], 'truncated': len(rows) >= limit}

    def read(self, file_id):
        """One file's text: exported for Google-native files, extracted locally for the rest."""
        if not isinstance(file_id, str) or not _FILE_ID.fullmatch(file_id):
            raise DriveReadError('invalid_file_id', 'drive_search가 돌려준 file_id로 읽어 주세요.')
        meta = self._json(f'files/{quote(file_id)}', {'fields': _FIELDS, 'supportsAllDrives': 'true'})
        mime = str(meta.get('mimeType') or '')
        name = str(meta.get('name') or '')
        if mime in _EXPORTS:
            export_mime, suffix = _EXPORTS[mime]
            raw = self.transport(f'{DRIVE_API}/files/{quote(file_id)}/export?{urlencode({"mimeType": export_mime})}')
        else:
            suffix = _SUFFIX_BY_MIME.get(mime) or ('.txt' if mime.startswith('text/') else Path(name).suffix.lower())
            if suffix not in SUPPORTED_SUFFIXES:
                raise DriveReadError('unsupported_type',
                                     '이 Drive 파일 형식은 읽을 수 없습니다. 구글 문서·시트·프레젠테이션, PDF, DOCX, XLSX, TXT, MD를 읽을 수 있습니다.')
            try:
                size = int(meta.get('size') or 0)
            except (TypeError, ValueError):
                size = 0
            if size > MAX_FILE_BYTES:
                raise DriveReadError('too_large', '10MB 이하 파일만 읽을 수 있습니다.')
            raw = self.transport(f'{DRIVE_API}/files/{quote(file_id)}?{urlencode({"alt": "media", "supportsAllDrives": "true"})}')
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_FILE_BYTES:
            raise DriveReadError('too_large', '10MB 이하 파일만 읽을 수 있습니다.')
        document = self._extract(bytes(raw), suffix)
        segments = document.segments
        rendered = '\n'.join(f"[{segment['location']}] {segment['text']}" for segment in segments)
        content = rendered[:MAX_CONTENT_CHARS]
        return {**_row(meta), 'kind': document.kind, 'content': content,
                'locations': [segment['location'] for segment in segments[:100]],
                'sources': [f'Google Drive: {name}'], 'truncated': len(rendered) > len(content)}

    @staticmethod
    def _extract(raw, suffix):
        # The extractor reads a path.  A private temporary file is created and
        # removed here; nothing is kept under the owner store.
        handle, path = tempfile.mkstemp(suffix=suffix, prefix='agentos-drive-')
        try:
            with os.fdopen(handle, 'wb') as file:
                file.write(raw)
            try:
                return read_document(path)
            except ValueError as exc:
                raise DriveReadError('unreadable', str(exc)) from None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
