#!/bin/bash
set -euo pipefail

# Install Freyja's native iMessage connector as the non-admin freyja user.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os-imessage-runtime"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_NAME="com.freyja-os.imessage-connector.plist"
LABEL="${PLIST_NAME%.plist}"
PLIST_SRC="${PROJECT_DIR}/scripts/${PLIST_NAME}"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"
LOG_DIR="${PROJECT_DIR}/logs"
RUN_DIR="${PROJECT_DIR}/run"
SERVICE_DOMAIN="gui/$(id -u)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "Error: runtime directory not found: ${PROJECT_DIR}" >&2
    exit 1
fi

if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
    echo "Error: runtime Python not found at ${PROJECT_DIR}/.venv/bin/python" >&2
    exit 1
fi

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    echo "Error: runtime .env not found at ${PROJECT_DIR}/.env" >&2
    exit 1
fi

mkdir -p "${LOG_DIR}" "${RUN_DIR}" "${AGENTS_DIR}"

if [[ -f "${RUN_DIR}/imessage-connector.pid" ]]; then
    OLD_PID="$(cat "${RUN_DIR}/imessage-connector.pid" 2>/dev/null || true)"
    if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" 2>/dev/null; then
        kill "${OLD_PID}" 2>/dev/null || true
        sleep 1
    fi
fi

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

echo "Freyja iMessage connector LaunchAgent installed and loaded."
echo "Plist: ${PLIST_DST}"
echo "Logs:  ${LOG_DIR}/imessage-connector.log"
