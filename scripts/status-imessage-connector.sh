#!/bin/bash
set -euo pipefail

# Show the current state of Freyja's native iMessage connector LaunchAgent.

PROJECT_DIR="/Users/freyja/freyja-os-imessage-runtime"
PLIST_NAME="com.freyja-os.imessage-connector.plist"
LABEL="${PLIST_NAME%.plist}"
LOG_FILE="${PROJECT_DIR}/logs/imessage-connector.log"

if UID_VAL="$(id -u freyja 2>/dev/null)"; then
    SERVICE_DOMAIN="gui/${UID_VAL}"
else
    echo "Error: freyja user not found" >&2
    exit 1
fi

SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

echo "=== Freyja iMessage connector status ==="
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
ps -axo pid,ppid,command | grep -E "[r]un-imessage-connector|[i]msg watch" || true

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 40 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi
