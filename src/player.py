import subprocess
import os
import json
import time
import sys
import datetime

# DYNAMIC PATHS
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")
LOG_FILE = os.path.join(PROJECT_ROOT, "splash_debug.log")

def log(msg):
    with open(LOG_FILE, "a") as f:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        f.write(f"[{ts}] {msg}\n")

def wait_for_display():
    log("Checking for X Server...")
    # Wait up to 10 seconds
    for i in range(100):
        try:
            # Check for DISPLAY env var first
            if not os.environ.get('DISPLAY'):
                os.environ['DISPLAY'] = ':0'
            
            subprocess.check_output("xset q", shell=True, stderr=subprocess.DEVNULL)
            log("X Server is ready.")
            return True
        except:
            time.sleep(0.1)
    log("FATAL: X Server never appeared.")
    return False

def run():
    # Wipe log on start
    with open(LOG_FILE, "w") as f: f.write("--- SYSTEMD SPLASH START ---\n")
    
    if not wait_for_display(): return

    if not os.path.exists(CONFIG_FILE): 
        log("No config file found.")
        return

    with open(CONFIG_FILE) as f: config = json.load(f)

    # Map Monitors
    indices = {}
    try:
        raw = subprocess.check_output("xrandr --listmonitors", shell=True).decode().split('\n')
        for line in raw[1:]:
            parts = line.split()
            indices[parts[-1]] = parts[0].replace(':', '')
    except: pass

    procs = []

    for mon, vid in config.items():
        if os.path.exists(vid):
            idx = indices.get(mon, '0')
            log(f"Launching video on Screen {idx}: {vid}")
            
            # ELON OPTIMIZATION: OpenGL + Hardware Decoding
            cmd = [
                'mpv',
                '--fs', f'--fs-screen={idx}',
                '--vo=gpu', '--gpu-api=opengl',  # COMPATIBILITY + SPEED
                '--hwdec=auto',                  # USE HARDWARE
                '--panscan=1.0',
                '--ontop',
                '--no-border',
                '--no-osc',
                '--no-input-default-bindings',
                '--input-vo-keyboard=no',
                '--input-media-keys=no',
                '--x11-bypass-compositor=yes',
                '--force-window=immediate',
                '--keep-open=no',
                vid
            ]
            procs.append(subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True))

    # GUARD DOG
    if procs:
        log("Guard Dog engaged.")
        try:
            while any(p.poll() is None for p in procs):
                subprocess.call("xdotool search --class mpv windowraise", shell=True)
                subprocess.call("xdotool search --class mpv windowactivate", shell=True)
                time.sleep(0.05)
        except Exception as e:
            log(f"Guard Dog error: {e}")

    log("Splash sequence finished.")

if __name__ == "__main__":
    run()
