#!/bin/bash
set -euo pipefail

# Show the current state of the Freyja Director LaunchAgent and health.

PLIST_NAME="com.freyja-os.director.plist"
PROJECT_DIR="/Users/freyja/freyja-os"
LOG_FILE="${PROJECT_DIR}/logs/director.log"
ENV_FILE="${PROJECT_DIR}/.env"
FREYJA_CONNECTOR_TOKEN_VALUE="${FREYJA_CONNECTOR_TOKEN:-}"

if [[ "$(id -un)" == "freyja" ]]; then
    UID_VAL=$(id -u)
    SERVICE_DOMAIN="gui/${UID_VAL}"
else
    UID_VAL=$(id -u freyja 2>/dev/null || true)
    if [[ -z "${UID_VAL}" ]]; then
        echo "Error: freyja user not found" >&2
        exit 1
    fi
    SERVICE_DOMAIN="gui/${UID_VAL}"
fi

echo "=== Freyja Director status ==="
echo "LaunchAgent: ${PLIST_NAME}"
echo "Service domain: ${SERVICE_DOMAIN}"

LABEL="${PLIST_NAME%.plist}"
# launchctl list from root cannot see gui-domain services; print can.
if SERVICE_INFO=$(launchctl print "${SERVICE_DOMAIN}/${LABEL}" 2>/dev/null); then
    echo "State: loaded"
    echo "${SERVICE_INFO}" | sed 's/^/  /'
else
    echo "State: not loaded"
fi

echo ""
echo "=== Health check (http://127.0.0.1:8000/health) ==="
if curl -s --max-time 3 http://127.0.0.1:8000/health 2>/dev/null; then
    echo ""
    echo "Director is reachable."
else
    echo "Director is not reachable on 127.0.0.1:8000."
fi

if [[ -z "${FREYJA_CONNECTOR_TOKEN_VALUE}" && -f "${ENV_FILE}" ]]; then
    while IFS='=' read -r key value; do
        case "${key}" in
            FREYJA_CONNECTOR_TOKEN)
                FREYJA_CONNECTOR_TOKEN_VALUE="${value%\"}"
                FREYJA_CONNECTOR_TOKEN_VALUE="${FREYJA_CONNECTOR_TOKEN_VALUE#\"}"
                ;;
        esac
    done < <(grep -E '^FREYJA_CONNECTOR_TOKEN=' "${ENV_FILE}" || true)
fi

echo ""
echo "=== Rev 2 protected health checks ==="
if [[ -z "${FREYJA_CONNECTOR_TOKEN_VALUE}" ]]; then
    echo "FREYJA_CONNECTOR_TOKEN is not configured; skipping protected health checks."
else
    for path in /providers/health /iris-router/health /macagent/health; do
        if curl -s --fail --max-time 5 \
            -H "Authorization: Bearer ${FREYJA_CONNECTOR_TOKEN_VALUE}" \
            "http://127.0.0.1:8000${path}" >/dev/null; then
            echo "${path}: OK"
        else
            echo "${path}: FAILED"
        fi
    done
fi

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 20 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi
