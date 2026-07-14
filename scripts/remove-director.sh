#!/bin/bash
set -euo pipefail

# Remove the Freyja Director LaunchAgent and its plist.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

PLIST_NAME="com.freyja-os.director.plist"
LABEL="${PLIST_NAME%.plist}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"

SERVICE_DOMAIN="gui/$(id -u freyja)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

echo "Stopping and removing ${PLIST_NAME}..."
launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
sleep 1

if [[ -f "${PLIST_DST}" ]]; then
    rm "${PLIST_DST}"
    echo "Removed ${PLIST_DST}"
else
    echo "Plist already removed: ${PLIST_DST}"
fi

echo "Freyja Director LaunchAgent removed."
