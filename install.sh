#!/bin/bash

echo "-----------------------------------"
echo " KALI SPLASH PRO: ROBUST INSTALLER"
echo "-----------------------------------"

# 1. SETUP PATHS
APP_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC_DIR="$APP_ROOT/src"
MANAGER="$SRC_DIR/manager.py"
PLAYER="$SRC_DIR/player.py"
ICON="$SRC_DIR/preview.png"

echo "[*] App Location: $APP_ROOT"

# 2. INSTALL DEPENDENCIES
echo "[*] Checking Dependencies..."
MISSING=""
if ! command -v mpv &> /dev/null; then MISSING="$MISSING mpv"; fi
if ! dpkg -s python3-tk &> /dev/null; then MISSING="$MISSING python3-tk"; fi
if ! command -v xdotool &> /dev/null; then MISSING="$MISSING xdotool"; fi

if [ -n "$MISSING" ]; then
    echo "[!] Missing tools:$MISSING"
    echo "[*] Installing them now (requires password)..."
    sudo apt update -qq && sudo apt install -y mpv python3-tk xdotool
else
    echo "[+] All dependencies installed."
fi

# 3. FIX PERMISSIONS & CLEANUP
echo "[*] Setting Permissions..."
chmod +x "$MANAGER" "$PLAYER"

# Remove old hacks
echo "[*] Cleaning old startup hacks..."
sed -i '/KaliSplashPro/d' "$HOME/.xsessionrc" 2>/dev/null
sed -i '/player.py/d' "$HOME/.xsessionrc" 2>/dev/null

# 4. ICON SETUP
# Use the custom icon if it exists, otherwise use a generic system icon
FINAL_ICON="utilities-terminal"
if [ -f "$ICON" ]; then
    FINAL_ICON="$ICON"
else
    echo "[!] No custom icon (preview.png) found in src/. Using default."
fi

# 5. CREATE DESKTOP SHORTCUT
echo "[*] Creating Desktop Entry..."
mkdir -p "$HOME/.local/share/applications"

cat << EODESK > "$HOME/.local/share/applications/kali-splash-pro.desktop"
[Desktop Entry]
Version=1.0
Name=Kali Splash Pro
Comment=Custom Login Splash Screen
Exec=/usr/bin/python3 "$MANAGER"
Icon=$FINAL_ICON
Terminal=false
Type=Application
Categories=Settings;Utility;
StartupNotify=true
EODESK

# Refresh Cache
touch "$HOME/.local/share/applications/kali-splash-pro.desktop"
gtk-update-icon-cache -f -t ~/.local/share/icons >/dev/null 2>&1

echo "-----------------------------------"
echo " ✅ INSTALLATION COMPLETE"
echo "-----------------------------------"
echo "1. Run 'Kali Splash Pro' from your menu."
echo "2. Select a video."
echo "3. Click 'Enable Autostart'."
echo "4. Reboot to test."
echo "-----------------------------------"

# Launch immediately
python3 "$MANAGER" &

