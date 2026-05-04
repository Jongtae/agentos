from __future__ import annotations

import os
import unittest

import config


class ConfigWorkspacePathTests(unittest.TestCase):
    def test_agentos_default_workspace_env_takes_precedence(self) -> None:
        old_agentos = os.environ.get("AGENTOS_DEFAULT_WORKSPACE")
        old_legacy = os.environ.get("DEFAULT_WORKSPACE")
        try:
            os.environ["AGENTOS_DEFAULT_WORKSPACE"] = "/tmp/agentos-ws"
            os.environ["DEFAULT_WORKSPACE"] = "/tmp/legacy-ws"
            self.assertEqual(config.get_workspace_path(), "/tmp/agentos-ws")
        finally:
            if old_agentos is None:
                os.environ.pop("AGENTOS_DEFAULT_WORKSPACE", None)
            else:
                os.environ["AGENTOS_DEFAULT_WORKSPACE"] = old_agentos
            if old_legacy is None:
                os.environ.pop("DEFAULT_WORKSPACE", None)
            else:
                os.environ["DEFAULT_WORKSPACE"] = old_legacy

    def test_installed_runtime_defaults_to_user_workspace(self) -> None:
        old_agentos = os.environ.get("AGENTOS_DEFAULT_WORKSPACE")
        old_legacy = os.environ.get("DEFAULT_WORKSPACE")
        old_home = os.environ.get("HOME")
        old_file = config.__file__
        try:
            os.environ.pop("AGENTOS_DEFAULT_WORKSPACE", None)
            os.environ.pop("DEFAULT_WORKSPACE", None)
            os.environ["HOME"] = "/home/ubuntu"
            config.__file__ = "/usr/lib/agentos/src/config.py"
            self.assertEqual(config.get_workspace_path(), "/home/ubuntu/agentos-ws")
        finally:
            config.__file__ = old_file
            if old_agentos is None:
                os.environ.pop("AGENTOS_DEFAULT_WORKSPACE", None)
            else:
                os.environ["AGENTOS_DEFAULT_WORKSPACE"] = old_agentos
            if old_legacy is None:
                os.environ.pop("DEFAULT_WORKSPACE", None)
            else:
                os.environ["DEFAULT_WORKSPACE"] = old_legacy
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
