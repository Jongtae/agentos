"""Sandbox-only import guard: no PyObjC, so no WebKit window can reach the owner's screen.

The eval launcher puts this folder first on ``PYTHONPATH`` of every sandbox
AgentOS process (and the browser worker inherits it).  AgentOS already treats
missing PyObjC as "embedded browser unavailable"
(``browser_session.webkit_unavailable_reason``), so the sandbox runs its
normal code path without a window.  Not used by the owner's live server.
"""
import sys

BLOCKED = frozenset({'objc', 'AppKit', 'WebKit', 'Foundation', 'Cocoa', 'Quartz', 'PyObjCTools'})


class _NoPyObjC:
    @staticmethod
    def find_spec(name, path=None, target=None):
        if name.split('.', 1)[0] in BLOCKED:
            raise ImportError(f'{name} is disabled in AgentOS eval sandboxes')
        return None


sys.meta_path.insert(0, _NoPyObjC())
