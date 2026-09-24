"""Validation for owner folder grants (AI read folders and file-workspace folders).

One rule set for both entry points, so a folder refused in one place is refused in
the other, and stored grants that later fall outside the rules are blocked at use
time instead of silently widening access.
"""
from pathlib import Path

# Credential and key stores under the owner's home. A grant may not be one of these,
# live inside one, or contain one.
_HOME_SENSITIVE = (
    '.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.password-store',
    '.config/gcloud', '.config/gh', '.local/share/keyrings',
    'Library/Keychains', 'Library/Cookies', 'Library/Mail', 'Library/Messages',
    'Library/Application Support',
)
# System configuration and binaries. Temporary folders stay allowed.
_SYSTEM_SENSITIVE = (
    '/etc', '/private/etc', '/System', '/usr', '/bin', '/sbin', '/dev', '/proc', '/sys',
    '/boot', '/root', '/Library/Keychains', '/var/db', '/private/var/db', '/var/lib',
)

BROAD = '전체 홈이나 시스템 루트 대신 작업용 하위 폴더를 선택하세요'
SENSITIVE = '인증 정보나 시스템 설정이 있는 폴더는 연결할 수 없습니다'


def _sensitive_paths():
    home = Path.home()
    candidates = [home / item for item in _HOME_SENSITIVE] + [Path(item) for item in _SYSTEM_SENSITIVE]
    return {form for path in candidates for form in (path, path.resolve())}


def refusal(path, store):
    """Why an existing, resolved directory may not be granted, or None."""
    home = Path.home().resolve()
    if (path in (Path('/'), home, store.root.resolve()) or home.is_relative_to(path)
            or path.is_relative_to(store.private.resolve()) or store.private.resolve().is_relative_to(path)):
        return BROAD
    if any(path == item or path.is_relative_to(item) or item.is_relative_to(path) for item in _sensitive_paths()):
        return SENSITIVE
    return None


def validate(value, store):
    """Return the resolved folder for an owner-supplied path or raise ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('폴더 경로를 입력하세요.')
    text = value.strip()
    supplied = Path(text).expanduser()
    if not supplied.is_absolute():
        raise ValueError(f'/로 시작하는 전체 경로를 입력하세요: {text}')
    if supplied.is_symlink():
        raise ValueError(f'심볼릭 링크 대신 실제 폴더 경로를 입력하세요: {text}')
    if not supplied.exists():
        raise ValueError(f'폴더를 찾을 수 없습니다: {text}')
    path = supplied.resolve()
    if not path.is_dir():
        raise ValueError(f'폴더가 아닙니다: {text}')
    reason = refusal(path, store)
    if reason:
        raise ValueError(f'{reason}: {text}')
    return path


def blocked(stored_path, store):
    """Reason a previously stored grant must not be used now, or None."""
    try:
        path = Path(stored_path).resolve()
    except (OSError, RuntimeError, TypeError):
        return BROAD
    return refusal(path, store)
