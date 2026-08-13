#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/freyja/freyja-os"
CONFIG_FILE="${HOME}/.config/freyja/apple-reminders.env"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Missing Apple Reminders bridge configuration: ${CONFIG_FILE}" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
set +a

export PYTHONPATH="${PROJECT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export FREYJA_APPLE_REMINDERS_HELPER="${HOME}/.local/lib/freyja/apple-reminders-eventkit"

exec "${PROJECT_DIR}/.venv/bin/uvicorn" freyja.apple_reminders_app:app \
    --host "${FREYJA_APPLE_REMINDERS_BIND_IP:-127.0.0.1}" \
    --port "${FREYJA_APPLE_REMINDERS_PORT:-8766}" \
    --log-level info
