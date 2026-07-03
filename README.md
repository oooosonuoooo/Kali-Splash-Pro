# 🚀 Kali Splash Pro

> **Cinematic login splash screen for Kali Linux XFCE — powered by mpv + XDG autostart**

![Platform](https://img.shields.io/badge/Platform-Kali%20Linux%20XFCE-blue?style=for-the-badge&logo=kali-linux)
![Language](https://img.shields.io/badge/Language-Python%203-yellow?style=for-the-badge&logo=python)
![Engine](https://img.shields.io/badge/Engine-MPV%20%2B%20Autostart-red?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

Replaces the jarring flicker of a bare XFCE desktop loading with a smooth fullscreen video played the moment your session starts. Controlled via a clean GUI manager — no manual config file editing needed.

---

## 🎬 See It In Action

<div align="center">
  <img src="https://github.com/user-attachments/assets/f3a1ea14-6110-4f9c-87f3-1ab36cbff7fc" alt="Kali Splash Pro Interface" width="100%">
</div>

[**▶️ Watch the demo video**](https://github.com/user-attachments/assets/ef81223c-818b-40d3-8201-a1329a44e423)

---

## 📋 Table of Contents

1. [Requirements](#-requirements)
2. [Installation](#-installation)
3. [How to Use](#-how-to-use)
4. [How It Works](#-how-it-works)
5. [Changing the Splash Video](#-changing-the-splash-video)
6. [Enable / Disable Autostart](#-enable--disable-autostart)
7. [Troubleshooting](#-troubleshooting)
8. [Uninstall](#-uninstall)
9. [Known Limitations](#-known-limitations)
10. [Testing](#-testing)
11. [Architecture Notes](#-architecture-notes)
12. [Changelog](#-changelog)

---

## ✅ Requirements

| Package | Purpose | Auto-installed |
|---------|---------|----------------|
| `python3` | Runs manager and player | Must be present |
| `python3-tk` | GUI manager | ✔ via apt |
| `mpv` | Video playback | ✔ via apt |
| `xdotool` | Window focus control | ✔ via apt |
| `x11-xserver-utils` | `xrandr` monitor detection and `xset` X readiness checks | ✔ via apt |

> **Optional:** Install `python3-pil` (`python3-pillow`) for proper PNG icon support in the manager window.

**Tested on:** Kali Linux 2024.x / 2025.x, XFCE desktop, X11 session.

> ⚠️ Wayland sessions are not supported. Ensure your Kali XFCE session uses X11.

---

## 📦 Installation

### Step 1 — Choose a permanent home for the folder

> **Important:** The autostart entry links directly to this folder. If you move the folder later, run `install.sh` again to repair the link.

Recommended permanent location:
```bash
mkdir -p ~/Applications
mv ~/Downloads/Kali-Splash-Pro ~/Applications/Kali-Splash-Pro
cd ~/Applications/Kali-Splash-Pro
```

### Step 2 — Run the installer

```bash
chmod +x install.sh
./install.sh
```

The installer will:
- Check for and install any missing dependencies via `apt`
- Set correct file permissions
- Create an application shortcut in your menu
- Create runtime `config.json` and `splash_debug.log` if missing
- Clean up any old `.xsessionrc` hacks from previous versions
- Repair the autostart entry path if the repo was moved

### Step 3 — Open the Manager

```bash
python3 src/manager.py
```

Or launch **Kali Splash Pro** from your application menu.

---

## 🎮 How to Use

The Manager GUI has three main sections:

### 🖥 Monitors & Videos
- Each connected monitor is listed (detected via `xrandr`)
- Click **📂 Browse** to choose a video file for that monitor
- Click **💾 Save Config** to write your choices to `config.json`
- Click **▶ Preview** to test the video in fullscreen without rebooting

### ⚙ Dependencies
- Shows green ✔ or red ✘ for each required tool
- If a dependency shows ✘, run `install.sh` again to install it

### Status Bar
- **Autostart**: ENABLED or DISABLED
- **Path**: Valid ✔ or BROKEN ✘ (run install.sh to repair after moving the folder)
- **Config**: OK or Missing/Empty

### Footer Buttons
| Button | Action |
|--------|--------|
| 📋 View Logs | Opens the debug log in a scrollable window |
| 🧪 Test Splash Now | Runs the splash immediately without rebooting |
| 🗑 Remove Autostart | Removes the autostart entry |
| Enable/Disable Autostart | Toggles login autostart |

---

## 🔧 How It Works

```
Login → XFCE session starts → Autostart .desktop fires
  → python3 src/player.py
    → Waits for X server (up to 10 s)
    → Reads config.json
    → Detects monitors via xrandr
    → Launches mpv fullscreen (OpenGL + hardware decode)
    → Guard Dog: keeps mpv on top for first 5 s (fast), then every 0.5 s
    → Video ends → mpv exits → player.py exits → desktop appears normally
```

### Key design choices
- **Autostart `.desktop` file** in `~/.config/autostart/` — the correct XFCE/GNOME mechanism (not `.xsessionrc`, not systemd user services at login)
- **Lock file** at `/tmp/kali-splash.lock` — prevents duplicate launches if autostart fires twice
- **Guard Dog** uses adaptive polling: 0.05 s for the first 5 s (beats compositor/taskbar), then backs off to 0.5 s (saves CPU)
- **mpv** uses OpenGL + hardware decoding for zero-lag playback
- **All paths** resolved from the script's real location — works regardless of CWD

---

## 🎬 Changing the Splash Video

1. Open **Kali Splash Pro** from the menu (or `python3 src/manager.py`)
2. Find your monitor name (e.g. `HDMI-0`)
3. Click **📂 Browse** → select your `.mp4`, `.mkv`, `.avi`, or `.webm` file
4. Click **💾 Save Config**
5. Click **🧪 Test Splash Now** to preview it

Supported formats: anything mpv can play (MP4, MKV, AVI, WebM, MOV, etc.)

---

## ✔ Enable / Disable Autostart

### Enable
Click **Enable Autostart** in the Manager. This creates:
```
~/.config/autostart/kali-splash-startup.desktop
```
Reboot to activate.

### Disable
Click **Disable Autostart** (or **🗑 Remove Autostart**) in the Manager. The `.desktop` file is removed. No other system files are touched.

### After moving the folder
If you move the project folder, the autostart path breaks. Fix it:
```bash
cd /new/path/to/Kali-Splash-Pro
./install.sh
```
Then re-enable autostart in the Manager.

---

## 🔍 Troubleshooting

### Run the health check first
```bash
./check.sh
```
This diagnoses the most common issues without modifying anything.

### Splash doesn't start at login
1. Run `./check.sh` — check for BROKEN autostart path
2. If path is broken: run `./install.sh` then re-enable autostart in Manager
3. Check `splash_debug.log` (click **📋 View Logs** in the Manager)
4. Ensure `DISPLAY=:0` is set: `echo $DISPLAY`
5. Ensure video file still exists at the configured path

### Video plays but desktop shows underneath / flickers
- Compositor conflict: disable Compton/Picom temporarily during video or set `--x11-bypass-compositor=yes` (already set)
- Try a different `--vo` option in `player.py` (e.g. `--vo=xv` for older cards)

### mpv crashes or hangs
```bash
# Test mpv directly:
mpv --fs --vo=gpu --gpu-api=opengl /path/to/your/video.mp4
# If that fails, try:
mpv --fs --vo=xv /path/to/your/video.mp4
```

### Manager GUI won't open
```bash
python3 -c "import tkinter; print('OK')"
# If this fails:
sudo apt install python3-tk
```

### Preview button does nothing
- Ensure `mpv` is installed: `which mpv`
- Check the video path is correct and the file exists

### "Another instance already running" in log
The lock file `/tmp/kali-splash.lock` was left from a previous crash. Delete it:
```bash
rm -f /tmp/kali-splash.lock
```

---

## 🧪 Testing

Automated checks:

```bash
python3 -m py_compile src/player.py src/manager.py
bash -n install.sh check.sh uninstall.sh
python3 -m unittest discover -s tests -v
./check.sh
```

Manual release checklist:

```text
docs/manual-verification.md
```

---

## 🗑 Uninstall

```bash
./uninstall.sh
# or equivalently:
./install.sh --uninstall
```

This removes:
- `~/.config/autostart/kali-splash-startup.desktop`
- `~/.local/share/applications/kali-splash-pro.desktop`
- Any legacy systemd user service from old versions

It does **not** delete the project folder or your video files.

To fully remove everything:
```bash
./uninstall.sh
rm -rf /path/to/Kali-Splash-Pro
```

---

## ⚠️ Known Limitations

| Limitation | Notes |
|-----------|-------|
| X11 only | Wayland is not supported (mpv `--fs-screen` and `xdotool` are X11-specific) |
| Login session only | Works only in a full XFCE/X11 session; not at GDM/LightDM level |
| Folder must stay put | Moving the folder breaks the autostart link (run `install.sh` to repair) |
| Single video per monitor | Each monitor plays one video; no playlist support |
| No Wayland guard dog | `xdotool` is unavailable on Wayland |
| Lock file persistence | If player.py crashes hard, delete `/tmp/kali-splash.lock` manually |

---

## 🏗 Architecture Notes

```
Kali-Splash-Pro/
├── install.sh        # Installer + uninstaller (--uninstall flag)
├── uninstall.sh      # Shortcut to install.sh --uninstall
├── check.sh          # Non-destructive health check
├── config.example.json
├── CHANGELOG.md
├── docs/
│   ├── MAINTENANCE_LOG.md
│   └── manual-verification.md
├── tests/
│   └── test_core.py
└── src/
    ├── player.py     # Splash player (launched at login)
    ├── manager.py    # GUI manager (tkinter)
    └── preview.png   # App icon
```

### config.json format
`config.json` is generated locally by the Manager or installer and intentionally ignored by Git. Use `config.example.json` as the template:

```json
{
    "HDMI-0": "/home/user/Videos/splash.mp4",
    "HDMI-1": "/home/user/Videos/splash2.mp4"
}
```
Monitor names come from `xrandr --listmonitors`. Run `xrandr --listmonitors` to see yours.

---

## 📜 Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

## 📜 License

MIT — see [LICENSE](LICENSE)
