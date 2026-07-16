#!/bin/bash
set -euo pipefail

# Enable Telegram travel mode on Iris.
# This script edits only the gitignored live .env file, makes an external
# backup, and restarts the affected services. It must be run as freyja.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <TELEGRAM_ALLOWED_USER_ID>" >&2
    exit 1
fi

ALLOWED_USER_ID="$1"
if ! [[ "${ALLOWED_USER_ID}" =~ ^[0-9]+$ ]]; then
    echo "Error: allowed user ID must be a numeric Telegram user ID." >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
ENV_FILE="${PROJECT_DIR}/.env"
STATE_DIR="${HOME}/.local/state/freyja"
BACKUP_DIR="${STATE_DIR}/env-backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/.env.before-telegram-travel-mode-${TIMESTAMP}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: live .env not found at ${ENV_FILE}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
cp "${ENV_FILE}" "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"

echo "Backup created: ${BACKUP_FILE}"

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

_update_or_append TELEGRAM_ENABLED true
_update_or_append TELEGRAM_ALLOWED_USER_IDS "${ALLOWED_USER_ID}"
_update_or_append TELEGRAM_DIRECT_MESSAGES_ONLY true
_update_or_append TELEGRAM_SMITH_READ_ONLY_ENABLED true
_update_or_append AGENT_SMITH_ENABLED true
_update_or_append AGENT_SMITH_READ_ONLY_ENABLED true
_update_or_append AGENT_SMITH_WRITE_PILOT_ENABLED false
_update_or_append AGENT_SMITH_DRY_RUN_ENABLED false

chmod 600 "${ENV_FILE}"

echo "Configuration updated."

if [[ -x "${PROJECT_DIR}/scripts/restart-director.sh" ]]; then
    echo "Restarting Freyja Director..."
    "${PROJECT_DIR}/scripts/restart-director.sh"
else
    echo "Warning: restart-director.sh not found; Director not restarted." >&2
fi

PLIST_NAME="com.freyja-os.telegram-gateway.plist"
PLIST_SRC="${PROJECT_DIR}/scripts/${PLIST_NAME}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"
LABEL="${PLIST_NAME%.plist}"
SERVICE_DOMAIN="gui/$(id -u)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if [[ -f "${PLIST_SRC}" ]]; then
    mkdir -p "${AGENTS_DIR}"
    cp "${PLIST_SRC}" "${PLIST_DST}"
    chmod 644 "${PLIST_DST}"
    plutil -lint "${PLIST_DST}" >/dev/null

    launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
    for _ in $(seq 1 60); do
        if ! launchctl list "${LABEL}" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done

    launchctl bootstrap "${SERVICE_DOMAIN}" "${PLIST_DST}"
    sleep 2

    if launchctl list "${LABEL}" >/dev/null 2>&1; then
        echo "Telegram gateway LaunchAgent loaded."
    else
        echo "Warning: Telegram gateway LaunchAgent did not load." >&2
    fi
else
    echo "Warning: Telegram gateway plist not found at ${PLIST_SRC}" >&2
fi

echo ""
echo "=== Travel mode enabled ==="
echo "Allowed Telegram user ID: ${ALLOWED_USER_ID}"
echo "To disable, run: ${PROJECT_DIR}/scripts/disable-telegram-travel-mode.sh"
echo "To verify, run: ${PROJECT_DIR}/scripts/verify-telegram-travel-mode.sh"
