#!/bin/bash
set -euo pipefail

# Remove the Freyja MacAgent LaunchAgent.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    exit 1
fi

PLIST_NAME="com.freyja-os.macagent.plist"
LABEL="${PLIST_NAME%.plist}"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
SERVICE_TARGET="gui/$(id -u)/${LABEL}"

launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
sleep 1

if [[ -f "${PLIST_DST}" ]]; then
    rm "${PLIST_DST}"
    echo "Removed ${PLIST_DST}"
else
    echo "Plist already removed: ${PLIST_DST}"
fi

echo "Freyja MacAgent LaunchAgent removed."
