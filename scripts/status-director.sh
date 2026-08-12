#!/bin/bash
set -euo pipefail

# Show the current state of the Freyja Director LaunchAgent and health.

PLIST_NAME="com.freyja-os.director.plist"
PROJECT_DIR="/Users/freyja/freyja-os"
LOG_FILE="${PROJECT_DIR}/logs/director.log"
ENV_FILE="${PROJECT_DIR}/.env"
CONNECTOR_TOKEN=""
HEALTH_OUTPUT=$(mktemp -t freyja-director-health.XXXXXX)
STATUS_OUTPUT=$(mktemp -t freyja-control-plane-status.XXXXXX)
trap 'rm -f "${HEALTH_OUTPUT}" "${STATUS_OUTPUT}"' EXIT

if [[ -f "${ENV_FILE}" ]]; then
    CONNECTOR_TOKEN=$(
        awk -F= '
            $1 == "FREYJA_CONNECTOR_TOKEN" {
                value = substr($0, index($0, "=") + 1)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                gsub(/^"|"$/, "", value)
                gsub(/^'\''|'\''$/, "", value)
                print value
                exit
            }
        ' "${ENV_FILE}"
    )
fi

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
HEALTH_BODY=""
HEALTH_CODE=$(curl -s --max-time 3 -w "%{http_code}" -o "${HEALTH_OUTPUT}" \
    http://127.0.0.1:8000/health 2>/dev/null || true)
if [[ -s "${HEALTH_OUTPUT}" ]]; then
    HEALTH_BODY=$(cat "${HEALTH_OUTPUT}")
fi
if [[ "${HEALTH_CODE}" == "200" ]]; then
    echo "${HEALTH_BODY}"
    echo "Director is reachable."
else
    echo "${HEALTH_BODY}"
    echo "Director is not healthy on 127.0.0.1:8000 (HTTP ${HEALTH_CODE:-unreachable})."
fi

echo ""
echo "=== Control plane status (http://127.0.0.1:8000/control-plane/status) ==="
STATUS_BODY=""
if [[ -n "${CONNECTOR_TOKEN}" ]]; then
    STATUS_CODE=$(curl -s --max-time 3 -w "%{http_code}" -o "${STATUS_OUTPUT}" \
        -H "Authorization: Bearer ${CONNECTOR_TOKEN}" \
        http://127.0.0.1:8000/control-plane/status 2>/dev/null || true)
    if [[ -s "${STATUS_OUTPUT}" ]]; then
        STATUS_BODY=$(cat "${STATUS_OUTPUT}")
    fi
    if [[ "${STATUS_CODE}" == "200" ]]; then
        echo "${STATUS_BODY}"
        echo "Control plane status is reachable with connector auth."
    else
        echo "${STATUS_BODY}"
        echo "Control plane status is not healthy with connector auth (HTTP ${STATUS_CODE:-unreachable})."
    fi
else
    STATUS_CODE=$(curl -s --max-time 3 -w "%{http_code}" -o "${STATUS_OUTPUT}" \
        http://127.0.0.1:8000/control-plane/status 2>/dev/null || true)
    if [[ -s "${STATUS_OUTPUT}" ]]; then
        STATUS_BODY=$(cat "${STATUS_OUTPUT}")
    fi
    if [[ "${STATUS_CODE}" == "200" ]]; then
        echo "${STATUS_BODY}"
        echo "Control plane status is reachable without connector auth."
    else
        echo "${STATUS_BODY}"
        echo "Control plane status is not healthy on 127.0.0.1:8000 (HTTP ${STATUS_CODE:-unreachable})."
    fi
fi

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 20 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi
