#!/usr/bin/env python3
"""
Kali Splash Pro — Splash Player
Plays fullscreen video(s) on login via XDG autostart.
Bugs fixed: CPU-burn guard dog, pipe deadlock, fragile xrandr parsing,
            missing error handling, no duplicate guard, no log rotation,
            blind DISPLAY override, missing SIGTERM cleanup.
"""

import subprocess
import os
import json
import random
import time
import sys
import signal
import datetime
import fcntl
import hashlib
import shutil
import tempfile

# ---------------------------------------------------------------------------
# DYNAMIC PATHS — resolved from this file's real location, not CWD
# ---------------------------------------------------------------------------
CURRENT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
CONFIG_FILE  = os.path.join(PROJECT_ROOT, "config.json")
LOG_FILE     = os.path.join(PROJECT_ROOT, "splash_debug.log")
LOCK_FILE    = os.path.join(tempfile.gettempdir(), "kali-splash.lock")
CACHE_ROOT   = os.environ.get(
    "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")
)
VIDEO_CACHE_DIR = os.path.join(CACHE_ROOT, "kali-splash-pro", "h264")
_H264_NVENC_AVAILABLE: bool | None = None

# ---------------------------------------------------------------------------
# LOG — rotating append, keeps last 500 lines max
# ---------------------------------------------------------------------------
LOG_MAX_LINES = 500

def log(msg: str) -> None:
    """Append a timestamped line to the log file, rotating if too large."""
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}\n"
    try:
        # Rotate if needed
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                if len(lines) > LOG_MAX_LINES:
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.writelines(lines[-LOG_MAX_LINES:])
        except OSError:
            pass  # rotation failure is non-fatal

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        # Last resort: stderr
        print(f"[LOG ERROR] {e}: {line}", file=sys.stderr)


# ---------------------------------------------------------------------------
# DUPLICATE GUARD — only one instance allowed
# ---------------------------------------------------------------------------
_lock_fd = None

def acquire_lock() -> bool:
    """Return True if this process successfully acquires the run lock."""
    global _lock_fd
    if _lock_fd:
        return False
    try:
        _lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except (OSError, IOError):
        if _lock_fd:
            try:
                _lock_fd.close()
            except OSError:
                pass
            _lock_fd = None
        return False

def release_lock() -> None:
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except OSError:
            pass
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# DISPLAY DETECTION
# ---------------------------------------------------------------------------
def detect_display() -> bool:
    """
    Ensure DISPLAY is set. Tries common values if not already in environment.
    Returns True when an X server responds.
    """
    candidates = []
    if os.environ.get("DISPLAY"):
        candidates.append(os.environ["DISPLAY"])
    # Fallback candidates for systemd-launched services
    candidates += [":0", ":1", ":10"]
    candidates = list(dict.fromkeys(candidates))

    for _ in range(100):            # up to 10 s total
        for disp in candidates:
            os.environ["DISPLAY"] = disp
            try:
                subprocess.check_output(
                    ["xset", "q"],
                    stderr=subprocess.DEVNULL,
                    timeout=1,
                )
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    FileNotFoundError, OSError):
                pass
        time.sleep(0.1)

    log("FATAL: X Server never appeared after 10 s.")
    return False


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
def load_config() -> dict:
    """Load and validate config.json. Returns empty dict on any failure."""
    if not os.path.exists(CONFIG_FILE):
        log("Config file not found — nothing to play.")
        return {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log(f"Config is not a JSON object — skipping.")
            return {}
        return data
    except json.JSONDecodeError as e:
        log(f"Config JSON parse error: {e}")
        return {}
    except OSError as e:
        log(f"Config read error: {e}")
        return {}


def normalize_monitor_config(value) -> dict:
    """
    Convert a legacy string or playlist object into one internal shape.
    Returns: {"videos": list[str], "shuffle": bool}
    """
    if isinstance(value, str):
        path = value.strip()
        return {"videos": [path] if path else [], "shuffle": False}

    if not isinstance(value, dict):
        return {"videos": [], "shuffle": False}

    raw_videos = value.get("videos", [])
    if isinstance(raw_videos, str):
        raw_videos = [raw_videos]
    elif not isinstance(raw_videos, list):
        raw_videos = []

    videos = []
    for path in raw_videos:
        if isinstance(path, str) and path.strip():
            videos.append(path.strip())

    return {
        "videos": videos,
        "shuffle": bool(value.get("shuffle", False)),
    }


def optimized_video_cache_path(video_path: str) -> str:
    """Return the cache path tied to this source file's location and contents."""
    source = os.path.abspath(os.path.expanduser(video_path))
    stat = os.stat(source)
    fingerprint = hashlib.sha256(
        f"{source}\0{stat.st_size}\0{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()
    return os.path.join(VIDEO_CACHE_DIR, f"{fingerprint}.mp4")


def resolve_playback_path(video_path: str) -> str:
    """Prefer an optimized hardware-decodable cache copy when one is ready."""
    try:
        cached = optimized_video_cache_path(video_path)
        if os.path.isfile(cached) and os.path.getsize(cached) > 0:
            return cached
    except OSError:
        pass
    return video_path


def optimize_video_for_gpu(video_path: str) -> str:
    """Create a source-preserving H.264/NVENC copy for smooth NVDEC playback."""
    global _H264_NVENC_AVAILABLE
    source = os.path.abspath(os.path.expanduser(video_path))
    if not os.path.isfile(source):
        raise FileNotFoundError(source)

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required for GPU optimization")

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", source],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
    )
    if probe.returncode:
        raise RuntimeError(probe.stderr.strip() or "Could not inspect video codec")
    if probe.stdout.strip().splitlines()[:1] == ["h264"]:
        return source

    if _H264_NVENC_AVAILABLE is None:
        encoders = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
        )
        _H264_NVENC_AVAILABLE = (
            encoders.returncode == 0 and "h264_nvenc" in encoders.stdout
        )
    if not _H264_NVENC_AVAILABLE:
        raise RuntimeError("This FFmpeg build does not provide the NVIDIA H.264 encoder")

    target = optimized_video_cache_path(source)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target

    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target[:-4] + ".partial.mp4"
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-threads", "2", "-i", source,
        "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0",
        "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq",
        "-rc:v", "vbr", "-cq:v", "20", "-b:v", "0",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-f", "mp4", temporary,
    ]
    nice = shutil.which("nice")
    if nice:
        command = [nice, "-n", "19", *command]
    ionice = shutil.which("ionice")
    if ionice:
        command = [ionice, "-c", "3", "--", *command]

    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=None,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[-1200:] or "FFmpeg encode failed")
        if not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
            raise RuntimeError("FFmpeg did not produce a non-empty optimized video")
        os.replace(temporary, target)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
    return target


def choose_video_for_monitor(monitor_name: str, config_value) -> str | None:
    """Return the one video this run should play for a monitor, or None."""
    monitor_config = normalize_monitor_config(config_value)
    videos = monitor_config["videos"]
    if not videos:
        log(f"Skipping {monitor_name}: playlist is empty.")
        return None

    valid_videos = []
    for path in videos:
        if os.path.exists(path):
            valid_videos.append(path)
        else:
            log(f"Skipping missing video for {monitor_name}: {path}")

    if not valid_videos:
        log(f"Skipping {monitor_name}: no valid videos in playlist.")
        return None

    if monitor_config["shuffle"]:
        return random.choice(valid_videos)
    return valid_videos[0]


# ---------------------------------------------------------------------------
# MONITOR INDEX MAP
# ---------------------------------------------------------------------------
def parse_monitor_indices(output: str) -> dict[str, str]:
    indices = {}
    for line in output.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        idx = parts[0].rstrip(":")
        name = parts[-1]
        if idx.isdigit() and name:
            indices[name] = idx
    return indices


def get_monitor_indices() -> dict:
    """
    Parse `xrandr --listmonitors` and return {monitor_name: screen_index}.
    Example output line: ' 0: +*HDMI-0 1680/444x1050/278+0+0  HDMI-0'
    """
    indices = {}
    try:
        raw = subprocess.check_output(
            ["xrandr", "--listmonitors"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8", errors="replace")
        indices = parse_monitor_indices(raw)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, OSError) as e:
        log(f"xrandr failed: {e} — defaulting all monitors to screen 0")
    return indices


# ---------------------------------------------------------------------------
# GUARD DOG — smarter, low-CPU version
# ---------------------------------------------------------------------------
GUARD_INITIAL_INTERVAL  = 0.25   # brief startup polling, with low idle overhead
GUARD_INITIAL_DURATION  = 5.0    # seconds of fast polling at start
GUARD_NORMAL_INTERVAL   = 1.0    # then back off to one check per second


def build_mpv_command(video_path: str, screen_index: str | None = None) -> list[str]:
    """Build a shared GPU-backed mpv command for startup and preview playback."""
    cmd = [
        "mpv",
        "--vo=gpu",
        "--gpu-api=opengl",
        "--hwdec=auto",
        "--panscan=1.0",
        "--ontop",
        "--no-border",
        "--no-osc",
        "--no-input-default-bindings",
        "--input-vo-keyboard=no",
        "--input-media-keys=no",
        "--x11-bypass-compositor=yes",
        "--force-window=immediate",
        "--keep-open=no",
        "--loop=no",
        "--fs",
    ]
    if screen_index is not None:
        cmd.append(f"--fs-screen={screen_index}")
    cmd.append(video_path)
    return cmd

def guard_dog(procs: list) -> None:
    """
    Keep mpv windows on top while any process is alive.
    Uses fast polling at startup (to beat compositor/taskbar),
    then backs off to save CPU.
    """
    log("Guard Dog engaged.")
    start_time = time.monotonic()
    windows_raised = False

    try:
        while any(p.poll() is None for p in procs):
            elapsed = time.monotonic() - start_time
            interval = (GUARD_INITIAL_INTERVAL if elapsed < GUARD_INITIAL_DURATION
                        else GUARD_NORMAL_INTERVAL)

            # mpv already stays on top. Raise its windows once, then only poll
            # child processes so long splash videos do not spawn xdotool in a loop.
            if not windows_raised:
                try:
                    result = subprocess.run(
                        ["xdotool", "search", "--class", "mpv"],
                        capture_output=True, timeout=2,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        windows_raised = True
                        for action in ("windowraise", "windowactivate"):
                            subprocess.run(
                                ["xdotool", "search", "--class", "mpv", action],
                                capture_output=True, timeout=2,
                            )
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                    log(f"Guard Dog xdotool error: {e}")

            time.sleep(interval)

    except Exception as e:
        log(f"Guard Dog crashed: {e}")


# ---------------------------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------------------------
_running_procs: list = []

def cleanup_handler(signum, frame) -> None:
    """Kill all child mpv processes cleanly on SIGTERM/SIGINT."""
    log(f"Received signal {signum} — terminating children.")
    for p in _running_procs:
        if p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
    # Give processes a moment to exit gracefully
    time.sleep(0.5)
    for p in _running_procs:
        if p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
    release_lock()
    sys.exit(0)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run() -> None:
    global _running_procs

    # --- Start fresh log session ---
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    except OSError:
        pass

    log("=== KALI SPLASH PRO START ===")

    if not acquire_lock():
        log("Another instance is already running — exiting.")
        return

    signal.signal(signal.SIGTERM, cleanup_handler)
    signal.signal(signal.SIGINT,  cleanup_handler)

    # --- Wait for display ---
    log("Checking for X Server...")
    if not detect_display():
        release_lock()
        return
    log(f"X Server ready (DISPLAY={os.environ.get('DISPLAY', '?')}).")

    # --- Load config ---
    config = load_config()
    if not config:
        release_lock()
        return

    # --- Get monitor indices ---
    indices = get_monitor_indices()

    # --- Launch mpv per monitor ---
    procs = []
    for mon, monitor_config in config.items():
        vid = choose_video_for_monitor(mon, monitor_config)
        if not vid:
            continue

        idx = indices.get(mon, "0")
        playback_path = resolve_playback_path(vid)
        if playback_path != vid:
            log(f"Using GPU-optimized cache for {vid}")
        log(f"Launching on {mon} (screen {idx}): {playback_path}")

        cmd = build_mpv_command(playback_path, idx)
        try:
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,   # FIX: was captured → pipe deadlock
                stderr=subprocess.DEVNULL,   # FIX: was captured → pipe deadlock
            )
            procs.append(p)
        except (FileNotFoundError, OSError) as e:
            log(f"Failed to launch mpv on {mon}: {e}")

    _running_procs = procs

    # --- Guard Dog ---
    if procs:
        guard_dog(procs)
    else:
        log("No videos launched — nothing to guard.")

    log("Splash sequence finished.")
    release_lock()


if __name__ == "__main__":
    run()
