import os
from pathlib import Path
import subprocess
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
PATH_SCRIPT = PROJECT_DIR / "scripts" / "user-install-paths.sh"


class UserInstallPathTests(unittest.TestCase):
    def resolve_paths(self, **environment):
        env = {"HOME": "/home/tester", **environment}
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$1"; printf "%s\\n%s\\n" '
                '"$speaktext_user_home" "$speaktext_data_home"',
                "bash",
                str(PATH_SCRIPT),
            ],
            check=True,
            capture_output=True,
            env=env,
            text=True,
        )
        return result.stdout.splitlines(), result.stderr

    def test_preserves_an_ordinary_xdg_data_home(self):
        paths, warning = self.resolve_paths(XDG_DATA_HOME="/tmp/custom-data")

        self.assertEqual(paths, ["/home/tester", "/tmp/custom-data"])
        self.assertEqual(warning, "")

    def test_replaces_snap_private_xdg_data_home(self):
        paths, warning = self.resolve_paths(
            XDG_DATA_HOME="/home/tester/snap/code/253/.local/share",
            SNAP_REAL_HOME="/home/tester",
            SNAP_USER_DATA="/home/tester/snap/code/253",
        )

        self.assertEqual(
            paths,
            ["/home/tester", "/home/tester/.local/share"],
        )
        self.assertIn("Ignoring Snap-private XDG_DATA_HOME", warning)

    def test_preserves_a_host_xdg_data_home_in_a_snap_environment(self):
        paths, warning = self.resolve_paths(
            XDG_DATA_HOME="/srv/tester-data",
            SNAP_REAL_HOME="/home/tester",
            SNAP_USER_DATA="/home/tester/snap/code/253",
        )

        self.assertEqual(paths, ["/home/tester", "/srv/tester-data"])
        self.assertEqual(warning, "")


if __name__ == "__main__":
    unittest.main()
