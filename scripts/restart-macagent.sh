#!/bin/bash
set -euo pipefail

# Restart the Freyja MacAgent LaunchAgent.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    exit 1
fi

PLIST_NAME="com.freyja-os.macagent.plist"
LABEL="${PLIST_NAME%.plist}"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
SERVICE_TARGET="gui/$(id -u)/${LABEL}"

if [[ ! -f "${PLIST_DST}" ]]; then
    echo "Error: LaunchAgent plist not installed at ${PLIST_DST}" >&2
    echo "Run scripts/install-macagent.sh first." >&2
    exit 1
fi

launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "${PLIST_DST}"
sleep 2
launchctl kickstart -k "${SERVICE_TARGET}" >/dev/null 2>&1 || true

echo "Freyja MacAgent restarted."
