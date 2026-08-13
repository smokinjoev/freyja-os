#!/bin/bash
set -euo pipefail

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: run this installer as the freyja user." >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
CONFIG_DIR="${HOME}/.config/freyja"
CONFIG_FILE="${CONFIG_DIR}/apple-reminders.env"
PLIST_NAME="com.freyja-os.apple-reminders.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LABEL="${PLIST_NAME%.plist}"
DOMAIN="gui/$(id -u)"

test -x "${PROJECT_DIR}/.venv/bin/uvicorn"
HELPER_DIR="${HOME}/.local/lib/freyja"
HELPER_DST="${HELPER_DIR}/apple-reminders-eventkit"
mkdir -p "${CONFIG_DIR}" "${HELPER_DIR}" "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs"
chmod 700 "${CONFIG_DIR}"
/usr/bin/swiftc "${PROJECT_DIR}/src/freyja/reminders/apple_eventkit.swift" -o "${HELPER_DST}"
chmod 700 "${HELPER_DST}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    umask 077
    TOKEN="$(openssl rand -hex 32)"
    BIND_IP="$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null | head -1)"
    BIND_IP="${BIND_IP:-127.0.0.1}"
    {
        printf 'FREYJA_APPLE_REMINDERS_TOKEN=%s\n' "${TOKEN}"
        printf 'FREYJA_APPLE_REMINDERS_BIND_IP=%s\n' "${BIND_IP}"
        printf 'FREYJA_APPLE_REMINDERS_PORT=8766\n'
    } > "${CONFIG_FILE}"
fi
chmod 600 "${CONFIG_FILE}"
chmod 700 "${PROJECT_DIR}/scripts/run-apple-reminders-bridge.sh"
cp "${PROJECT_DIR}/scripts/${PLIST_NAME}" "${PLIST_DST}"
chmod 644 "${PLIST_DST}"
plutil -lint "${PLIST_DST}" >/dev/null
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "${DOMAIN}" "${PLIST_DST}"
sleep 2
launchctl print "${DOMAIN}/${LABEL}" >/dev/null
echo "Apple Reminders bridge installed."
echo "Configuration: ${CONFIG_FILE}"
echo "Log: ${HOME}/Library/Logs/freyja-apple-reminders.log"
