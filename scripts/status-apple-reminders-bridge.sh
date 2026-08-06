#!/bin/bash
set -euo pipefail

LABEL="com.freyja-os.apple-reminders"
DOMAIN="gui/$(id -u)"
CONFIG_FILE="${HOME}/.config/freyja/apple-reminders.env"

launchctl print "${DOMAIN}/${LABEL}" | sed -n '1,30p'
if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${CONFIG_FILE}"
    curl --fail --silent --show-error \
        -H "Authorization: Bearer ${FREYJA_APPLE_REMINDERS_TOKEN}" \
        "http://${FREYJA_APPLE_REMINDERS_BIND_IP}:${FREYJA_APPLE_REMINDERS_PORT:-8766}/health"
    printf '\n'
fi
