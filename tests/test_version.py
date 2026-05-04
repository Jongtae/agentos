from __future__ import annotations

import re
import unittest

from version import APP_VERSION


class VersionTests(unittest.TestCase):
    def test_app_version_is_semver(self):
        self.assertRegex(APP_VERSION, r"^[0-9]+\.[0-9]+\.[0-9]+$")


if __name__ == "__main__":
    unittest.main()
