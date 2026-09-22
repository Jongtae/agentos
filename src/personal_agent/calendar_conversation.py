"""Natural-language Calendar create, from one owner utterance to one approval.

This is the executing worker branch that ``calendar-create`` never had: the
intent classifier recognised "내일 오후 3시에 치과 일정 잡아줘" and answered
with a fixed clarification that promised a draft, and the owner's reply then
carried no calendar cue, fell to the model route, and drafted nothing.

The authority split is unchanged and is the point of this file:

* **Interpretation is AgentOS's.**  Title, date, time and duration are read
  by literal rules declared below, in the same reviewable style as
  ``conversation_handoff``'s cue tables.  No model is consulted, and a model
  suggestion still cannot select this intent.
* **Interpretation never becomes an effect.**  Everything here ends in
  ``CalendarConnector.draft_create``, which is an owner-bound proposal with
  no external effect, or in a question.  The preview shows exactly what would
  be sent.
* **Only the owner's explicit approval of that preview executes.**  The
  approval spends ``CalendarConnector.approve`` -> ``execute``, which binds
  a one-time token to this owner, this draft, this payload hash and the write
  connector's revision.  A correction, cancel, new request, topic change or
  expiry leaves the earlier draft inert.

Durable state is one ``calendar_conversation`` row: hashed owner, the slots
already collected, the draft id and payload hash being shown, and an expiry.
It is the same content class as the existing ``calendar_create`` draft table
and holds no utterance text and no secret.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta
import os
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .calendar import CalendarError
from .connector_contract import _owner_key

STATE_KEY = 'calendar_conversation'
PENDING_TTL_SECONDS = 900
DEFAULT_DURATION_MINUTES = 60
TIMEZONE_CONFIG_KEY = 'calendar_timezone'
_MAX_TITLE = 200

STATE_COLLECTING = 'collecting'
STATE_AWAITING_APPROVAL = 'awaiting-approval'

# --- owner-facing text -------------------------------------------------------
ASK_TITLE = '어떤 일정인가요? 제목만 알려 주세요. (예: 치과)'
ASK_WHEN = '언제인가요? 날짜와 시각을 알려 주세요. (예: 내일 오후 3시)'
ASK_TIME = '몇 시인가요? (예: 오후 3시, 15:00)'
ASK_DATE = '어느 날인가요? (예: 내일, 금요일, 9월 25일)'
PREVIEW_HEADER = '일정 초안입니다. 아직 캘린더에 만들지 않았습니다.'
PREVIEW_FOOTER = ('"승인"이라고 답하면 이 내용 그대로 만듭니다. '
                  '바꾸려면 예: "4시로", "제목은 치과 검진으로". 그만두려면 "취소"라고 답해 주세요.')
REPLACED_NOTICE = '이전 일정 초안은 취소했습니다.'
DROPPED_NOTICE = '대기 중이던 일정 초안은 실행하지 않고 취소했습니다.'
CANCELLED = '일정 초안을 취소했습니다. 아무 일정도 만들지 않았습니다.'
NOTHING_PENDING = '승인할 일정 초안이 없어 아무 일정도 만들지 않았습니다. 새로 요청해 주세요.'
OTHER_CHANNEL = ('이 일정 초안은 다른 채널에서 만든 것이라 여기서 승인하지 않았습니다. '
                 '초안을 만든 채널에서 "승인"이라고 답해 주세요.')
CHANGED_UNDER_US = '초안 내용이 확인한 미리보기와 달라 일정을 만들지 않았습니다. 다시 요청해 주세요.'
CREATED = '캘린더에 일정을 만들었습니다.'
OUTCOME_UNKNOWN = ('일정을 만들었는지 확인할 수 없습니다. 캘린더를 직접 확인하고, 없으면 다시 요청해 주세요. '
                   '자동으로 다시 시도하지 않았습니다.')
FAILED = '일정을 만들지 못했습니다. 아무 일정도 만들지 않았습니다.'
RECONNECT_HINT = ' 캘린더를 다시 연결한 뒤 새로 요청해 주세요.'
RETRY_HINT = ' 새로 요청해 주세요.'

# --- vocabularies ------------------------------------------------------------
# Every entry is a literal an owner can read and a reviewer can audit.
APPROVE_WORDS = frozenset({
    '승인', '승인해', '승인해줘', '승인해 줘', '승인할게', '승인합니다', '승인이요', '확인', '확인했어', '확인했어요',
    '네', '예', '응', '어', '좋아', '좋아요', '그래', '그래요', '맞아', '맞아요', '진행해', '진행해줘', '진행해 줘',
    '만들어', '만들어줘', '만들어 줘', '등록해줘', '등록해 줘', '그렇게 해줘', '그렇게 해', '해줘',
    'ok', 'okay', 'yes', 'y', 'yep', 'yeah', 'approve', 'approved', 'confirm', 'confirmed', 'go ahead',
    'do it', 'create it', 'looks good', 'lgtm', 'sure', 'go',
})
CANCEL_WORDS = frozenset({
    '취소', '취소해', '취소해줘', '취소해 줘', '아니', '아니요', '아니오', '아냐', '됐어', '됐어요', '그만', '그만해',
    '하지 마', '하지마', '하지 마세요', '없던 걸로', '없던걸로', '잊어', '잊어줘', '관둬', '말아', '말고',
    'no', 'nope', 'cancel', 'never mind', 'nevermind', 'forget it', 'stop', "don't", 'dont', 'scratch that',
    'not now', 'abort',
})
#: Tokens that may accompany a bare cancel without changing its meaning.
_CANCEL_FILLER = frozenset({'그거', '그건', '이거', '이건', '일정', '초안', '그냥', '전부', '다', '좀', 'it', 'that',
                            'this', 'the', 'draft', 'event', 'please', 'just', 'all'})
_CORRECTION_CUES = ('그게 아니라', '아니라', '아니고', '아니', '말고', '대신', '바꿔', '변경', '수정', '옮겨',
                    'no,', 'not that', 'instead', 'actually', 'change', 'make it', 'move it', 'move',
                    'rather', 'switch', 'correction', 'scratch that')
_AMEND_MARKERS_KO = ('로 바꿔', '으로 바꿔', '로 변경', '으로 변경', '로 해', '으로 해', '로 수정', '으로 수정',
                     '로 옮겨', '으로 옮겨', '로 해줘', '으로 해줘')

_CALENDAR_FILLER_KO = (
    '캘린더에', '캘린더', '달력에', '달력', '일정으로', '일정을', '일정이', '일정은', '일정', '스케줄', '이벤트',
    '잡아 주세요', '잡아주세요', '잡아 줘', '잡아줘', '잡아줄래', '잡을래', '잡아', '잡고', '잡을',
    '만들어 주세요', '만들어주세요', '만들어 줘', '만들어줘', '만들어', '등록해 주세요', '등록해주세요', '등록해 줘',
    '등록해줘', '등록해', '등록', '추가해 주세요', '추가해주세요', '추가해 줘', '추가해줘', '추가해', '추가',
    '넣어 주세요', '넣어주세요', '넣어 줘', '넣어줘', '넣어', '예약해 줘', '예약해줘', '예약해',
    '잡아야 해', '잡아야 함', '해 줘', '해줘', '주세요', '부탁해', '부탁', '하나', '한 개', '좀', '제발',
)
_CALENDAR_FILLER_EN = (
    'schedule', 'scheduled', 'add', 'create', 'book', 'set up', 'setup', 'put', 'make', 'new',
    'on my calendar', 'in my calendar', 'to my calendar', 'to the calendar', 'on the calendar',
    'calendar event', 'calendar', 'event', 'an event', 'for me', 'please', 'me',
    'at', 'on', 'for', 'from', 'to', 'until', 'till', 'of', 'in',
)
#: Residue that is a usable title on its own.  ``일정``/``event`` are not.
_GENERIC_OBJECTS = frozenset({'일정', '이벤트', '스케줄', 'event', 'calendar', 'schedule', 'appt'})
_TRAILING_PARTICLES = ('에는', '에서', '으로', '에게', '한테', '이랑', '하고', '에', '로', '을', '를', '은', '는',
                       '이', '가', '도', '만', '와', '과')
#: Endings that mark a question or a request, not a title.
_NOT_A_TITLE_ENDINGS = ('어때', '어때요', '뭐야', '뭐예요', '까', '까요', '줘', '주세요', '나요', '가요', '니', '해',
                        '해요', '봐', '볼까', '할까', '있어', '있어요', '없어', '없어요', '알려', '찾아')
_NOT_A_TITLE_STARTS = ('what', 'how', 'why', 'when', 'where', 'who', 'is ', 'are ', 'do ', 'does ', 'can ',
                       'could ', 'should ', 'tell me', 'show me', 'find', 'search', 'look up')

_WEEKDAYS_KO = '월화수목금토일'
_WEEKDAYS_EN = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
_WEEKDAYS_EN_SHORT = ('mon', 'tue', 'tues', 'wed', 'thu', 'thur', 'thurs', 'fri', 'sat', 'sun')
_MONTHS_EN = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
              'october', 'november', 'december')
_MONTHS_EN_SHORT = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec')

# --- time expressions --------------------------------------------------------
_TIME_KO = re.compile(
    r'(?P<mer>오전|오후|아침|새벽|저녁|밤|낮)?\s*(?P<h>\d{1,2})\s*시\s*(?:(?P<m>\d{1,2})\s*분|(?P<half>반))?'
    r'\s*(?:쯤|경|정도)?(?:에는|에서|부터|까지|에|로|으로)?')
_TIME_EN = re.compile(
    r'(?<![\d:])(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<mer>a\.?m\.?|p\.?m\.?)(?![a-z])', re.I)
_TIME_24 = re.compile(r'(?<![\d:])(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)(?!\d)')
_TIME_AT = re.compile(r'\b(?:at|from|to|until|till|by)\s+(?P<h>\d{1,2})(?![\d:]|\s*(?:am|pm|시|월|일|분|시간|hour|min|h\b))', re.I)
_NOON = re.compile(r'정오|\bnoon\b|\bmidday\b', re.I)
_MIDNIGHT = re.compile(r'자정|\bmidnight\b', re.I)
_RANGE_SEP = re.compile(r'\s*(?:~|-|–|—|부터|에서|to|until|till|through)\s*', re.I)

# --- durations ---------------------------------------------------------------
_DURATION_KO = re.compile(r'(?P<h>\d+(?:\.\d+)?)\s*시간\s*(?:(?P<half>반)|(?P<m>\d{1,2})\s*분)?\s*(?:동안|짜리|으로|로|정도)?'
                          r'|(?P<mo>\d{1,3})\s*분\s*(?:동안|짜리|으로|로|정도)?')
_DURATION_EN = re.compile(r'\b(?:for\s+)?(?:(?P<h>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b(?:\s*(?:and\s+)?(?P<m>\d{1,2})\s*(?:minutes?|mins?))?'
                          r'|(?P<mo>\d{1,3})\s*(?:minutes?|mins?)\b|(?P<an>an hour|one hour|half an hour|half hour))', re.I)

# --- dates -------------------------------------------------------------------
_DATE_ISO = re.compile(r'(?P<y>20\d{2})[-./]\s?(?P<mo>1[0-2]|0?[1-9])[-./]\s?(?P<d>3[01]|[12]\d|0?[1-9])(?!\d)')
_DATE_KO_MD = re.compile(r'(?:(?P<y>20\d{2})\s*년\s*)?(?P<mo>1[0-2]|0?[1-9])\s*월\s*(?P<d>3[01]|[12]\d|0?[1-9])\s*일(?:에는|에|부터)?')
_DATE_SLASH = re.compile(r'(?<![\d/])(?P<mo>1[0-2]|0?[1-9])/(?P<d>3[01]|[12]\d|0?[1-9])(?![\d/])')
_DATE_EN_MD = re.compile(r'\b(?P<mon>' + '|'.join(_MONTHS_EN + _MONTHS_EN_SHORT) + r')\.?\s+(?P<d>3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?\b'
                         r'(?:,?\s*(?P<y>20\d{2}))?', re.I)
_DATE_EN_DM = re.compile(r'\b(?P<d>3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?\s+(?P<mon>' + '|'.join(_MONTHS_EN + _MONTHS_EN_SHORT) + r')\b'
                         r'(?:,?\s*(?P<y>20\d{2}))?', re.I)
_DATE_REL_KO = re.compile(r'(?P<w>오늘|내일|모레|글피)(?:은|는|에|에는)?')
_DATE_REL_EN = re.compile(r'\b(?P<w>day after tomorrow|tomorrow|today|tonight)\b', re.I)
_DATE_IN_DAYS_KO = re.compile(r'(?P<n>\d{1,2})\s*일\s*(?:후|뒤)(?:에|에는)?')
_DATE_IN_DAYS_EN = re.compile(r'\bin\s+(?P<n>\d{1,2})\s+days?\b', re.I)
_WEEKDAY_KO = re.compile(r'(?P<week>이번\s*주|다음\s*주|다다음\s*주)?\s*(?P<w>[월화수목금토일])요일(?:에는|에|은|는)?')
_WEEKDAY_EN = re.compile(r'\b(?:(?P<week>this|next|coming|on)\s+)?(?P<w>' + '|'.join(_WEEKDAYS_EN + _WEEKDAYS_EN_SHORT) + r')\b', re.I)

_TITLE_AMEND_KO = re.compile(r'제목\s*(?:은|을|는|이|:)?\s*(?P<t>.+?)\s*(?:으로|로)?\s*(?:바꿔\s*줘|바꿔|변경해\s*줘|변경|해\s*줘|해|수정해\s*줘|수정)?\s*$')
_TITLE_AMEND_EN = re.compile(r'\b(?:title|name|call it|name it|rename(?: it)? to|title it|titled)\s*:?\s*(?P<t>.+?)\s*$', re.I)


def resolve_local_timezone(store=None, environ=None):
    """The IANA zone events are drafted in: owner config, then TZ, then the host."""
    environ = os.environ if environ is None else environ
    candidates = []
    if store is not None:
        candidates.append(store.config(TIMEZONE_CONFIG_KEY, None))
    candidates.append(environ.get('TZ'))
    try:
        real = os.path.realpath('/etc/localtime')
        if 'zoneinfo/' in real:
            candidates.append(real.split('zoneinfo/', 1)[1])
    except OSError:
        pass
    for name in candidates:
        if not isinstance(name, str) or not name or name.startswith((':', '/')):
            continue
        try:
            ZoneInfo(name)
        except (ValueError, ZoneInfoNotFoundError):
            continue
        return name
    return 'UTC'


class _Slots:
    """What one utterance said about the event.  Absent fields stay None."""

    __slots__ = ('title', 'date', 'start', 'end', 'duration', 'residue', 'explicit_title')

    def __init__(self):
        self.title = None
        self.date = None
        self.start = None
        self.end = None
        self.duration = None
        self.residue = ''
        self.explicit_title = False

    def any(self):
        return any(value is not None for value in (self.title, self.date, self.start, self.end, self.duration))


def _clock(h, m, mer):
    """Resolve one clock reading.  A bare 1-6 is read as afternoon and 7-11 as
    morning; both are visible in the preview and cheap to correct."""
    if h > 24 or m > 59:
        return None
    mer = (mer or '').lower().replace('.', '')
    if mer in ('오전', '아침', '새벽', 'am'):
        return (0 if h == 12 else h % 24, m)
    if mer in ('오후', '저녁', '밤', 'pm', '낮'):
        return (12 if h == 12 else (h % 12) + 12, m)
    if h == 24:
        return (0, m)
    if h >= 13 or h == 0 or h == 12:
        return (h, m)
    return (h + 12, m) if h <= 6 else (h, m)


def _times(text):
    """Every clock reading in the text, in order, as (span, (h, m), had_meridiem)."""
    found = []
    for match in _TIME_KO.finditer(text):
        minute = int(match.group('m') or 0) if not match.group('half') else 30
        clock = _clock(int(match.group('h')), minute, match.group('mer'))
        if clock is not None:
            found.append((match.span(), clock, bool(match.group('mer'))))
    for match in _TIME_EN.finditer(text):
        clock = _clock(int(match.group('h')), int(match.group('m') or 0), match.group('mer'))
        if clock is not None:
            found.append((match.span(), clock, True))
    covered = [span for span, _c, _m in found]
    for match in _TIME_24.finditer(text):
        if not any(a <= match.start() < b for a, b in covered):
            found.append((match.span(), (int(match.group('h')), int(match.group('m'))), True))
            covered.append(match.span())
    for match in _TIME_AT.finditer(text):
        if not any(a <= match.start('h') < b for a, b in covered):
            clock = _clock(int(match.group('h')), 0, None)
            if clock is not None:
                found.append(((match.start('h'), match.end('h')), clock, False))
                covered.append(match.span())
    for match in _NOON.finditer(text):
        found.append((match.span(), (12, 0), True))
    for match in _MIDNIGHT.finditer(text):
        found.append((match.span(), (0, 0), True))
    found.sort(key=lambda item: item[0][0])
    return found


def _weekday_target(today, weekday, week, start=None, now=None):
    if week in ('이번주', '이번 주', 'this'):
        base = today - timedelta(days=today.weekday())
        return base + timedelta(days=weekday)
    if week in ('다음주', '다음 주', 'next'):
        base = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return base + timedelta(days=weekday)
    if week in ('다다음주', '다다음 주'):
        base = today - timedelta(days=today.weekday()) + timedelta(days=14)
        return base + timedelta(days=weekday)
    ahead = (weekday - today.weekday()) % 7
    if ahead == 0 and start is not None and now is not None:
        if (start[0], start[1]) <= (now.hour, now.minute):
            ahead = 7
    elif ahead == 0:
        ahead = 7
    return today + timedelta(days=ahead)


def _month_number(name):
    name = name.lower().rstrip('.')
    if name in _MONTHS_EN:
        return _MONTHS_EN.index(name) + 1
    return [month[:3] for month in _MONTHS_EN].index(name[:3]) + 1


def _month_day(today, month, day, year=None):
    try:
        if year is not None:
            return _date(year, month, day)
        candidate = _date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
        try:
            return _date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def parse_event(text, now, start_hint=None):
    """Read title, date, time and duration from one utterance by literal rules.

    ``now`` is an aware datetime in the owner's zone.  Nothing here consults a
    model or any state; the caller merges the result with what it already
    collected.
    """
    slots = _Slots()
    work = ' ' + text.strip() + ' '
    today = now.date()
    cut = []

    def take(span):
        cut.append(span)

    # -- explicit title first, so its words are not mistaken for cues -------
    for pattern in (_TITLE_AMEND_KO, _TITLE_AMEND_EN):
        match = pattern.match(work.strip())
        if match:
            title = match.group('t').strip(' \t"“”\'‘’.,:')
            for particle in ('으로', '로'):
                if title.endswith(particle) and len(title) > len(particle) + 1:
                    title = title[:-len(particle)].strip()
            if title:
                slots.title = title[:_MAX_TITLE]
                slots.explicit_title = True
                slots.residue = ''
                # A title amendment may also carry a time; keep parsing, but
                # nothing outside the title pattern becomes the title.
                work = ' '
                break

    # -- durations, before times, so "1시간" is not read as "1시" ----------
    for pattern in (_DURATION_KO, _DURATION_EN):
        match = pattern.search(work)
        if match:
            groups = match.groupdict()
            if groups.get('an'):
                slots.duration = 30 if 'half' in groups['an'].lower() else 60
            elif groups.get('mo'):
                slots.duration = int(groups['mo'])
            else:
                hours = float(groups['h'])
                minutes = int(round(hours * 60))
                if groups.get('half'):
                    minutes += 30
                elif groups.get('m'):
                    minutes += int(groups['m'])
                slots.duration = minutes
            if slots.duration and 1 <= slots.duration <= 24 * 60:
                work = work[:match.start()] + ' ' + work[match.end():]
            else:
                slots.duration = None
            break

    # -- dates -------------------------------------------------------------
    date_match = None
    for pattern in (_DATE_ISO, _DATE_KO_MD, _DATE_EN_MD, _DATE_EN_DM, _DATE_SLASH):
        match = pattern.search(work)
        if not match:
            continue
        groups = match.groupdict()
        if groups.get('mon'):
            month = _month_number(groups['mon'])
        else:
            month = int(groups['mo'])
        year = int(groups['y']) if groups.get('y') else None
        resolved = _month_day(today, month, int(groups['d']), year) if month else None
        if resolved is not None:
            slots.date, date_match = resolved, match
            break
    if date_match is None:
        for pattern, table in ((_DATE_REL_KO, {'오늘': 0, '내일': 1, '모레': 2, '글피': 3}),
                               (_DATE_REL_EN, {'today': 0, 'tonight': 0, 'tomorrow': 1, 'day after tomorrow': 2})):
            match = pattern.search(work)
            if match:
                slots.date, date_match = today + timedelta(days=table[match.group('w').lower()]), match
                break
    if date_match is None:
        for pattern in (_DATE_IN_DAYS_KO, _DATE_IN_DAYS_EN):
            match = pattern.search(work)
            if match:
                slots.date, date_match = today + timedelta(days=int(match.group('n'))), match
                break
    weekday_match = None
    if date_match is None:
        match = _WEEKDAY_KO.search(work)
        if match:
            weekday = _WEEKDAYS_KO.index(match.group('w'))
            week = (match.group('week') or '').replace(' ', '')
            weekday_match = (match, weekday, week)
        else:
            match = _WEEKDAY_EN.search(work)
            if match:
                name = match.group('w').lower()
                weekday = _WEEKDAYS_EN.index(name) if name in _WEEKDAYS_EN else [w[:3] for w in _WEEKDAYS_EN].index(name[:3])
                week = (match.group('week') or '').lower()
                weekday_match = (match, weekday, 'next' if week == 'next' else 'this' if week == 'this' else '')
    if date_match is not None:
        work = work[:date_match.start()] + ' ' + work[date_match.end():]

    # -- times -------------------------------------------------------------
    readings = _times(work)
    if readings:
        (first_span, first, first_mer) = readings[0]
        slots.start = first
        end_span = None
        if len(readings) >= 2:
            (second_span, second, second_mer) = readings[1]
            between = work[first_span[1]:second_span[0]]
            if _RANGE_SEP.fullmatch(between) or between.strip() == '' or re.fullmatch(r'\s*(?:부터|에서)?\s*', between):
                end = second
                if not second_mer and first_mer:
                    # "오후 3시부터 4시까지": the end inherits the afternoon.
                    # When that lands before the start, the other half of the
                    # day is meant ("오전 11시부터 1시까지", "오후 11시부터 1시까지").
                    raw = readings[1][1][0] % 12
                    end = (raw + 12 if first[0] >= 12 else raw, second[1])
                    if end <= first:
                        end = (raw if first[0] >= 12 else raw + 12, second[1])
                elif end <= first and not second_mer and end[0] < 12:
                    end = (end[0] + 12, end[1])
                # An end that is still not after the start is read as the
                # next day ("오후 11시부터 1시까지"); the preview shows both dates.
                slots.end = end
                end_span = second_span
        spans = [first_span] + ([end_span] if end_span else [])
        for span in sorted(spans, reverse=True):
            work = work[:span[0]] + ' ' + work[span[1]:]
    if weekday_match is not None:
        match, weekday, week = weekday_match
        slots.date = _weekday_target(today, weekday, week, slots.start, now)
        work = work[:match.start()] + ' ' + work[match.end():]

    # -- what is left is the title -----------------------------------------
    slots.residue = _title_from_residue(work) if not slots.explicit_title else ''
    if slots.residue and not slots.explicit_title:
        slots.title = slots.residue
    return slots


def _title_from_residue(work):
    lowered_cut = work
    for cue in sorted(_CALENDAR_FILLER_KO, key=len, reverse=True):
        lowered_cut = lowered_cut.replace(cue, ' ')
    for cue in sorted(_CALENDAR_FILLER_EN, key=len, reverse=True):
        lowered_cut = re.sub(rf'(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])', ' ', lowered_cut, flags=re.I)
    for cue in _CORRECTION_CUES:
        if cue.isascii():
            lowered_cut = re.sub(rf'(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])', ' ', lowered_cut, flags=re.I)
        else:
            lowered_cut = lowered_cut.replace(cue, ' ')
    for marker in _AMEND_MARKERS_KO:
        lowered_cut = lowered_cut.replace(marker, ' ')
    tokens = []
    for token in lowered_cut.split():
        token = token.strip(' \t?!.,;:·"“”‘’()[]')
        if not token:
            continue
        for particle in _TRAILING_PARTICLES:
            if token.endswith(particle) and len(token) > len(particle) + 1 and not token.isascii():
                token = token[:-len(particle)]
                break
        if token in ('에', '로', '으로', '부터', '까지', '쯤', '경', '정도', '그리고', '및', 'and', '&'):
            continue
        tokens.append(token)
    while tokens and tokens[0].casefold() in ('a', 'an', 'the'):
        tokens.pop(0)
    while tokens and tokens[-1].casefold() in ('a', 'an', 'the', 'with', 'and'):
        tokens.pop()
    title = ' '.join(tokens).strip()
    if not title or title.casefold() in _GENERIC_OBJECTS:
        return ''
    return title[:_MAX_TITLE]


def _looks_like_title(text):
    """A short reply with no question or request shape can be a title."""
    value = text.strip(' \t?!.,;:·"“”‘’')
    if not value or len(value) > 60 or '?' in text or '？' in text:
        return False
    lowered = value.casefold()
    if any(lowered.startswith(start) for start in _NOT_A_TITLE_STARTS):
        return False
    if any(lowered.endswith(ending) for ending in _NOT_A_TITLE_ENDINGS):
        return False
    return True


def _tokens(text):
    return [token for token in re.split(r'[\s,.!。！]+', text.strip().casefold()) if token]


def is_approval(text):
    value = re.sub(r'[\s.!。！~]+$', '', text.strip().casefold())
    value = value.strip(' \t"“”\'‘’')
    return value in APPROVE_WORDS


def is_cancel(text):
    value = re.sub(r'[.!。！~]+$', '', text.strip().casefold()).strip(' \t"“”\'‘’')
    if value in CANCEL_WORDS:
        return True
    tokens = _tokens(value)
    if not tokens:
        return False
    vocab = CANCEL_WORDS | _CANCEL_FILLER | {'그게', '아니라', '아니고'}
    return all(token in vocab for token in tokens) and any(token in CANCEL_WORDS for token in tokens)


def _has_correction(text):
    lowered = text.casefold()
    for cue in _CORRECTION_CUES:
        if cue.isascii():
            if re.search(rf'(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])', lowered):
                return True
        elif cue in text:
            return True
    return any(marker in text for marker in _AMEND_MARKERS_KO)


def _after_last_correction(text):
    """Only the words after the last correction cue describe the new intent."""
    best = -1
    lowered = text.casefold()
    for cue in _CORRECTION_CUES:
        index = lowered.rfind(cue.casefold()) if not cue.isascii() else -1
        if cue.isascii():
            for match in re.finditer(rf'(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])', lowered):
                index = max(index, match.end())
        elif index >= 0:
            index += len(cue)
        best = max(best, index)
    return text[best:] if best > 0 else text


class CalendarConversation:
    """Slot collection, exact preview and owner approval for one create.

    ``connector_for(owner_id)`` returns the owner-bound ``CalendarConnector``
    or None.  It is resolved per turn because the service builds one per
    connector identity.
    """

    def __init__(self, store, connector_for, *, now=time.time, timezone=None,
                 ttl_seconds=PENDING_TTL_SECONDS):
        self.store = store
        self.connector_for = connector_for
        self.now = now
        self._timezone = timezone
        self.ttl_seconds = ttl_seconds

    # -- state ----------------------------------------------------------------
    def timezone(self):
        if callable(self._timezone):
            return self._timezone()
        return self._timezone or resolve_local_timezone(self.store)

    def _local_now(self):
        return datetime.fromtimestamp(float(self.now()), ZoneInfo(self.timezone()))

    def pending(self):
        row = self.store.config(STATE_KEY, None)
        if not isinstance(row, dict) or row.get('state') not in (STATE_COLLECTING, STATE_AWAITING_APPROVAL):
            return None
        if float(row.get('expires', 0) or 0) <= float(self.now()):
            self.clear()
            return None
        return row

    def has_pending(self):
        return self.pending() is not None

    def clear(self):
        previous = self.store.config(STATE_KEY, None)
        self.store.put(STATE_KEY, {})
        return previous if isinstance(previous, dict) and previous.get('state') else None

    def _save(self, owner_id, state, slots, draft_id='', payload_hash=''):
        row = {'owner': _owner_key(owner_id), 'state': state, 'slots': slots, 'draft_id': draft_id,
               'payload_hash': payload_hash, 'at': float(self.now()),
               'expires': float(self.now()) + self.ttl_seconds}
        self.store.put(STATE_KEY, row)
        return row

    @staticmethod
    def _owned(row, owner_id):
        return isinstance(row, dict) and row.get('owner') == _owner_key(owner_id)

    # -- routing ------------------------------------------------------------------
    def claims(self, owner_id, text):
        """Whether a cue-free utterance belongs to the pending calendar turn.

        The classifier routes every cue-free utterance here while a draft is
        pending; this is the check that keeps "오늘 날씨 어때?" from being
        swallowed as a title or a date correction.
        """
        row = self.pending()
        if row is None:
            return False
        if is_approval(text) or is_cancel(text):
            return True
        if not self._owned(row, owner_id):
            return False
        slots = parse_event(_after_last_correction(text) if _has_correction(text) else text, self._local_now())
        if slots.explicit_title:
            return True
        # Whatever is left after the date/time/duration words must itself be
        # a plausible title, or the utterance is about something else.
        clean_residue = not slots.residue or _looks_like_title(slots.residue)
        if row['state'] == STATE_AWAITING_APPROVAL:
            if _has_correction(text):
                return clean_residue and (slots.any() or bool(slots.residue))
            # Without a correction cue, only an utterance that is nothing but
            # a new value ("4시로", "오후 4시", "2시간") amends the draft.
            return slots.any() and not slots.residue
        collected = row.get('slots') or {}
        if not collected.get('title'):
            if slots.start is not None or slots.date is not None or slots.duration is not None:
                return clean_residue
            return _looks_like_title(text) and bool(slots.residue)
        return (slots.start is not None or slots.date is not None or slots.duration is not None) and not slots.residue

    # -- the turn -----------------------------------------------------------------
    def handle(self, owner_id, text, *, fresh, evidence=None):
        """Answer one calendar turn.  ``fresh`` is a new create request; the
        alternative is a follow-up the classifier routed here while a draft
        was pending, which the caller has already checked with ``claims``."""
        row = self.pending()
        notice = ''
        if fresh:
            if row is not None:
                self.clear()
                notice = REPLACED_NOTICE + '\n\n'
            tail = _after_last_correction(text) if _has_correction(text) else text
            slots = self._merge({}, parse_event(tail, self._local_now()))
            return notice + self._advance(owner_id, slots, evidence)
        if row is None:
            return NOTHING_PENDING
        if is_cancel(text):
            # Cancelling creates nothing, so either channel may do it.
            self.clear()
            return CANCELLED
        if not self._owned(row, owner_id):
            # Ownership is checked before anything is written: the other
            # channel may neither approve nor take over a half-collected
            # request.
            return OTHER_CHANNEL
        if is_approval(text):
            if row['state'] != STATE_AWAITING_APPROVAL:
                # "네" while a detail is still missing is not an approval of
                # anything; ask again for the detail.
                return self._advance(owner_id, row.get('slots') or {}, evidence)
            return self._approve(owner_id, row, evidence)
        parsed = parse_event(_after_last_correction(text) if _has_correction(text) else text, self._local_now())
        collected = dict(row.get('slots') or {})
        if row['state'] == STATE_COLLECTING and not collected.get('title') and not parsed.explicit_title \
                and parsed.start is None and parsed.date is None and _looks_like_title(text):
            parsed.title = _title_from_residue(' ' + text + ' ') or text.strip()[:_MAX_TITLE]
            parsed.explicit_title = True
        if row['state'] == STATE_AWAITING_APPROVAL and _has_correction(text) and not parsed.explicit_title \
                and parsed.residue and _looks_like_title(parsed.residue):
            parsed.explicit_title = True
        slots = self._merge(collected, parsed)
        return self._advance(owner_id, slots, evidence)

    @staticmethod
    def _merge(collected, parsed):
        slots = dict(collected)
        if parsed.explicit_title or (parsed.title and not slots.get('title')):
            slots['title'] = parsed.title
        if parsed.date is not None:
            slots['date'] = parsed.date.isoformat()
        if parsed.start is not None:
            slots['start'] = list(parsed.start)
            # A new start without a new end invalidates the old end.
            slots.pop('end', None)
        if parsed.end is not None:
            slots['end'] = list(parsed.end)
            slots.pop('duration', None)
        if parsed.duration is not None:
            slots['duration'] = parsed.duration
            slots.pop('end', None)
        return slots

    def _advance(self, owner_id, slots, evidence):
        """Ask for the one missing detail, or draft and show the preview."""
        if not slots.get('title'):
            self._save(owner_id, STATE_COLLECTING, slots)
            return ASK_TITLE
        if slots.get('start') is None and slots.get('date') is None:
            self._save(owner_id, STATE_COLLECTING, slots)
            return ASK_WHEN
        if slots.get('start') is None:
            self._save(owner_id, STATE_COLLECTING, slots)
            return ASK_TIME
        if slots.get('date') is None:
            self._save(owner_id, STATE_COLLECTING, slots)
            return ASK_DATE
        zone = self.timezone()
        start = datetime.combine(_date.fromisoformat(slots['date']), datetime.min.time(),
                                 tzinfo=ZoneInfo(zone)).replace(hour=slots['start'][0], minute=slots['start'][1])
        if slots.get('end') is not None:
            end = start.replace(hour=slots['end'][0], minute=slots['end'][1])
            if end <= start:
                end += timedelta(days=1)
        else:
            end = start + timedelta(minutes=slots.get('duration') or DEFAULT_DURATION_MINUTES)
        payload = {'summary': slots['title'], 'start': start.isoformat(timespec='seconds'),
                   'end': end.isoformat(timespec='seconds'), 'timezone': zone}
        connector = self.connector_for(owner_id)
        if connector is None:
            self.clear()
            raise CalendarError('unavailable')
        preview = connector.draft_create(payload, owner_id)
        self._save(owner_id, STATE_AWAITING_APPROVAL, slots, preview['id'], preview['payload_hash'])
        if evidence is not None:
            evidence('calendar_draft', 'succeeded', {'draft_id': preview['id'], 'state': preview['state'],
                                                    'payload_hash': preview['payload_hash'][:12]})
        return self._preview_text(preview['payload'])

    def _preview_text(self, payload):
        return '\n'.join((PREVIEW_HEADER,
                          f"제목: {payload['summary']}",
                          f"일시: {self._describe(payload['start'], payload['end'], payload['timezone'])}",
                          '캘린더: Google 기본 캘린더',
                          PREVIEW_FOOTER))

    @staticmethod
    def _describe(start, end, zone):
        first = datetime.fromisoformat(start)
        last = datetime.fromisoformat(end)
        day = f"{first:%Y-%m-%d} ({_WEEKDAYS_KO[first.weekday()]})"
        if last.date() == first.date():
            return f"{day} {first:%H:%M} – {last:%H:%M} ({zone})"
        return f"{day} {first:%H:%M} – {last:%Y-%m-%d} ({_WEEKDAYS_KO[last.weekday()]}) {last:%H:%M} ({zone})"

    def _approve(self, owner_id, row, evidence):
        connector = self.connector_for(owner_id)
        if connector is None:
            self.clear()
            raise CalendarError('unavailable')
        draft_id = row.get('draft_id')
        try:
            preview = connector.preview(draft_id, owner_id)
        except CalendarError:
            self.clear()
            return CHANGED_UNDER_US
        if preview['state'] != 'awaiting-approval' or preview['payload_hash'] != row.get('payload_hash'):
            self.clear()
            return CHANGED_UNDER_US
        # The pending record is dropped *before* dispatch.  The worker is
        # serialised, so this alone makes a second "승인" find nothing; the
        # connector's own approved/executing/completed states are the second
        # and third barriers and are not weakened here.
        self.clear()
        try:
            approval = connector.approve(draft_id, owner_id)
            result = connector.execute(draft_id, approval['approval_id'], owner_id)
        except CalendarError as error:
            if evidence is not None:
                evidence('calendar_create', 'failed', {'draft_id': draft_id, 'error': error.reason,
                                                       'effect': error.effect, 'recovery': error.recovery})
            if error.effect == 'unknown':
                return OUTCOME_UNKNOWN
            hint = RECONNECT_HINT if 'reconnect' in (error.recovery or '') else RETRY_HINT
            return FAILED + hint
        if evidence is not None:
            evidence('calendar_create', 'succeeded', {'draft_id': draft_id, 'event_id': result.get('id', ''),
                                                      'effect': 'observed'})
        payload = preview['payload']
        return '\n'.join((CREATED, f"제목: {payload['summary']}",
                          f"일시: {self._describe(payload['start'], payload['end'], payload['timezone'])}"))
