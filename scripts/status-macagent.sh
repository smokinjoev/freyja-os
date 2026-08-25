#!/bin/bash
set -euo pipefail

# Show the current state of the Freyja MacAgent LaunchAgent and health.

PROJECT_DIR="/Users/freyja/freyja-os"
PLIST_NAME="com.freyja-os.macagent.plist"
LABEL="${PLIST_NAME%.plist}"
LOG_FILE="${PROJECT_DIR}/logs/macagent.log"
ENV_FILE="${PROJECT_DIR}/.env"

if UID_VAL="$(id -u freyja 2>/dev/null)"; then
    SERVICE_DOMAIN="gui/${UID_VAL}"
else
    echo "Error: freyja user not found" >&2
    exit 1
fi

SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

echo "=== Freyja MacAgent status ==="
echo "LaunchAgent: ${PLIST_NAME}"
echo "Runtime: ${PROJECT_DIR}"
echo "Service target: ${SERVICE_TARGET}"

if SERVICE_INFO="$(launchctl print "${SERVICE_TARGET}" 2>/dev/null)"; then
    echo "State: loaded"
    echo "${SERVICE_INFO}" | sed 's/^/  /'
else
    echo "State: not loaded"
fi

echo ""
echo "=== Authenticated health check ==="
MACAGENT_HOST_VALUE="${MACAGENT_HOST:-127.0.0.1}"
MACAGENT_PORT_VALUE="${MACAGENT_PORT:-8765}"
MACAGENT_TOKEN_VALUE="${MACAGENT_TOKEN:-}"

if [[ -f "${ENV_FILE}" ]]; then
    while IFS='=' read -r key value; do
        case "${key}" in
            MACAGENT_HOST)
                MACAGENT_HOST_VALUE="${value%\"}"
                MACAGENT_HOST_VALUE="${MACAGENT_HOST_VALUE#\"}"
                ;;
            MACAGENT_PORT)
                MACAGENT_PORT_VALUE="${value%\"}"
                MACAGENT_PORT_VALUE="${MACAGENT_PORT_VALUE#\"}"
                ;;
            MACAGENT_TOKEN)
                MACAGENT_TOKEN_VALUE="${value%\"}"
                MACAGENT_TOKEN_VALUE="${MACAGENT_TOKEN_VALUE#\"}"
                ;;
        esac
    done < <(grep -E '^(MACAGENT_HOST|MACAGENT_PORT|MACAGENT_TOKEN)=' "${ENV_FILE}" || true)
fi

if [[ -z "${MACAGENT_TOKEN_VALUE}" ]]; then
    echo "MacAgent token is not configured; authenticated health cannot be checked."
else
    if curl -s --fail --max-time 3 \
        -H "Authorization: Bearer ${MACAGENT_TOKEN_VALUE}" \
        "http://${MACAGENT_HOST_VALUE}:${MACAGENT_PORT_VALUE}/health"; then
        echo ""
        echo "MacAgent authenticated health: OK"
    else
        echo "MacAgent authenticated health: not reachable"
    fi
fi

echo ""
echo "=== Processes ==="
ps -axo pid,ppid,command | grep -E "[r]un-macagent|[f]reyja.macagent_app" || true

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 40 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi
