#!/usr/bin/env bash
# =============================================================================
# Kali Splash Pro — Uninstaller
# Shortcut wrapper: delegates to install.sh --uninstall
# =============================================================================
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
exec bash "${APP_ROOT}/install.sh" --uninstall "$@"
