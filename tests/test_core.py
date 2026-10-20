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


class ManagerFilePickerTests(unittest.TestCase):
    def test_zenity_multi_select_output_is_split_into_paths(self):
        result = mock.Mock(returncode=0, stdout="/tmp/one.mp4\n/tmp/two.MP4\n")

        with mock.patch.object(manager.shutil, "which", return_value="/usr/bin/zenity"):
            with mock.patch.object(manager.subprocess, "run", return_value=result) as run:
                self.assertEqual(
                    manager.select_video_files("Add videos"),
                    ["/tmp/one.mp4", "/tmp/two.MP4"],
                )
                args = run.call_args.args[0]
                self.assertIn("--multiple", args)
                self.assertIn("--separator=\n", args)

    def test_zenity_cancel_returns_empty_list_without_tk_fallback(self):
        result = mock.Mock(returncode=1, stdout="")

        with mock.patch.object(manager.shutil, "which", return_value="/usr/bin/zenity"):
            with mock.patch.object(manager.subprocess, "run", return_value=result):
                with mock.patch.object(manager.filedialog, "askopenfilenames") as fallback:
                    self.assertEqual(manager.select_video_files("Add videos"), [])
                    fallback.assert_not_called()

    def test_file_picker_uses_tk_fallback_without_zenity(self):
        with mock.patch.object(manager.shutil, "which", return_value=None):
            with mock.patch.object(
                manager.filedialog,
                "askopenfilenames",
                return_value=("/tmp/one.mp4", "/tmp/two.mp4"),
            ) as fallback:
                self.assertEqual(
                    manager.select_video_files("Add videos"),
                    ["/tmp/one.mp4", "/tmp/two.mp4"],
                )
                fallback.assert_called_once()

    def test_folder_scan_returns_all_supported_files_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = [f"clip-{index:02}.mkv" for index in range(12)]
            names += ["special.MP4", "space name.WebM", "extra.3GP"]
            for name in names:
                (folder / name).touch()
            (folder / "readme.txt").touch()
            nested = folder / "nested"
            nested.mkdir()
            (nested / "not-recursive.mp4").touch()

            found = manager.list_video_files(str(folder))

            self.assertEqual(len(found), len(names))
            self.assertEqual(
                {Path(path).name for path in found},
                set(names),
            )

    def test_append_videos_adds_large_batch_and_scrolls_to_end(self):
        class FakeListbox:
            def __init__(self):
                self.items = []
                self.last_selection = None
                self.last_scrolled = None

            def size(self):
                return len(self.items)

            def get(self, index):
                return self.items[index]

            def insert(self, index, value):
                self.items.append(value)

            def selection_clear(self, *_args):
                pass

            def selection_set(self, start, end):
                self.last_selection = (start, end)

            def see(self, index):
                self.last_scrolled = index

        listbox = FakeListbox()
        manager_state = type("ManagerHarness", (), {})()
        manager_state._monitor_states = {"HDMI-0": {"listbox": listbox}}
        manager_state._show_toast = mock.Mock()
        batch = [f"/tmp/video-{index}.mkv" for index in range(21)]

        added = manager.KaliSplashManager._append_videos(
            manager_state, "HDMI-0", batch
        )

        self.assertEqual(added, 21)
        self.assertEqual(listbox.size(), 21)
        self.assertEqual(listbox.last_selection, (0, "end"))
        self.assertEqual(listbox.last_scrolled, "end")

    def test_save_keeps_missing_paths_and_other_playlist_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "available.mp4"
            existing.touch()
            missing = str(Path(tmp) / "old-location.mp4")

            class Listbox:
                def size(self):
                    return 2

                def get(self, index):
                    return [missing, str(existing)][index]

            class SaveHarness:
                _playlist_for_monitor = manager.KaliSplashManager._playlist_for_monitor

                def __init__(self):
                    self._monitor_states = {
                        "HDMI-0": {
                            "listbox": Listbox(),
                            "shuffle": mock.Mock(get=mock.Mock(return_value=False)),
                        }
                    }
                    self._show_toast = mock.Mock()
                    self._refresh_status = mock.Mock()

            harness = SaveHarness()
            with mock.patch.object(manager, "load_config", return_value={}):
                with mock.patch.object(manager, "save_config", return_value=True) as save:
                    self.assertTrue(manager.KaliSplashManager._save_all(harness))

            saved = save.call_args.args[0]["HDMI-0"]["videos"]
            self.assertEqual(saved, [missing, str(existing)])
            harness._show_toast.assert_called_once_with(
                "Config saved; kept 1 unavailable path(s)."
            )


class MonitorParsingTests(unittest.TestCase):
    def test_manager_parses_xrandr_monitor_names(self):
        self.assertEqual(manager.parse_xrandr_monitors(XRANDR_OUTPUT), ["HDMI-0", "DP-1"])

    def test_player_parses_xrandr_screen_indices(self):
        self.assertEqual(
            player.parse_monitor_indices(XRANDR_OUTPUT),
            {"HDMI-0": "0", "DP-1": "1"},
        )


class PlayerPlaylistTests(unittest.TestCase):
    def test_mpv_command_uses_gpu_rendering_and_available_hardware_decode(self):
        command = player.build_mpv_command("/tmp/my video.mkv", "1")

        self.assertIn("--vo=gpu", command)
        self.assertIn("--gpu-api=opengl", command)
        self.assertIn("--hwdec=auto", command)
        self.assertIn("--fs-screen=1", command)
        self.assertEqual(command[-1], "/tmp/my video.mkv")

    def test_playback_uses_optimized_copy_when_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mkv"
            cache = Path(tmp) / "cache"
            source.touch()
            with mock.patch.object(player, "VIDEO_CACHE_DIR", str(cache)):
                self.assertEqual(player.resolve_playback_path(str(source)), str(source))
                optimized = Path(player.optimized_video_cache_path(str(source)))
                optimized.parent.mkdir(parents=True)
                optimized.write_bytes(b"optimized")

                self.assertEqual(
                    player.resolve_playback_path(str(source)), str(optimized)
                )

    def test_legacy_string_normalizes_to_single_video_without_shuffle(self):
        self.assertEqual(
            player.normalize_monitor_config("/tmp/splash.mp4"),
            {"videos": ["/tmp/splash.mp4"], "shuffle": False},
        )

    def test_playlist_dict_normalizes_videos_and_shuffle(self):
        self.assertEqual(
            player.normalize_monitor_config({
                "videos": [" /tmp/one.mp4 ", "/tmp/two.mkv", 12, ""],
                "shuffle": True,
            }),
            {"videos": ["/tmp/one.mp4", "/tmp/two.mkv"], "shuffle": True},
        )

    def test_shuffle_true_uses_random_choice_from_valid_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "one.mp4"
            second = Path(tmp) / "two.mp4"
            first.touch()
            second.touch()
            config = {"videos": [str(first), str(second)], "shuffle": True}

            with mock.patch.object(player.random, "choice", return_value=str(second)) as choice:
                self.assertEqual(
                    player.choose_video_for_monitor("HDMI-0", config),
                    str(second),
                )
                choice.assert_called_once_with([str(first), str(second)])

    def test_shuffle_false_chooses_first_valid_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "one.mp4"
            second = Path(tmp) / "two.mp4"
            first.touch()
            second.touch()
            config = {"videos": [str(first), str(second)], "shuffle": False}

            self.assertEqual(
                player.choose_video_for_monitor("HDMI-0", config),
                str(first),
            )

    def test_missing_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.mp4"
            valid = Path(tmp) / "valid.mp4"
            valid.touch()
            config = {"videos": [str(missing), str(valid)], "shuffle": False}

            with mock.patch.object(player, "log") as log:
                self.assertEqual(
                    player.choose_video_for_monitor("HDMI-0", config),
                    str(valid),
                )
                log.assert_any_call(f"Skipping missing video for HDMI-0: {missing}")

    def test_all_missing_files_return_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.mp4"
            config = {"videos": [str(missing)], "shuffle": False}

            with mock.patch.object(player, "log") as log:
                self.assertIsNone(player.choose_video_for_monitor("HDMI-0", config))
                log.assert_any_call("Skipping HDMI-0: no valid videos in playlist.")


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
