import tkinter as tk
from tkinter import filedialog
import subprocess
import os
import json

# PATHS
HOME = os.path.expanduser("~")
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")
PLAYER_SCRIPT = os.path.join(CURRENT_DIR, "player.py")
LOGO_PATH = os.path.join(CURRENT_DIR, "preview.png")

# AUTOSTART FILE
AUTOSTART_DIR = os.path.join(HOME, ".config/autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "kali-splash-startup.desktop")

# LEGACY SERVICE FILE (For Cleanup)
LEGACY_SERVICE = os.path.join(HOME, ".config/systemd/user/kali-splash.service")

def check_autostart():
    return os.path.exists(AUTOSTART_FILE)

def toggle_autostart(lbl, btn):
    # Cleanup legacy if exists
    if os.path.exists(LEGACY_SERVICE):
        try:
            subprocess.run(["systemctl", "--user", "disable", "kali-splash"], stderr=subprocess.DEVNULL)
            os.remove(LEGACY_SERVICE)
            subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
        except: pass

    if check_autostart():
        # DISABLE
        if os.path.exists(AUTOSTART_FILE): os.remove(AUTOSTART_FILE)
        
        lbl.config(text="Status: DISABLED ❌", fg="#ff5555")
        btn.config(text="Enable Autostart")
    else:
        # ENABLE (Create Desktop File)
        if not os.path.exists(AUTOSTART_DIR): os.makedirs(AUTOSTART_DIR)
        
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Kali Splash Pro Startup
Exec=/usr/bin/python3 {PLAYER_SCRIPT}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name[en_US]=Kali Splash Pro Startup
Comment[en_US]=Start Kali Splash Pro
"""
        with open(AUTOSTART_FILE, "w") as f: f.write(desktop_content)
        
        lbl.config(text="Status: AUTOSTART ACTIVE ⚡", fg="#00ff00")
        btn.config(text="Disable Autostart")

# GUI UTILS
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

def browse(mon, var):
    f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.avi")])
    if f:
        var.set(f)
        c = load_config()
        c[mon] = f
        save_config(c)
        
def get_monitors():
    try:
        out = subprocess.check_output("xrandr --listmonitors", shell=True).decode()
        return [l.split()[-1] for l in out.strip().split('\n')[1:]]
    except: return ["Default"]

# GUI SETUP
root = tk.Tk()
root.title("Kali Splash Pro (Autostart)")
root.geometry("650x500")
root.configure(bg="#1a1a1a")

# Header
header = tk.Frame(root, bg="#1a1a1a", pady=15)
header.pack(fill="x")
try:
    if os.path.exists(LOGO_PATH):
        img = tk.PhotoImage(file=LOGO_PATH)
        while img.width() > 80: img = img.subsample(2, 2)
        root.logo_ref = img 
        root.iconphoto(False, img)
        tk.Label(header, image=img, bg="#1a1a1a").pack(side="left", padx=(20, 10))
except: pass
tk.Label(header, text="KALI SPLASH PRO", font=("Sans", 20, "bold"), bg="#1a1a1a", fg="#257ace").pack(side="left")

# Monitor List
list_frame = tk.Frame(root, bg="#1a1a1a")
list_frame.pack(fill="both", expand=True, padx=20)
conf = load_config()
for mon in get_monitors():
    r = tk.Frame(list_frame, bg="#252525", pady=8, padx=8)
    r.pack(fill="x", pady=5)
    tk.Label(r, text=mon, bg="#252525", fg="white", width=10, font=("Sans", 10, "bold")).pack(side="left")
    v = tk.StringVar(value=conf.get(mon, ""))
    tk.Entry(r, textvariable=v, bg="#333", fg="#aaa", borderwidth=0).pack(side="left", fill="x", expand=True, padx=10)
    tk.Button(r, text="📂", command=lambda m=mon, x=v: browse(m,x), bg="#444", fg="white", relief="flat").pack(side="left", padx=2)
    tk.Button(r, text="▶", command=lambda x=v: preview(x), bg="#257ace", fg="white", relief="flat").pack(side="left", padx=2)

def preview(var):
    if os.path.exists(var.get()):
        subprocess.Popen(f"mpv --fs --panscan=1.0 --ontop --force-window=immediate '{var.get()}'", shell=True)

# Footer
btm = tk.Frame(root, bg="#1a1a1a")
btm.pack(side="bottom", fill="x", pady=20, padx=20)
stat = tk.Label(btm, text="Checking...", bg="#1a1a1a", fg="white")
stat.pack(side="left")
btn = tk.Button(btm, text="Action", command=lambda: toggle_autostart(stat, btn), bg="#444", fg="white", font=("Sans", 11, "bold"), width=20)
btn.pack(side="right")

# Initial Status
if check_autostart():
    stat.config(text="Status: AUTOSTART ACTIVE ⚡", fg="#00ff00")
    btn.config(text="Disable Autostart")
else:
    stat.config(text="Status: DISABLED ❌", fg="#ff5555")
    btn.config(text="Enable Autostart")

root.mainloop()
