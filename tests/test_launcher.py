from pathlib import Path
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_DIR / "scripts" / "speaktext-launcher"


class LauncherTests(unittest.TestCase):
    def test_launcher_is_a_direct_python_entry_point(self):
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertTrue(source.startswith("#!/usr/bin/python3\n"))
        compile(source, str(LAUNCHER), "exec")
        self.assertNotIn("pwsh", source)
        self.assertNotIn("bash", source)

    def test_snap_launches_delegate_to_dbus_activation(self):
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('os.environ.get("SNAP")', source)
        self.assertIn('["/usr/bin/gapplication", "launch", APP_ID]', source)


if __name__ == "__main__":
    unittest.main()
