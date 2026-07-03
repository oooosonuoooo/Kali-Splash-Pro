#!/usr/bin/env bash
# =============================================================================
# Kali Splash Pro — Installer
# Fixes: no error trap, silent apt failures, all-or-nothing package install,
#        no python3 check, broken desktop Exec= for paths with spaces,
#        gtk-update-icon-cache on missing dir, manager launched without DISPLAY,
#        sed -i .xsessionrc without backup, no uninstall flag.
# =============================================================================
set -euo pipefail

# Print every command on error for easier debugging
trap 'echo "[ERROR] Script failed at line $LINENO. Exit code: $?" >&2' ERR

# ---------------------------------------------------------------------------
# Resolve project root from the script's real location (handles symlinks too)
# ---------------------------------------------------------------------------
APP_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
SRC_DIR="${APP_ROOT}/src"
MANAGER="${SRC_DIR}/manager.py"
PLAYER="${SRC_DIR}/player.py"
ICON="${SRC_DIR}/preview.png"
CONFIG="${APP_ROOT}/config.json"
LOG="${APP_ROOT}/splash_debug.log"

AUTOSTART_DIR="${HOME}/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/kali-splash-startup.desktop"
APP_DESKTOP="${HOME}/.local/share/applications/kali-splash-pro.desktop"

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[*]${RESET} $*"; }
success() { echo -e "${GREEN}[✔]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
error()   { echo -e "${RED}[✘]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}${CYAN}$*${RESET}"; }

config_has_videos() {
    local path="$1"
    [[ -s "${path}" ]] || return 1
    CONFIG_PATH="${path}" python3 - <<'PYEOF'
import json
import os
import sys

try:
    with open(os.environ["CONFIG_PATH"], encoding="utf-8") as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    sys.exit(1)

if not isinstance(data, dict) or not data:
    sys.exit(1)

for value in data.values():
    if isinstance(value, str) and value:
        sys.exit(0)
sys.exit(1)
PYEOF
}

find_migratable_config() {
    local current_root
    current_root="$(realpath "${APP_ROOT}")"

    while IFS= read -r candidate; do
        local candidate_root
        candidate_root="$(realpath "$(dirname "${candidate}")")"
        [[ "${candidate_root}" == "${current_root}" ]] && continue
        [[ -f "${candidate_root}/src/player.py" ]] || continue
        if config_has_videos "${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done < <(
        find "${HOME}" -maxdepth 4 -type f -name config.json \
            -path '*/Kali*Splash*/config.json' 2>/dev/null | sort
    )

    return 1
}

migrate_existing_config_if_needed() {
    if config_has_videos "${CONFIG}"; then
        return 0
    fi

    local old_config
    old_config="$(find_migratable_config || true)"
    if [[ -z "${old_config}" ]]; then
        return 0
    fi

    if [[ -f "${CONFIG}" ]]; then
        cp "${CONFIG}" "${CONFIG}.pre-migration-backup"
        warn "Backed up existing empty/invalid config to config.json.pre-migration-backup."
    fi
    cp "${old_config}" "${CONFIG}"
    success "Migrated existing video config from: ${old_config}"
}

# ---------------------------------------------------------------------------
# Uninstall mode
# ---------------------------------------------------------------------------
uninstall_mode() {
    header "═══ KALI SPLASH PRO — UNINSTALL ═══"

    # Remove autostart entry
    if [[ -f "${AUTOSTART_FILE}" ]]; then
        rm -f "${AUTOSTART_FILE}"
        success "Removed autostart entry."
    else
        info "Autostart entry was not present."
    fi

    # Remove application shortcut
    if [[ -f "${APP_DESKTOP}" ]]; then
        rm -f "${APP_DESKTOP}"
        success "Removed application shortcut."
    fi

    # Disable legacy systemd service if present
    LEGACY_SERVICE="${HOME}/.config/systemd/user/kali-splash.service"
    if [[ -f "${LEGACY_SERVICE}" ]]; then
        systemctl --user disable kali-splash 2>/dev/null || true
        rm -f "${LEGACY_SERVICE}"
        systemctl --user daemon-reload 2>/dev/null || true
        success "Removed legacy systemd service."
    fi

    # Clean up old .xsessionrc entries if present
    if [[ -f "${HOME}/.xsessionrc" ]]; then
        if grep -q 'KaliSplashPro\|player\.py' "${HOME}/.xsessionrc" 2>/dev/null; then
            cp "${HOME}/.xsessionrc" "${HOME}/.xsessionrc.ksp-backup"
            sed -i '/KaliSplashPro/d; /player\.py/d' "${HOME}/.xsessionrc"
            success "Cleaned .xsessionrc (backup at .xsessionrc.ksp-backup)."
        fi
    fi

    echo ""
    success "Uninstall complete. The repository folder is untouched."
    info "To fully remove the app, delete: ${APP_ROOT}"
    exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case "${arg}" in
        --uninstall|-u) uninstall_mode ;;
        --help|-h)
            echo "Usage: $0 [--uninstall | --help]"
            echo "  (no args)    Install / repair Kali Splash Pro"
            echo "  --uninstall  Remove autostart and shortcuts"
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
header "═══════════════════════════════════════"
header " KALI SPLASH PRO — INSTALLER"
header "═══════════════════════════════════════"
echo ""
info "App root: ${APP_ROOT}"

# ---------------------------------------------------------------------------
# Sanity: must be run from inside the project folder (or it auto-detects fine)
# ---------------------------------------------------------------------------
if [[ ! -f "${PLAYER}" ]]; then
    error "Cannot find src/player.py at: ${PLAYER}"
    error "Ensure you are running install.sh from inside the Kali-Splash-Pro folder."
    exit 1
fi

# ---------------------------------------------------------------------------
# Dependency check and install (only missing packages)
# ---------------------------------------------------------------------------
header "Checking dependencies…"

MISSING_PKGS=()

add_missing_pkg() {
    local pkg="$1"
    local existing
    for existing in "${MISSING_PKGS[@]:-}"; do
        [[ "${existing}" == "${pkg}" ]] && return
    done
    MISSING_PKGS+=("${pkg}")
}

need_cmd() {
    local cmd="$1" pkg="$2"
    if ! command -v "${cmd}" &>/dev/null; then
        warn "${cmd} not found (package: ${pkg})"
        add_missing_pkg "${pkg}"
    else
        success "${cmd} found."
    fi
}

need_dpkg() {
    local pkg="$1"
    if ! dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null | grep -q "install ok installed"; then
        warn "${pkg} not installed."
        add_missing_pkg "${pkg}"
    else
        success "${pkg} found."
    fi
}

# Check python3 explicitly
if ! command -v python3 &>/dev/null; then
    error "python3 is not installed. Install it with: sudo apt install python3"
    exit 1
fi
success "python3 found ($(python3 --version 2>&1))."

need_cmd  "mpv"     "mpv"
need_cmd  "xdotool" "xdotool"
need_cmd  "xrandr"  "x11-xserver-utils"
need_cmd  "xset"    "x11-xserver-utils"
need_dpkg "python3-tk"

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    warn "Missing packages: ${MISSING_PKGS[*]}"
    info "Installing missing packages (sudo required)…"
    sudo apt-get update -qq
    sudo apt-get install -y "${MISSING_PKGS[@]}"
    success "All missing packages installed."
else
    success "All dependencies satisfied."
fi

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
header "Setting file permissions…"
chmod +x "${MANAGER}" "${PLAYER}"
success "Permissions set."

# ---------------------------------------------------------------------------
# Clean up legacy .xsessionrc hacks (with backup)
# ---------------------------------------------------------------------------
if [[ -f "${HOME}/.xsessionrc" ]]; then
    if grep -q 'KaliSplashPro\|player\.py' "${HOME}/.xsessionrc" 2>/dev/null; then
        header "Removing old startup hacks from .xsessionrc…"
        cp "${HOME}/.xsessionrc" "${HOME}/.xsessionrc.ksp-backup"
        sed -i '/KaliSplashPro/d; /player\.py/d' "${HOME}/.xsessionrc"
        success "Cleaned .xsessionrc (backup at .xsessionrc.ksp-backup)."
    fi
fi

# ---------------------------------------------------------------------------
# Disable legacy systemd service if present
# ---------------------------------------------------------------------------
LEGACY_SERVICE="${HOME}/.config/systemd/user/kali-splash.service"
if [[ -f "${LEGACY_SERVICE}" ]]; then
    header "Removing legacy systemd service…"
    systemctl --user disable kali-splash 2>/dev/null || true
    rm -f "${LEGACY_SERVICE}"
    systemctl --user daemon-reload 2>/dev/null || true
    success "Legacy service removed."
fi

# ---------------------------------------------------------------------------
# Pre-create config and log (if absent)
# ---------------------------------------------------------------------------
migrate_existing_config_if_needed
if [[ ! -f "${CONFIG}" ]]; then
    echo '{}' > "${CONFIG}"
    success "Created empty config.json."
fi
touch "${LOG}" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Create application .desktop shortcut
# ---------------------------------------------------------------------------
header "Creating application shortcut…"
mkdir -p "${HOME}/.local/share/applications"

ICON_VAL="utilities-terminal"
if [[ -f "${ICON}" ]]; then
    ICON_VAL="${ICON}"
fi

# Properly quote the Exec path to handle spaces
cat > "${APP_DESKTOP}" <<EOF
[Desktop Entry]
Version=1.0
Name=Kali Splash Pro
Comment=Custom Login Splash Screen Manager
Exec=/usr/bin/python3 "${MANAGER}"
Icon=${ICON_VAL}
Terminal=false
Type=Application
Categories=Settings;
StartupNotify=true
EOF
success "Shortcut created at: ${APP_DESKTOP}"

# Refresh icon cache only if the directory exists
if [[ -d "${HOME}/.local/share/icons" ]]; then
    gtk-update-icon-cache -f -t "${HOME}/.local/share/icons" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------------------
# Update autostart entry to current path (fix broken path after repo move)
# ---------------------------------------------------------------------------
if [[ -f "${AUTOSTART_FILE}" ]]; then
    header "Repairing autostart entry path…"
    mkdir -p "${AUTOSTART_DIR}"
    cat > "${AUTOSTART_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=Kali Splash Pro
Exec=/usr/bin/python3 "${PLAYER}"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Start Kali Splash Pro on login
EOF
    success "Autostart entry path updated to current location."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
header "═══════════════════════════════════════"
echo -e "${GREEN}${BOLD} ✔  INSTALLATION COMPLETE${RESET}"
header "═══════════════════════════════════════"
echo ""
echo -e "  ${BOLD}App location:${RESET} ${APP_ROOT}"
echo -e "  ${BOLD}Next steps:${RESET}"
echo "    1. Run 'Kali Splash Pro' from your application menu, or:"
echo "       python3 \"${MANAGER}\""
echo "    2. Select a video file for each monitor."
echo "    3. Click 'Save Config'."
echo "    4. Click 'Enable Autostart'."
echo "    5. Reboot to test."
echo ""
echo -e "  ${BOLD}To uninstall:${RESET} bash \"${APP_ROOT}/install.sh\" --uninstall"
echo ""
