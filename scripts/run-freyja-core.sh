#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/freyja/freyja-os"
TOKEN_FILE="${NEXUS_API_KEY_FILE:-/Users/freyja/.config/freyja/msty-nexus-token}"

export HOME="${HOME:-/Users/freyja}"
export USER="${USER:-freyja}"
export LOGNAME="${LOGNAME:-freyja}"
export PYTHONPATH="${PROJECT_DIR}/src:${PROJECT_DIR}"
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export FREYJA_CORE_HOST="${FREYJA_CORE_HOST:-100.115.228.56}"
export FREYJA_CORE_PORT="${FREYJA_CORE_PORT:-8510}"
export NEXUS_BASE_URL="${NEXUS_BASE_URL:-http://100.94.80.21:3939}"
export NEXUS_API_KEY_FILE="${TOKEN_FILE}"

if [[ ! -s "${NEXUS_API_KEY_FILE}" ]]; then
    echo "Error: Nexus token file is missing or empty: ${NEXUS_API_KEY_FILE}" >&2
    exit 1
fi

cd "${PROJECT_DIR}"
exec "${PROJECT_DIR}/.venv/bin/python" -m freyja.core
