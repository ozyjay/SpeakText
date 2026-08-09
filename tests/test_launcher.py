from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


PROJECT_DIR = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_DIR / "scripts" / "speaktext-launcher"
INSTALLER = PROJECT_DIR / "scripts" / "install-user.ps1"
UNINSTALLER = PROJECT_DIR / "scripts" / "uninstall-user.ps1"
IBUS_COMPONENT = PROJECT_DIR / "data" / "local.SpeakText.ibus.xml.in"


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

    def test_launcher_can_report_its_build_identity(self):
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('sys.argv[1:] == ["--build-id"]', source)
        self.assertIn("from speaktext.build_info import BUILD_LABEL", source)

    def test_installer_embeds_an_installed_build_label(self):
        source = INSTALLER.read_text(encoding="utf-8")

        self.assertIn('Join-Path $pythonPackageDir "build_info.py"', source)
        self.assertIn('BUILD_LABEL = "Installed build: $buildRevision"', source)

    def test_installer_adds_ibus_source_without_replacing_layouts(self):
        source = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("SPEAKTEXT_SKIP_INPUT_SOURCE", source)
        self.assertIn("$entries, ('ibus', 'speaktext')", source)
        self.assertIn("SpeakText input source already configured", source)

    def test_ibus_component_is_discoverable_and_installed(self):
        root = ET.parse(IBUS_COMPONENT).getroot()
        installer = INSTALLER.read_text(encoding="utf-8")

        self.assertEqual(root.findtext("name"), "local.SpeakText.IBus")
        self.assertEqual(root.findtext("engines/engine/name"), "speaktext")
        self.assertEqual(root.findtext("exec"), "@EXEC@")
        self.assertIn('Join-Path $dataHome "ibus/component"', installer)
        self.assertIn("write-cache", installer)
        self.assertIn('ibus/component/local.SpeakText.xml', UNINSTALLER.read_text())


if __name__ == "__main__":
    unittest.main()
