"""Owner-local native folder selection on the Mac (PRESENCE-CAP-01 / #505).

The folder a contextual handoff grants is chosen here, on the owner's own
machine, through the platform's standard folder dialog: AppleScript's
``choose folder`` (Standard Additions, backed by the system open panel), run
by ``/usr/bin/osascript``.  Nothing is installed and no dependency is added.

This module only returns the path the owner picked, or ``None`` when the
owner cancelled.  It grants nothing: the caller validates the path with the
shared ``folder_grants`` rules and asks for an explicit approval before any
grant is written.  The prompt is passed as an argument, never interpolated
into script source, so no request text can become AppleScript.
"""
import subprocess
import sys
import threading
from pathlib import Path

OSASCRIPT = Path('/usr/bin/osascript')
PICKER_TIMEOUT_SECONDS = 300
_SCRIPT = ('on run argv',
           'activate',
           'return POSIX path of (choose folder with prompt (item 1 of argv))',
           'end run')
#: AppleScript's "User canceled." error number.
_CANCELLED = '-128'

_LOCK = threading.Lock()


class FolderPickerUnavailable(ValueError):
    """No native folder dialog can be shown on this machine."""


class FolderPickerBusy(ValueError):
    """A folder dialog is already open."""


def available():
    return sys.platform == 'darwin' and OSASCRIPT.exists()


def choose_folder(prompt, *, runner=subprocess.run, timeout=PICKER_TIMEOUT_SECONDS):
    """Show one native folder dialog and return the chosen POSIX path or None."""
    if runner is subprocess.run and not available():
        raise FolderPickerUnavailable('이 컴퓨터에서는 폴더 선택 창을 열 수 없습니다.')
    if not _LOCK.acquire(blocking=False):
        raise FolderPickerBusy('이미 폴더 선택 창이 열려 있습니다. 먼저 그 창을 닫아 주세요.')
    try:
        command = [str(OSASCRIPT)]
        for line in _SCRIPT:
            command += ['-e', line]
        command.append(str(prompt))
        try:
            result = runner(command, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return None
        except OSError:
            raise FolderPickerUnavailable('이 컴퓨터에서는 폴더 선택 창을 열 수 없습니다.') from None
        if result.returncode != 0:
            if _CANCELLED in (result.stderr or ''):
                return None
            raise FolderPickerUnavailable('폴더 선택 창을 열지 못했습니다.')
        chosen = (result.stdout or '').strip()
        return chosen or None
    finally:
        _LOCK.release()
