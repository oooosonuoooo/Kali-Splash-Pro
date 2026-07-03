import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import manager, player  # noqa: E402


XRANDR_OUTPUT = """Monitors: 2
 0: +*HDMI-0 1680/444x1050/278+0+0  HDMI-0
 1: +DP-1 1920/520x1080/290+1680+0  DP-1
"""


class DesktopExecParsingTests(unittest.TestCase):
    def test_extracts_quoted_python_script_with_spaces(self):
        line = 'Exec=/usr/bin/python3 "/tmp/New Folder/Kali-Splash-Pro/src/player.py"'

        self.assertEqual(
            manager.extract_exec_script_path(line),
            "/tmp/New Folder/Kali-Splash-Pro/src/player.py",
        )

    def test_extracts_direct_script_exec(self):
        line = 'Exec="/tmp/New Folder/Kali-Splash-Pro/src/player.py"'

        self.assertEqual(
            manager.extract_exec_script_path(line),
            "/tmp/New Folder/Kali-Splash-Pro/src/player.py",
        )

    def test_autostart_must_point_to_current_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "current" / "src" / "player.py"
            stale = Path(tmp) / "stale" / "src" / "player.py"
            autostart = Path(tmp) / "kali-splash-startup.desktop"
            current.parent.mkdir(parents=True)
            stale.parent.mkdir(parents=True)
            current.write_text("# current\n", encoding="utf-8")
            stale.write_text("# stale\n", encoding="utf-8")
            autostart.write_text(
                f'Exec=/usr/bin/python3 "{stale}"\n',
                encoding="utf-8",
            )

            with mock.patch.object(manager, "AUTOSTART_FILE", str(autostart)):
                with mock.patch.object(manager, "PLAYER_SCRIPT", str(current)):
                    self.assertFalse(manager.autostart_path_is_valid())


class MonitorParsingTests(unittest.TestCase):
    def test_manager_parses_xrandr_monitor_names(self):
        self.assertEqual(manager.parse_xrandr_monitors(XRANDR_OUTPUT), ["HDMI-0", "DP-1"])

    def test_player_parses_xrandr_screen_indices(self):
        self.assertEqual(
            player.parse_monitor_indices(XRANDR_OUTPUT),
            {"HDMI-0": "0", "DP-1": "1"},
        )


class PlayerLockTests(unittest.TestCase):
    def test_duplicate_lock_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "kali-splash.lock")
            with mock.patch.object(player, "LOCK_FILE", lock_path):
                self.assertTrue(player.acquire_lock())
                try:
                    self.assertFalse(player.acquire_lock())
                finally:
                    player.release_lock()


if __name__ == "__main__":
    unittest.main()
