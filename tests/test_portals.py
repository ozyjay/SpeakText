from __future__ import annotations

import unittest

from speaktext.portals import PortalRequestRunner


class FakeConnection:
    def get_unique_name(self) -> str:
        return ":1.245"


class PortalTests(unittest.TestCase):
    def test_request_path_uses_dbus_unique_name(self) -> None:
        runner = PortalRequestRunner(FakeConnection())  # type: ignore[arg-type]
        self.assertEqual(
            runner.request_path("token"),
            "/org/freedesktop/portal/desktop/request/1_245/token",
        )


if __name__ == "__main__":
    unittest.main()

