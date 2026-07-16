#!/bin/bash
set -euo pipefail

# Disable Telegram travel mode and restore safe defaults.
# This script edits only the gitignored live .env file. It is idempotent.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
ENV_FILE="${PROJECT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: live .env not found at ${ENV_FILE}" >&2
    exit 1
fi

_update_or_append() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key}=" "${ENV_FILE}"; then
        sed -i.bak.tmp "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
        rm -f "${ENV_FILE}.bak.tmp"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

_update_or_append TELEGRAM_ENABLED false
_update_or_append TELEGRAM_ALLOWED_USER_IDS ""
_update_or_append TELEGRAM_DIRECT_MESSAGES_ONLY true
_update_or_append TELEGRAM_SMITH_READ_ONLY_ENABLED false
_update_or_append AGENT_SMITH_ENABLED false
_update_or_append AGENT_SMITH_READ_ONLY_ENABLED false
_update_or_append AGENT_SMITH_WRITE_PILOT_ENABLED false
_update_or_append AGENT_SMITH_DRY_RUN_ENABLED false

chmod 600 "${ENV_FILE}"

echo "Configuration updated."

PLIST_NAME="com.freyja-os.telegram-gateway.plist"
LABEL="${PLIST_NAME%.plist}"
SERVICE_DOMAIN="gui/$(id -u)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "${SERVICE_TARGET}" >/dev/null 2>&1 || true
    echo "Telegram gateway LaunchAgent unloaded."
else
    echo "Telegram gateway LaunchAgent was not loaded."
fi

if [[ -x "${PROJECT_DIR}/scripts/restart-director.sh" ]]; then
    echo "Restarting Freyja Director..."
    "${PROJECT_DIR}/scripts/restart-director.sh"
else
    echo "Warning: restart-director.sh not found; Director not restarted." >&2
fi

echo ""
echo "=== Travel mode disabled ==="
echo "Telegram gateway and Agent Smith are disabled."
echo "Run ${PROJECT_DIR}/scripts/verify-telegram-travel-mode.sh to confirm."
