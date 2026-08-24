#!/bin/bash
set -euo pipefail

# Show the current state of Freyja's Gmail connector LaunchAgent.

PROJECT_DIR="/Users/freyja/freyja-os"
PLIST_NAME="com.freyja-os.gmail-connector.plist"
LABEL="${PLIST_NAME%.plist}"
LOG_FILE="${PROJECT_DIR}/logs/gmail-connector.log"

if UID_VAL="$(id -u freyja 2>/dev/null)"; then
    SERVICE_DOMAIN="gui/${UID_VAL}"
else
    echo "Error: freyja user not found" >&2
    exit 1
fi

SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

echo "=== Freyja Gmail connector status ==="
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
echo "=== Processes ==="
ps -axo pid,ppid,command | grep -E "[r]un-gmail-connector" || true

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 40 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi
