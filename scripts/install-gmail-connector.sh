#!/bin/bash
set -euo pipefail

# Install Freyja's Gmail connector LaunchAgent.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_NAME="com.freyja-os.gmail-connector.plist"
LABEL="${PLIST_NAME%.plist}"
PLIST_SRC="${PROJECT_DIR}/scripts/${PLIST_NAME}"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"
LOG_DIR="${PROJECT_DIR}/logs"
SERVICE_DOMAIN="gui/$(id -u)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
    echo "Error: Python not found at ${PROJECT_DIR}/.venv/bin/python" >&2
    exit 1
fi

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    echo "Error: .env not found at ${PROJECT_DIR}/.env" >&2
    exit 1
fi

mkdir -p "${LOG_DIR}" "${AGENTS_DIR}"

launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
sleep 1

cp "${PLIST_SRC}" "${PLIST_DST}"
chmod 644 "${PLIST_DST}"
plutil -lint "${PLIST_DST}" >/dev/null

launchctl bootstrap "${SERVICE_DOMAIN}" "${PLIST_DST}"
sleep 2

if ! launchctl print "${SERVICE_TARGET}" >/dev/null 2>&1; then
    echo "Error: LaunchAgent ${PLIST_NAME} did not load." >&2
    exit 1
fi

launchctl kickstart -k "${SERVICE_TARGET}" >/dev/null 2>&1 || true

echo "Freyja Gmail connector LaunchAgent installed and loaded."
echo "Plist: ${PLIST_DST}"
echo "Logs:  ${LOG_DIR}/gmail-connector.log"
