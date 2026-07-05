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
import tempfile

# ---------------------------------------------------------------------------
# DYNAMIC PATHS — resolved from this file's real location, not CWD
# ---------------------------------------------------------------------------
CURRENT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
CONFIG_FILE  = os.path.join(PROJECT_ROOT, "config.json")
LOG_FILE     = os.path.join(PROJECT_ROOT, "splash_debug.log")
LOCK_FILE    = os.path.join(tempfile.gettempdir(), "kali-splash.lock")

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
GUARD_INITIAL_INTERVAL  = 0.05   # fast for the first few seconds
GUARD_INITIAL_DURATION  = 5.0    # seconds of fast polling at start
GUARD_NORMAL_INTERVAL   = 0.5    # then back off to 0.5 s

def guard_dog(procs: list) -> None:
    """
    Keep mpv windows on top while any process is alive.
    Uses fast polling at startup (to beat compositor/taskbar),
    then backs off to save CPU.
    """
    log("Guard Dog engaged.")
    start_time = time.monotonic()

    try:
        while any(p.poll() is None for p in procs):
            elapsed = time.monotonic() - start_time
            interval = (GUARD_INITIAL_INTERVAL if elapsed < GUARD_INITIAL_DURATION
                        else GUARD_NORMAL_INTERVAL)

            # Only call xdotool when mpv windows actually exist
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--class", "mpv"],
                    capture_output=True, timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    subprocess.run(
                        ["xdotool", "search", "--class", "mpv", "windowraise"],
                        capture_output=True, timeout=2,
                    )
                    subprocess.run(
                        ["xdotool", "search", "--class", "mpv", "windowactivate"],
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

    # --- Duplicate guard ---
    if not acquire_lock():
        log("Another instance is already running — exiting.")
        return

    # --- Signal handlers ---
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
        log(f"Launching on {mon} (screen {idx}): {vid}")

        cmd = [
            "mpv",
            "--fs",
            f"--fs-screen={idx}",
            "--vo=gpu",
            "--gpu-api=opengl",   # OpenGL for broadest compatibility
            "--hwdec=auto",        # hardware decoding when available
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
            vid,
        ]
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
