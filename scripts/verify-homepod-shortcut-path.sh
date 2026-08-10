#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/freyja/freyja-os"
RUNTIME_DIR="/Users/freyja/freyja-os-imessage-runtime"
STATUS_SCRIPT="${PROJECT_DIR}/scripts/status-imessage-connector.sh"
RUNTIME_ENV="${RUNTIME_DIR}/.env"

echo "=== Freyja HomePod Shortcut path ==="
echo "Shortcut phrase: Hey Siri, Tell Freyja"
echo "Transport: HomePod/Siri -> iPhone Shortcut -> iMessage -> Freyja iMessage connector -> Director /route"
echo ""

if [[ ! -x "${STATUS_SCRIPT}" ]]; then
    echo "UNSAFE: missing ${STATUS_SCRIPT}" >&2
    exit 1
fi

"${STATUS_SCRIPT}" | sed 's/^/  /'

echo ""
echo "=== Runtime configuration ==="
if [[ ! -f "${RUNTIME_ENV}" ]]; then
    echo "UNSAFE: missing runtime .env at ${RUNTIME_ENV}" >&2
    exit 1
fi

required_keys=(
    IMESSAGE_ENABLED
    IMESSAGE_ALLOWED_SENDERS
    FREYJA_DIRECTOR_URL
    FREYJA_CONNECTOR_TOKEN
)

for key in "${required_keys[@]}"; do
    value="$(grep -E "^${key}=" "${RUNTIME_ENV}" | tail -n 1 | cut -d= -f2- || true)"
    if [[ -z "${value}" ]]; then
        echo "UNSAFE: ${key} is not configured in runtime .env" >&2
        exit 1
    fi
    lowered_value="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${key}" == "IMESSAGE_ENABLED" && "${lowered_value}" != "true" ]]; then
        echo "UNSAFE: IMESSAGE_ENABLED is ${value}, expected true" >&2
        exit 1
    fi
    echo "  ${key}: configured"
done

echo ""
echo "HomePod Shortcut path is configured on the Freyja side."
