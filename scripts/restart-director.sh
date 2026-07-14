#!/bin/bash
set -euo pipefail

# Restart the Freyja Director LaunchAgent.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

PLIST_NAME="com.freyja-os.director.plist"
LABEL="${PLIST_NAME%.plist}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"
PROJECT_DIR="/Users/freyja/freyja-os"

if [[ ! -f "${PLIST_DST}" ]]; then
    echo "Error: LaunchAgent plist not installed at ${PLIST_DST}" >&2
    echo "Run scripts/install-director.sh first." >&2
    exit 1
fi

SERVICE_DOMAIN="gui/$(id -u freyja)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

echo "Unloading ${PLIST_NAME}..."
launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true

# Wait for the service to actually disappear from launchctl.
for _ in $(seq 1 60); do
    if ! launchctl list "${LABEL}" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if launchctl list "${LABEL}" >/dev/null 2>&1; then
    echo "Warning: previous service instance still present; attempting kickstart -k..." >&2
    launchctl kickstart -k "${SERVICE_TARGET}" || true
    sleep 1
fi
sleep 1

echo "Loading ${PLIST_NAME}..."
launchctl bootstrap "${SERVICE_DOMAIN}" "${PLIST_DST}"
sleep 2

if launchctl list "${LABEL}" >/dev/null 2>&1; then
    echo "Freyja Director restarted."
    if curl -s --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "Health check: OK"
    else
        echo "Health check: not yet reachable. Check ${PROJECT_DIR}/logs/director.log"
    fi
else
    echo "Error: LaunchAgent did not reload." >&2
    exit 1
fi
