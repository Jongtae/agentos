"""Validation for owner folder grants (AI read folders and file-workspace folders).

One rule set for both entry points, so a folder refused in one place is refused in
the other, and stored grants that later fall outside the rules are blocked at use
time instead of silently widening access.

Folders are compared by filesystem identity (device and inode of the folder and its
ancestors) as well as by case-folded path, so case-insensitive volumes, firmlinks and
alternative spellings cannot reach a protected folder. The sensitive list is
best-effort: it covers common credential, key, browser and system locations, and the
read-time guards (no dot-files, no symlinks, no escaping the root) remain the second
layer.
"""
import os
from pathlib import Path

# Credential, key and app-data stores under the owner's home. A grant may not be one
# of these, live inside one, or contain one.
_HOME_SENSITIVE = (
    '.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.password-store', '.gnome-keyring',
    '.terraform.d', '.mozilla', '.config/gcloud', '.config/gh', '.config/google-chrome',
    '.config/chromium', '.local/share/keyrings',
    'Library/Keychains', 'Library/Cookies', 'Library/Mail', 'Library/Messages', 'Library/Safari',
    'Library/Containers', 'Library/Group Containers', 'Library/Application Support',
)
# System configuration and binaries. Temporary folders stay allowed.
_SYSTEM_SENSITIVE = (
    '/etc', '/private/etc', '/System', '/usr', '/bin', '/sbin', '/dev', '/proc', '/sys',
    '/boot', '/root', '/var/root', '/private/var/root', '/Library/Keychains', '/var/db',
    '/private/var/db', '/var/lib',
)

BROAD = '전체 홈이나 시스템 루트 대신 작업용 하위 폴더를 선택하세요'
SENSITIVE = '인증 정보나 시스템 설정이 있는 폴더는 연결할 수 없습니다'
SYMLINK_CHANGED = '연결한 폴더가 심볼릭 링크로 바뀌어 다시 연결해야 합니다'
UNAVAILABLE = '연결한 폴더를 현재 사용할 수 없습니다'


def _identity(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


def _chain(path):
    """Identities of an existing path and every ancestor."""
    return {identity for identity in map(_identity, (path, *path.parents)) if identity}


def _folded(path):
    return Path(os.path.normcase(str(path)).casefold())


def _case_insensitive(path):
    """Whether an existing path's volume aliases a component with changed case."""
    for candidate in (path, *path.parents):
        if not candidate.exists():
            continue
        for index, character in enumerate(candidate.name):
            if not character.isalpha():
                continue
            alternate_name = (candidate.name[:index] + character.swapcase() + candidate.name[index + 1:])
            alternate = candidate.with_name(alternate_name)
            try:
                if alternate.exists() and os.path.samefile(candidate, alternate):
                    return True
            except OSError:
                continue
    return False


def _related(path, path_chain, other, case_insensitive):
    """True when path is other, lies inside it, or contains it (identity or case-folded name)."""
    other_id = _identity(other)
    other_chain = _chain(other) | _chain(other.resolve())
    if other_id and (other_id in path_chain or _identity(path) in other_chain):
        return True
    if case_insensitive:
        mine = _folded(path)
        return any(mine.is_relative_to(form) or form.is_relative_to(mine) for form in {_folded(other), _folded(other.resolve())})
    return False


def _sensitive_paths():
    home = Path.home()
    return [home / item for item in _HOME_SENSITIVE] + [Path(item) for item in _SYSTEM_SENSITIVE]


def refusal(path, store):
    """Why an existing, resolved directory may not be granted, or None."""
    chain = _chain(path)
    own = _identity(path)
    home = Path.home().resolve()
    if own is None:
        return None
    case_insensitive = _case_insensitive(path)
    if (own == _identity(Path('/')) or own == _identity(store.root) or own in _chain(home)
            or (case_insensitive and _folded(home).is_relative_to(_folded(path)))
            or _related(path, chain, store.private, case_insensitive)):
        return BROAD
    if any(_related(path, chain, item, case_insensitive) for item in _sensitive_paths()):
        return SENSITIVE
    return None


def validate(value, store):
    """Return the resolved folder for an owner-supplied path or raise ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('폴더 경로를 입력하세요.')
    text = value.strip()
    try:
        supplied = Path(text).expanduser()
    except (RuntimeError, OSError):
        raise ValueError(f'폴더 경로를 확인할 수 없습니다: {text}') from None
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
    """Reason a previously stored grant must not be used now, or None.

    Re-check the *stored path* before resolving it. A directory that was
    originally granted and later replaced by a symlink must not inherit the
    old grant for its new target, even when that target is otherwise allowed.
    """
    try:
        supplied = Path(stored_path).expanduser()
        if not supplied.is_absolute():
            return UNAVAILABLE
        if any(part.is_symlink() for part in (supplied, *supplied.parents)):
            return SYMLINK_CHANGED
        if not supplied.exists() or not supplied.is_dir():
            return UNAVAILABLE
        path = supplied.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return UNAVAILABLE
    return refusal(path, store)
