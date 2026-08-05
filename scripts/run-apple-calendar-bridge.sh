#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/freyja/freyja-os"
CONFIG_FILE="${HOME}/.config/freyja/apple-calendar.env"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Missing Apple Calendar bridge configuration: ${CONFIG_FILE}" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
set +a

exec "${PROJECT_DIR}/.venv/bin/uvicorn" freyja.apple_calendar_app:app \
    --host "${FREYJA_APPLE_CALENDAR_BIND_IP:-127.0.0.1}" \
    --port "${FREYJA_APPLE_CALENDAR_PORT:-8765}" \
    --log-level info
