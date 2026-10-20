#!/usr/bin/env python3
"""
Kali Splash Pro — GUI Manager
Bugs fixed: no __main__ guard, shell injection in preview(), PNG crash via
            tk.PhotoImage, bare except:pass everywhere, no status validation,
            missing Open Logs / Test Now / Uninstall UI, blocking system calls
            on main thread, undefined preview() referenced before definition.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import subprocess
import os
import json
import random
import shlex
import shutil
import sys
import threading

try:
    from .player import (
        build_mpv_command, normalize_monitor_config, optimize_video_for_gpu,
        resolve_playback_path,
    )
except ImportError:
    from player import (
        build_mpv_command, normalize_monitor_config, optimize_video_for_gpu,
        resolve_playback_path,
    )

# ---------------------------------------------------------------------------
# PATHS — always resolved from this file's real location
# ---------------------------------------------------------------------------
CURRENT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(CURRENT_DIR)
CONFIG_FILE   = os.path.join(PROJECT_ROOT, "config.json")
PLAYER_SCRIPT = os.path.join(CURRENT_DIR, "player.py")
LOG_FILE      = os.path.join(PROJECT_ROOT, "splash_debug.log")
LOGO_PATH     = os.path.join(CURRENT_DIR, "preview.png")

AUTOSTART_DIR  = os.path.join(os.path.expanduser("~"), ".config", "autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "kali-splash-startup.desktop")
LEGACY_SERVICE = os.path.join(
    os.path.expanduser("~"), ".config", "systemd", "user", "kali-splash.service"
)

# ---------------------------------------------------------------------------
# COLOURS
# ---------------------------------------------------------------------------
BG        = "#111827"
BG2       = "#1f2937"
BG3       = "#374151"
ACCENT    = "#3b82f6"
ACCENT2   = "#1d4ed8"
GREEN     = "#22c55e"
RED       = "#ef4444"
YELLOW    = "#eab308"
FG        = "#f9fafb"
FG_DIM    = "#9ca3af"
FONT_HEAD = ("Sans Serif", 22, "bold")
FONT_SUB  = ("Sans Serif", 11)
FONT_MONO = ("Monospace", 9)
SUPPORTED_VIDEO_EXTENSIONS = frozenset({
    ".264", ".265", ".3g2", ".3gp", ".asf", ".avi", ".divx", ".f4v",
    ".flv", ".h264", ".h265", ".hevc", ".ivf", ".m2t", ".m2ts", ".m2v",
    ".m4v", ".mkv", ".mov", ".mp4", ".mpe", ".mpeg", ".mpg", ".mts",
    ".mxf", ".nut", ".ogv", ".rm", ".rmvb", ".ts", ".vob", ".webm",
    ".wmv", ".y4m",
})


def _case_insensitive_glob(extension: str) -> str:
    return "*" + "".join(
        f"[{character.lower()}{character.upper()}]" if character.isalpha()
        else character
        for character in extension
    )


VIDEO_FILE_PATTERNS = " ".join(
    _case_insensitive_glob(extension)
    for extension in sorted(SUPPORTED_VIDEO_EXTENSIONS)
)

# ---------------------------------------------------------------------------
# CONFIG HELPERS
# ---------------------------------------------------------------------------

def load_config(show_errors: bool = True) -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        if show_errors:
            messagebox.showerror(
                "Config Error",
                f"Could not read config.json:\n{e}\n\nPlease check the file.",
            )
        return {}


def save_config(data: dict) -> bool:
    try:
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)   # atomic write — no corruption risk
        return True
    except OSError as e:
        messagebox.showerror("Save Error", f"Failed to save config:\n{e}")
        return False


def config_has_any_videos(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    for value in data.values():
        if normalize_monitor_config(value)["videos"]:
            return True
    return False


def list_video_files(folder: str) -> list[str]:
    """Return every supported video directly inside a folder, without a count limit."""
    with os.scandir(folder) as entries:
        paths = [
            entry.path
            for entry in entries
            if entry.is_file()
            and os.path.splitext(entry.name)[1].casefold() in SUPPORTED_VIDEO_EXTENSIONS
        ]
    return sorted(paths, key=lambda path: (os.path.basename(path).casefold(), path))


def select_video_files(title: str) -> list[str]:
    """
    Open a multi-select video picker.
    Prefer zenity's GTK dialog on Linux because some Tk file dialogs expose
    awkward or unreliable multi-select behavior on desktop themes.
    """
    if shutil.which("zenity"):
        try:
            result = subprocess.run(
                [
                    "zenity",
                    "--file-selection",
                    "--multiple",
                    "--separator=\n",
                    f"--title={title}",
                    f"--file-filter=Video files | {VIDEO_FILE_PATTERNS}",
                    "--file-filter=All files | *",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            result = None

        if result is not None:
            if result.returncode == 0:
                return [
                    path.strip()
                    for path in result.stdout.splitlines()
                    if path.strip()
                ]
            return []

    return list(filedialog.askopenfilenames(
        title=title,
        filetypes=[("Video files", VIDEO_FILE_PATTERNS.split()),
                   ("All files", "*.*")],
    ))


# ---------------------------------------------------------------------------
# AUTOSTART HELPERS
# ---------------------------------------------------------------------------

def autostart_is_enabled() -> bool:
    return os.path.exists(AUTOSTART_FILE)


def extract_exec_script_path(exec_line: str) -> str | None:
    """Return the script path from a .desktop Exec= line."""
    if not exec_line.startswith("Exec="):
        return None

    try:
        args = shlex.split(exec_line[len("Exec="):].strip())
    except ValueError:
        return None

    if not args:
        return None

    first = os.path.basename(args[0])
    if first.startswith("python") and len(args) >= 2:
        return args[1]
    return args[0]


def autostart_path_is_valid() -> bool:
    """Check that the autostart .desktop points to the current player.py."""
    if not os.path.exists(AUTOSTART_FILE):
        return False
    try:
        with open(AUTOSTART_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("Exec="):
                    pointed_at = extract_exec_script_path(line.strip())
                    if not pointed_at:
                        return False
                    return (
                        os.path.exists(pointed_at)
                        and os.path.realpath(pointed_at) == os.path.realpath(PLAYER_SCRIPT)
                    )
        return False
    except OSError:
        return False


def remove_legacy_service() -> None:
    if os.path.exists(LEGACY_SERVICE):
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "kali-splash"],
                stderr=subprocess.DEVNULL, timeout=5,
            )
            os.remove(LEGACY_SERVICE)
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                stderr=subprocess.DEVNULL, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def enable_autostart() -> bool:
    remove_legacy_service()
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    # Quote the path to handle spaces correctly
    quoted_script = f'"{PLAYER_SCRIPT}"'
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Kali Splash Pro\n"
        f"Exec=/usr/bin/python3 {quoted_script}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Comment=Start Kali Splash Pro on login\n"
    )
    try:
        with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except OSError as e:
        messagebox.showerror("Autostart Error", f"Could not write autostart file:\n{e}")
        return False


def disable_autostart() -> bool:
    remove_legacy_service()
    if os.path.exists(AUTOSTART_FILE):
        try:
            os.remove(AUTOSTART_FILE)
        except OSError as e:
            messagebox.showerror("Error", f"Could not remove autostart file:\n{e}")
            return False
    return True


# ---------------------------------------------------------------------------
# MONITOR DETECTION (non-blocking via thread)
# ---------------------------------------------------------------------------

def parse_xrandr_monitors(output: str) -> list[str]:
    names = []
    for line in output.strip().splitlines()[1:]:
        parts = line.split()
        if parts:
            names.append(parts[-1])
    return names


def get_monitors() -> list:
    try:
        out = subprocess.check_output(
            ["xrandr", "--listmonitors"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode("utf-8", errors="replace")
        names = parse_xrandr_monitors(out)
        return names if names else ["Default"]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, OSError):
        return ["Default"]


# ---------------------------------------------------------------------------
# DEPENDENCY CHECK
# ---------------------------------------------------------------------------
REQUIRED_CMDS = {
    "mpv": "mpv",
    "xdotool": "xdotool",
    "xrandr": "xrandr",
    "xset": "xset",
}

def check_deps() -> dict:
    """Returns dict of {tool: bool_installed}."""
    result = {}
    for name, cmd in REQUIRED_CMDS.items():
        result[name] = shutil.which(cmd) is not None
    # python3 is clearly installed (we're running)
    result["python3"] = True
    result["tkinter"] = True
    return result


# ---------------------------------------------------------------------------
# APPLICATION CLASS
# ---------------------------------------------------------------------------

class KaliSplashManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Kali Splash Pro")
        self.root.geometry("860x760")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(760, 680)

        self._monitor_states: dict[str, dict] = {}
        self._preview_proc = None
        self._optimization_active = False

        self._load_icon()
        self._build_header()
        self._build_status_bar()
        self._build_monitor_section()
        self._build_dep_section()
        self._build_footer()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        # Refresh status asynchronously so the window opens instantly
        threading.Thread(target=self._async_refresh, daemon=True).start()

    # ------------------------------------------------------------------ icon
    def _load_icon(self):
        if not os.path.exists(LOGO_PATH):
            return
        try:
            # Try PIL first (supports PNG properly)
            from PIL import Image, ImageTk
            img = Image.open(LOGO_PATH).resize((48, 48))
            self._icon_img = ImageTk.PhotoImage(img)
            self.root.iconphoto(False, self._icon_img)
        except ImportError:
            # Pillow not installed — try native tk (only works for GIF/PPM,
            # but Tk 8.6+ has limited PNG support via libpng)
            try:
                img = tk.PhotoImage(file=LOGO_PATH)
                # Scale down if needed
                w = img.width()
                factor = 1
                while w // factor > 64:
                    factor *= 2
                if factor > 1:
                    img = img.subsample(factor, factor)
                self._icon_img = img
                self.root.iconphoto(False, img)
            except tk.TclError:
                pass  # icon load failed — not critical
        except Exception:
            pass

    # --------------------------------------------------------------- header
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG, pady=16)
        hdr.pack(fill="x", padx=24)

        if hasattr(self, "_icon_img"):
            tk.Label(hdr, image=self._icon_img, bg=BG).pack(side="left", padx=(0, 12))

        title_frame = tk.Frame(hdr, bg=BG)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="KALI SPLASH PRO",
                 font=FONT_HEAD, bg=BG, fg=ACCENT).pack(anchor="w")
        tk.Label(title_frame, text="Cinematic login screen manager for Kali XFCE",
                 font=FONT_SUB, bg=BG, fg=FG_DIM).pack(anchor="w")

        tk.Frame(self.root, bg=BG3, height=1).pack(fill="x", padx=24)

    # ----------------------------------------------------------- status bar
    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=BG2, pady=10, padx=20)
        bar.pack(fill="x", padx=24, pady=(12, 0))

        # Autostart status
        left = tk.Frame(bar, bg=BG2)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text="Autostart", font=("Sans Serif", 9), bg=BG2, fg=FG_DIM).grid(
            row=0, column=0, sticky="w")
        self._status_label = tk.Label(left, text="Checking…",
                                      font=("Sans Serif", 11, "bold"), bg=BG2, fg=YELLOW)
        self._status_label.grid(row=1, column=0, sticky="w")

        # Path validity
        tk.Label(left, text="Path", font=("Sans Serif", 9), bg=BG2, fg=FG_DIM).grid(
            row=0, column=2, sticky="w", padx=(30, 0))
        self._path_label = tk.Label(left, text="Checking…",
                                    font=("Sans Serif", 11, "bold"), bg=BG2, fg=YELLOW)
        self._path_label.grid(row=1, column=2, sticky="w", padx=(30, 0))

        # Config validity
        tk.Label(left, text="Config", font=("Sans Serif", 9), bg=BG2, fg=FG_DIM).grid(
            row=0, column=4, sticky="w", padx=(30, 0))
        self._config_label = tk.Label(left, text="Checking…",
                                      font=("Sans Serif", 11, "bold"), bg=BG2, fg=YELLOW)
        self._config_label.grid(row=1, column=4, sticky="w", padx=(30, 0))

        # Refresh button
        tk.Button(bar, text="↻ Refresh", command=self._refresh_status,
                  bg=BG3, fg=FG, font=("Sans Serif", 9), relief="flat",
                  padx=8, pady=4,
                  cursor="hand2").pack(side="right")

    # ---------------------------------------------------- monitor section
    def _build_monitor_section(self):
        sec = tk.LabelFrame(self.root, text=" 🖥  Monitors & Videos ",
                            bg=BG, fg=FG_DIM, font=FONT_SUB,
                            bd=1, relief="solid")
        sec.pack(fill="x", padx=24, pady=12)

        self._monitor_frame = tk.Frame(sec, bg=BG)
        self._monitor_frame.pack(fill="x", padx=12, pady=8)
        self._populate_monitors()

    def _populate_monitors(self):
        for w in self._monitor_frame.winfo_children():
            w.destroy()
        self._monitor_states.clear()

        conf     = load_config()
        monitors = get_monitors()

        for mon in monitors:
            row = tk.Frame(self._monitor_frame, bg=BG2, pady=8, padx=10)
            row.pack(fill="x", pady=4)

            normalized = normalize_monitor_config(conf.get(mon, ""))
            shuffle_var = tk.BooleanVar(value=normalized["shuffle"])

            top = tk.Frame(row, bg=BG2)
            top.pack(fill="x")

            tk.Label(top, text=f"  {mon}", bg=BG2, fg=FG,
                     font=("Monospace", 10, "bold"), width=14, anchor="w").pack(side="left")

            tk.Checkbutton(top, text="Shuffle", variable=shuffle_var,
                           bg=BG2, fg=FG, selectcolor=BG3,
                           activebackground=BG2, activeforeground=FG,
                           font=("Sans Serif", 9), cursor="hand2").pack(side="right")

            body = tk.Frame(row, bg=BG2)
            body.pack(fill="x", pady=(6, 0))

            list_wrap = tk.Frame(body, bg=BG3)
            list_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8))

            listbox = tk.Listbox(
                list_wrap,
                height=4,
                selectmode="extended",
                exportselection=False,
                bg=BG3,
                fg=FG,
                selectbackground=ACCENT2,
                selectforeground=FG,
                borderwidth=0,
                highlightthickness=0,
                font=("Monospace", 9),
            )
            scrollbar = tk.Scrollbar(list_wrap, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=scrollbar.set)
            listbox.pack(side="left", fill="both", expand=True, padx=4, pady=4)
            scrollbar.pack(side="right", fill="y")

            for path in normalized["videos"]:
                listbox.insert("end", path)

            self._monitor_states[mon] = {
                "listbox": listbox,
                "shuffle": shuffle_var,
            }

            buttons = tk.Frame(body, bg=BG2)
            buttons.pack(side="left", fill="y")

            tk.Button(buttons, text="📂 Add",
                      command=lambda m=mon: self._add_videos(m),
                      bg=BG3, fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="📁 Add Folder",
                      command=lambda m=mon: self._add_video_folder(m),
                      bg=BG3, fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="⚡ Optimize for GPU",
                      command=lambda m=mon: self._optimize_playlist(m),
                      bg=BG3, fg=FG, relief="flat", padx=4, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="▶ Preview",
                      command=lambda m=mon: self._preview_playlist(m),
                      bg=ACCENT2, fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="↑ Up",
                      command=lambda m=mon: self._move_selected(m, -1),
                      bg=BG3, fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="↓ Down",
                      command=lambda m=mon: self._move_selected(m, 1),
                      bg=BG3, fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="Remove",
                      command=lambda m=mon: self._remove_selected(m),
                      bg="#7f1d1d", fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)
            tk.Button(buttons, text="Clear",
                      command=lambda m=mon: self._clear_playlist(m),
                      bg="#7f1d1d", fg=FG, relief="flat", padx=8, cursor="hand2",
                      font=("Sans Serif", 9)).pack(fill="x", pady=1)

        # Save button
        tk.Button(self._monitor_frame, text="💾  Save Config",
                  command=self._save_all,
                  bg=ACCENT, fg=FG, relief="flat", padx=12, pady=5,
                  font=("Sans Serif", 10, "bold"), cursor="hand2").pack(
                      side="right", padx=4, pady=(6, 2))

    # ---------------------------------------------------- dep section
    def _build_dep_section(self):
        sec = tk.LabelFrame(self.root, text=" ⚙  Dependencies ",
                            bg=BG, fg=FG_DIM, font=FONT_SUB,
                            bd=1, relief="solid")
        sec.pack(fill="x", padx=24, pady=(0, 6))

        self._dep_frame = tk.Frame(sec, bg=BG)
        self._dep_frame.pack(fill="x", padx=12, pady=6)
        # Placeholder until thread populates
        tk.Label(self._dep_frame, text="Checking…", bg=BG, fg=FG_DIM,
                 font=FONT_SUB).pack()

    def _update_dep_section(self, deps: dict):
        for w in self._dep_frame.winfo_children():
            w.destroy()
        cols = tk.Frame(self._dep_frame, bg=BG)
        cols.pack(fill="x")
        for name, ok in deps.items():
            color = GREEN if ok else RED
            sym   = "✔" if ok else "✘"
            lbl   = tk.Frame(cols, bg=BG2, padx=8, pady=3)
            lbl.pack(side="left", padx=3, pady=2)
            tk.Label(lbl, text=f"{sym} {name}", bg=BG2,
                     fg=color, font=("Monospace", 9)).pack()

    # --------------------------------------------------------------- footer
    def _build_footer(self):
        tk.Frame(self.root, bg=BG3, height=1).pack(fill="x", padx=24, pady=(4, 0))
        foot = tk.Frame(self.root, bg=BG, pady=14, padx=24)
        foot.pack(fill="x", side="bottom")

        # Left cluster
        left = tk.Frame(foot, bg=BG)
        left.pack(side="left")

        tk.Button(left, text="📋 View Logs",
                  command=self._open_logs,
                  bg=BG3, fg=FG, relief="flat", padx=10, pady=6,
                  font=("Sans Serif", 9), cursor="hand2").pack(side="left", padx=2)

        tk.Button(left, text="🧪 Test Splash Now",
                  command=self._test_splash,
                  bg=BG3, fg=FG, relief="flat", padx=10, pady=6,
                  font=("Sans Serif", 9), cursor="hand2").pack(side="left", padx=2)

        tk.Button(left, text="🗑 Remove Autostart",
                  command=self._uninstall,
                  bg="#7f1d1d", fg=FG, relief="flat", padx=10, pady=6,
                  font=("Sans Serif", 9), cursor="hand2").pack(side="left", padx=2)

        # Right cluster
        right = tk.Frame(foot, bg=BG)
        right.pack(side="right")

        self._toggle_btn = tk.Button(
            right, text="Enable Autostart",
            command=self._toggle_autostart,
            bg=ACCENT, fg=FG, relief="flat", padx=20, pady=8,
            font=("Sans Serif", 11, "bold"), cursor="hand2",
        )
        self._toggle_btn.pack(side="right")

    # ---------------------------------------------------------------- actions
    def _playlist_for_monitor(self, mon: str) -> list[str]:
        state = self._monitor_states[mon]
        listbox = state["listbox"]
        return [
            listbox.get(idx).strip()
            for idx in range(listbox.size())
            if listbox.get(idx).strip()
        ]

    def _add_videos(self, mon: str):
        paths = select_video_files(f"Add videos for {mon}")
        if not paths:
            return
        self._append_videos(mon, paths)

    def _add_video_folder(self, mon: str):
        videos_dir = os.path.join(os.path.expanduser("~"), "Videos")
        initialdir = videos_dir if os.path.isdir(videos_dir) else os.path.expanduser("~")
        folder = filedialog.askdirectory(
            title=f"Add videos from a folder for {mon}",
            initialdir=initialdir,
            mustexist=True,
            parent=self.root,
        )
        if not folder:
            return
        try:
            paths = list_video_files(folder)
        except OSError as e:
            messagebox.showerror("Folder Error", f"Could not read folder:\n{e}")
            return
        if not paths:
            messagebox.showinfo(
                "No Videos Found",
                "The selected folder contains no supported video files.",
            )
            return
        self._append_videos(mon, paths)

    def _append_videos(self, mon: str, paths: list[str]) -> int:
        listbox = self._monitor_states[mon]["listbox"]
        existing = {
            os.path.normcase(os.path.abspath(listbox.get(idx).strip()))
            for idx in range(listbox.size())
            if listbox.get(idx).strip()
        }
        added = 0
        for path in paths:
            path = os.path.abspath(path)
            key = os.path.normcase(path)
            if key in existing:
                continue
            listbox.insert("end", path)
            existing.add(key)
            added += 1

        if added:
            listbox.selection_clear(0, "end")
            listbox.selection_set(listbox.size() - added, "end")
            listbox.see("end")
            self._show_toast(f"Added {added} video(s). Click Save Config.")
        else:
            self._show_toast("Those videos are already in the playlist.")
        return added

    def _optimize_playlist(self, mon: str):
        if self._optimization_active:
            self._show_toast("GPU optimization is already running.")
            return
        videos = self._playlist_for_monitor(mon)
        if not videos:
            messagebox.showwarning("Empty Playlist", f"Add videos to {mon} first.")
            return
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            messagebox.showerror(
                "FFmpeg Not Found",
                "Install ffmpeg to create hardware-decodable playback copies.",
            )
            return

        self._optimization_active = True
        self._show_toast(f"Preparing GPU playback copies for {len(videos)} video(s)…")
        threading.Thread(
            target=self._optimize_playlist_worker,
            args=(mon, videos),
            daemon=True,
        ).start()

    def _optimize_playlist_worker(self, mon: str, videos: list[str]):
        optimized = 0
        compatible = 0
        failures = []
        for index, path in enumerate(videos, start=1):
            try:
                before = resolve_playback_path(path)
                result = optimize_video_for_gpu(path)
                if os.path.abspath(result) == os.path.abspath(path):
                    compatible += 1
                elif os.path.abspath(result) == os.path.abspath(before):
                    compatible += 1
                else:
                    optimized += 1
            except Exception as e:
                failures.append((path, str(e)))

            try:
                self.root.after(
                    0,
                    lambda i=index, total=len(videos): self._show_toast(
                        f"GPU optimization {i}/{total}…"
                    ),
                )
            except tk.TclError:
                return

        summary = (
            f"GPU copies ready: {optimized} optimized, "
            f"{compatible} already compatible."
        )
        if failures:
            summary += f" {len(failures)} could not be optimized."

        def finish():
            self._optimization_active = False
            if failures:
                details = "\n".join(
                    f"• {os.path.basename(path)}: {error[:180]}"
                    for path, error in failures[:3]
                )
                messagebox.showwarning("Some Videos Were Not Optimized", details)
            self._show_toast(summary)

        try:
            self.root.after(0, finish)
        except tk.TclError:
            self._optimization_active = False

    def _remove_selected(self, mon: str):
        listbox = self._monitor_states[mon]["listbox"]
        selected = list(listbox.curselection())
        if not selected:
            messagebox.showwarning("No Selection", "Select a playlist item to remove.")
            return
        for idx in reversed(selected):
            listbox.delete(idx)

    def _clear_playlist(self, mon: str):
        self._monitor_states[mon]["listbox"].delete(0, "end")

    def _move_selected(self, mon: str, delta: int):
        listbox = self._monitor_states[mon]["listbox"]
        selected = list(listbox.curselection())
        if not selected:
            messagebox.showwarning("No Selection", "Select a playlist item to move.")
            return
        if delta < 0 and selected[0] == 0:
            return
        if delta > 0 and selected[-1] == listbox.size() - 1:
            return

        iterator = selected if delta < 0 else reversed(selected)
        for idx in iterator:
            item = listbox.get(idx)
            listbox.delete(idx)
            listbox.insert(idx + delta, item)

        listbox.selection_clear(0, "end")
        for idx in selected:
            listbox.selection_set(idx + delta)
        listbox.activate(selected[0] + delta)

    def _save_all(self):
        cfg = load_config()
        missing_count = 0
        for mon, state in self._monitor_states.items():
            videos = self._playlist_for_monitor(mon)
            missing = [path for path in videos if not os.path.exists(path)]
            missing_count += len(missing)

            if videos:
                cfg[mon] = {
                    "videos": videos,
                    "shuffle": bool(state["shuffle"].get()),
                }
            elif mon in cfg:
                del cfg[mon]

        if save_config(cfg):
            if missing_count:
                self._show_toast(
                    f"Config saved; kept {missing_count} unavailable path(s)."
                )
            else:
                self._show_toast("Config saved ✔")
            self._refresh_status()
            return True
        return False

    def _preview_playlist(self, mon: str):
        state = self._monitor_states[mon]
        listbox = state["listbox"]
        selected = list(listbox.curselection())

        if selected:
            path = listbox.get(selected[0]).strip()
            if not path:
                messagebox.showwarning("No Video", "Selected playlist item is empty.")
                return
            if not os.path.exists(path):
                messagebox.showerror("Not Found", f"Selected file not found:\n{path}")
                return
        else:
            playlist = self._playlist_for_monitor(mon)
            if not playlist:
                messagebox.showwarning("Empty Playlist", f"No videos are configured for {mon}.")
                return
            valid = [path for path in playlist if os.path.exists(path)]
            if not valid:
                messagebox.showerror("No Valid Videos", f"No playlist files exist for {mon}.")
                return
            path = random.choice(valid) if state["shuffle"].get() else valid[0]

        self._launch_preview(path)

    def _launch_preview(self, path: str):
        if not path:
            messagebox.showwarning("No Video", "No video path selected.")
            return
        if not os.path.exists(path):
            messagebox.showerror("Not Found", f"File not found:\n{path}")
            return
        # Kill previous preview if still running
        if self._preview_proc and self._preview_proc.poll() is None:
            try:
                self._preview_proc.terminate()
            except OSError:
                pass
        # FIX: use list form — no shell injection
        try:
            self._preview_proc = subprocess.Popen(
                build_mpv_command(resolve_playback_path(path)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            messagebox.showerror("mpv Not Found",
                "mpv is not installed. Run:\n  sudo apt install mpv")
        except OSError as e:
            messagebox.showerror("Launch Error", str(e))

    def _toggle_autostart(self):
        if autostart_is_enabled():
            if disable_autostart():
                self._show_toast("Autostart disabled.")
        else:
            # Save current config first
            if not self._save_all():
                return
            if enable_autostart():
                self._show_toast("Autostart enabled ✔  — reboot to test.")
        self._refresh_status()

    def _uninstall(self):
        if not messagebox.askyesno(
            "Remove Autostart",
            "This will remove the autostart entry so the splash screen\n"
            "no longer runs at login.\n\nProceed?"
        ):
            return
        if disable_autostart():
            self._refresh_status()
            self._show_toast("Autostart entry removed.")

    def _test_splash(self):
        """Run player.py directly to test the splash without rebooting."""
        if not os.path.exists(PLAYER_SCRIPT):
            messagebox.showerror("Missing", f"player.py not found:\n{PLAYER_SCRIPT}")
            return
        cfg = load_config()
        if not config_has_any_videos(cfg):
            messagebox.showwarning("No Config",
                "No videos configured. Add videos to a monitor playlist first.")
            return
        try:
            subprocess.Popen(
                [sys.executable, PLAYER_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._show_toast("Splash test launched — close mpv window when done.")
        except OSError as e:
            messagebox.showerror("Error", str(e))

    def _open_logs(self):
        """Open the log file in a scrollable text window."""
        win = tk.Toplevel(self.root)
        win.title("Splash Debug Log")
        win.geometry("700x400")
        win.configure(bg=BG)

        txt = scrolledtext.ScrolledText(win, bg="#0d1117", fg=GREEN,
                                        font=FONT_MONO, wrap="none")
        txt.pack(fill="both", expand=True, padx=8, pady=8)

        def read_log() -> str:
            if os.path.exists(LOG_FILE):
                try:
                    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                        return f.read()
                except OSError as e:
                    return f"(Error reading log: {e})"
            return "(No log file found yet — run a splash to generate one.)"

        txt.insert("end", read_log())

        txt.see("end")
        txt.config(state="disabled")

        btm = tk.Frame(win, bg=BG)
        btm.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btm, text="Close", command=win.destroy,
                  bg=BG3, fg=FG, relief="flat", padx=10).pack(side="right")
        tk.Button(btm, text="Refresh", bg=BG3, fg=FG, relief="flat", padx=10,
                  command=lambda: self._refresh_log_window(txt, read_log)).pack(
                      side="right", padx=4)

    def _refresh_log_window(self, txt: scrolledtext.ScrolledText, reader):
        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", reader())
        txt.see("end")
        txt.config(state="disabled")

    def _refresh_status(self):
        threading.Thread(target=self._async_refresh, daemon=True).start()

    def _async_refresh(self):
        # Run heavy checks off the main thread, then update UI via after()
        enabled = autostart_is_enabled()
        valid   = autostart_path_is_valid() if enabled else False
        cfg     = load_config(show_errors=False)
        cfg_ok  = config_has_any_videos(cfg)
        deps    = check_deps()

        self.root.after(0, self._apply_status, enabled, valid, cfg_ok, deps)

    def _apply_status(self, enabled: bool, valid: bool, cfg_ok: bool, deps: dict):
        if enabled:
            self._status_label.config(text="ENABLED ✔", fg=GREEN)
            self._toggle_btn.config(text="Disable Autostart", bg="#b91c1c")
        else:
            self._status_label.config(text="DISABLED ✘", fg=RED)
            self._toggle_btn.config(text="Enable Autostart", bg=ACCENT)

        if not enabled:
            self._path_label.config(text="N/A", fg=FG_DIM)
        elif valid:
            self._path_label.config(text="Valid ✔", fg=GREEN)
        else:
            self._path_label.config(
                text="BROKEN ✘ — re-enable", fg=RED)

        if cfg_ok:
            self._config_label.config(text="OK ✔", fg=GREEN)
        else:
            self._config_label.config(text="Missing / Empty", fg=YELLOW)

        self._update_dep_section(deps)

    def _show_toast(self, msg: str):
        """Brief status message at the bottom of the window."""
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.configure(bg=BG2)
        tk.Label(toast, text=f"  {msg}  ", bg=BG2, fg=GREEN,
                 font=("Sans Serif", 10), pady=8, padx=12).pack()
        # Center over main window
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width()  // 2 - 150
        y = self.root.winfo_y() + self.root.winfo_height() - 60
        toast.geometry(f"+{x}+{y}")
        self.root.after(2500, toast.destroy)

    def _close(self):
        if self._preview_proc and self._preview_proc.poll() is None:
            try:
                self._preview_proc.terminate()
            except OSError:
                pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = KaliSplashManager(root)   # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    main()
