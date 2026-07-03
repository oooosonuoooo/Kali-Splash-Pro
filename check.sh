#!/usr/bin/env bash
# =============================================================================
# Kali Splash Pro — Health Check / Self-Test Script
# Run this to diagnose installation problems without modifying anything.
# =============================================================================

set -u

APP_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
SRC_DIR="${APP_ROOT}/src"
CONFIG="${APP_ROOT}/config.json"
LOG="${APP_ROOT}/splash_debug.log"
PLAYER="${SRC_DIR}/player.py"
MANAGER="${SRC_DIR}/manager.py"
AUTOSTART_FILE="${HOME}/.config/autostart/kali-splash-startup.desktop"

PASS=0; FAIL=0; WARN=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  [✔]${RESET} $*"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}  [✘]${RESET} $*"; FAIL=$((FAIL+1)); }
warn() { echo -e "${YELLOW}  [!]${RESET} $*"; WARN=$((WARN+1)); }
hdr()  { echo -e "\n${BOLD}${CYAN}$*${RESET}"; }

hdr "══════════════════════════════════════"
hdr " Kali Splash Pro — Health Check"
hdr "══════════════════════════════════════"

# ── Project files ────────────────────────────────────────────────────────────
hdr "Project Files"
[[ -f "${PLAYER}"  ]] && ok "player.py exists"   || fail "player.py MISSING: ${PLAYER}"
[[ -f "${MANAGER}" ]] && ok "manager.py exists"  || fail "manager.py MISSING: ${MANAGER}"
[[ -f "${CONFIG}"  ]] && ok "config.json exists" || warn "config.json missing (no videos configured)"

# ── Python syntax ────────────────────────────────────────────────────────────
hdr "Python Syntax"
if command -v python3 &>/dev/null; then
    python3 -m py_compile "${PLAYER}"  2>/dev/null && ok "player.py syntax OK"  || fail "player.py has SYNTAX ERRORS"
    python3 -m py_compile "${MANAGER}" 2>/dev/null && ok "manager.py syntax OK" || fail "manager.py has SYNTAX ERRORS"
else
    fail "python3 not found"
fi

# ── Dependencies ─────────────────────────────────────────────────────────────
hdr "Dependencies"
for cmd in python3 mpv xdotool xrandr xset; do
    command -v "${cmd}" &>/dev/null && ok "${cmd}" || fail "${cmd} NOT FOUND"
done
dpkg-query -W -f='${Status}' python3-tk 2>/dev/null | grep -q "install ok installed" \
    && ok "python3-tk" || fail "python3-tk NOT INSTALLED (sudo apt install python3-tk)"

# ── Config validity ──────────────────────────────────────────────────────────
hdr "Config"
if [[ -f "${CONFIG}" ]]; then
    if CONFIG_PATH="${CONFIG}" python3 - <<'PYEOF' 2>/dev/null; then
import json
import os
import sys

with open(os.environ["CONFIG_PATH"], encoding="utf-8") as f:
    data = json.load(f)
sys.exit(0 if isinstance(data, dict) else 1)
PYEOF
        ok "config.json is valid JSON"
        # Check video paths
        CONFIG_PATH="${CONFIG}" python3 - <<'PYEOF'
import json
import os
import sys

with open(os.environ["CONFIG_PATH"], encoding="utf-8") as f:
    cfg = json.load(f)

for mon, vid in cfg.items():
    if not isinstance(vid, str):
        print(f"  \033[31m  [✘]\033[0m  {mon} -> not a string: {vid!r}")
        sys.exit(1)
    if os.path.exists(vid):
        print(f"  \033[32m  [✔]\033[0m  {mon} -> {vid}")
    else:
        print(f"  \033[31m  [✘]\033[0m  {mon} -> FILE NOT FOUND: {vid}")
        sys.exit(1)
PYEOF
        [[ $? -eq 0 ]] && ok "All video paths exist" || warn "Some video paths are missing"
    else
        fail "config.json is NOT valid JSON"
    fi
fi

# ── Autostart ────────────────────────────────────────────────────────────────
hdr "Autostart"
if [[ -f "${AUTOSTART_FILE}" ]]; then
    ok "Autostart file present: ${AUTOSTART_FILE}"
    if command -v desktop-file-validate &>/dev/null; then
        desktop-file-validate "${AUTOSTART_FILE}" >/dev/null 2>&1 \
            && ok "Autostart desktop file validates" \
            || warn "Autostart desktop file has validation warnings"
    fi
    # Extract the script path from Exec= line
    EXEC_LINE="$(grep '^Exec=' "${AUTOSTART_FILE}" 2>/dev/null || true)"
    if [[ -n "${EXEC_LINE}" ]]; then
        SCRIPT_PATH="$(python3 - "${EXEC_LINE}" <<'PYEOF'
import shlex
import sys

line = sys.argv[1]
try:
    args = shlex.split(line.removeprefix("Exec=").strip())
except ValueError:
    sys.exit(1)

if not args:
    sys.exit(1)

first = args[0].split("/")[-1]
if first.startswith("python") and len(args) > 1:
    print(args[1])
else:
    print(args[0])
PYEOF
)"
        if [[ ! -f "${SCRIPT_PATH}" ]]; then
            fail "Autostart path BROKEN — file not found: ${SCRIPT_PATH}"
            fail "Run install.sh to repair, or use the Manager to re-enable."
        elif [[ "$(realpath "${SCRIPT_PATH}" 2>/dev/null)" != "$(realpath "${PLAYER}" 2>/dev/null)" ]]; then
            warn "Autostart points to a DIFFERENT player.py than this repo:"
            warn "  Autostart: ${SCRIPT_PATH}"
            warn "  This repo: ${PLAYER}"
            warn "Run install.sh --repair or re-enable autostart in the Manager."
        else
            ok "Autostart path is correct: ${SCRIPT_PATH}"
        fi
    else
        fail "Autostart file has no Exec= line"
    fi
else
    warn "Autostart not enabled (splash will not run at login)."
fi

# ── Log writability ──────────────────────────────────────────────────────────
hdr "Logs"
if touch "${LOG}" 2>/dev/null; then
    ok "Log file writable: ${LOG}"
else
    fail "Cannot write log file: ${LOG}"
fi
if [[ -f "${LOG}" ]]; then
    LINES="$(wc -l < "${LOG}" 2>/dev/null || echo 0)"
    ok "Log has ${LINES} lines."
    if [[ "${LINES}" -gt 0 ]]; then
        echo "  Last 5 entries:"
        tail -5 "${LOG}" 2>/dev/null | sed 's/^/    /'
    fi
fi

# ── Display ──────────────────────────────────────────────────────────────────
hdr "Display"
if [[ -n "${DISPLAY:-}" ]]; then
    ok "DISPLAY=${DISPLAY}"
    xrandr --listmonitors 2>/dev/null && ok "xrandr working" || warn "xrandr failed"
else
    warn "DISPLAY not set (expected when running from terminal; OK from autostart)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
hdr "══════════════════════════════════════"
echo -e "  ${BOLD}Results:${RESET}  ${GREEN}${PASS} passed${RESET}  |  ${YELLOW}${WARN} warnings${RESET}  |  ${RED}${FAIL} failed${RESET}"
hdr "══════════════════════════════════════"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
    echo -e "${RED}  Some checks FAILED. See messages above.${RESET}"
    exit 1
elif [[ "${WARN}" -gt 0 ]]; then
    echo -e "${YELLOW}  Installation OK but has warnings.${RESET}"
    exit 0
else
    echo -e "${GREEN}  All checks passed! ✔${RESET}"
    exit 0
fi
