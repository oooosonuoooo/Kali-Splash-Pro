# 🚀 Kali Splash Pro
> **The Ultimate Cinematic Boot Experience for Kali Linux (XFCE)**

![Platform](https://img.shields.io/badge/Platform-Kali%20Linux-blue?style=for-the-badge&logo=kali-linux)
![Language](https://img.shields.io/badge/Language-Python%203-yellow?style=for-the-badge&logo=python)
![Engine](https://img.shields.io/badge/Engine-Systemd%20%2B%20MPV-red?style=for-the-badge&logo=youtube)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

<div align="center">
  <img src="https://github.com/user-attachments/assets/f3a1ea14-6110-4f9c-87f3-1ab36cbff7fc" alt="Kali Splash Pro Interface" width="100%">
</div>

---

## 🎬 See It In Action
**Transform your boot sequence.** Eliminate the jarring flicker of the desktop loading screen and replace it with high-performance visuals.

[**▶️ CLICK HERE TO WATCH THE DEMO VIDEO**](https://github.com/user-attachments/assets/ef81223c-818b-40d3-8201-a1329a44e423)

---

## ⚠️ ARCHITECTURAL WARNING: READ BEFORE USE

### 🛑 DO NOT DELETE OR MOVE THIS FOLDER!

**Kali Splash Pro is location-dependent.**
Unlike standard apt packages, this application functions by creating a systemd service link directly to **this specific folder**. It does not install itself into `/usr/bin`.

| Action | Result | Solution |
| :--- | :--- | :--- |
| **Delete Folder** | 💀 **Critical Failure** | The boot service will crash. You must disable the service manually. |
| **Move Folder** | ⚠️ **Broken Link** | The system won't find the script. You must run `install.sh` again in the new location. |

> **💡 PRO TIP:** Move this folder to a permanent "Safe Zone" (e.g., `~/Documents/KaliSplashPro`) **BEFORE** running the installer.

---

## 🔥 Why It's Different

Most splash screens fail because they try to load *before* the graphics driver is ready. **Kali Splash Pro** takes a smarter approach:

* **⚡ Systemd Native Architecture:**
    We ditched the hacky `.xsessionrc` edits. This app uses a dedicated **Systemd User Service**, ensuring a robust, OS-managed startup sequence that respects your system's boot process.

* **🛡️ "Guard Dog" Focus Engine:**
    A background thread runs a combat loop every **0.05 seconds**. It aggressively monitors window stacking and uses `xdotool` to force your video to **Layer 0 (Top)**, preventing the Taskbar or Desktop icons from rendering over your splash screen.

* **🚀 Zero-Latency Rendering:**
    The engine forces `mpv` to use **OpenGL hardware acceleration** (`--vo=gpu --gpu-api=opengl`) and bypasses the X11 Compositor completely. This results in instant, frame-perfect playback with no lag.

* **🔧 Self-Healing Ecosystem:**
    The Manager App isn't just a GUI; it's a doctor. Every time you launch it, it scans your configuration, permissions, and system paths. If it finds a broken link or permission error, it silently fixes it in the background.

---

## 🛠️ Installation Guide

### 1. Prepare the Directory
Download or Clone this repository and move it to its **permanent home**.

### 2. Run the Universal Installer
Open a terminal inside the folder and run:

```bash
chmod +x install.sh
./install.sh
