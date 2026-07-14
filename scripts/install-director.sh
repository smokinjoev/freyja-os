#!/bin/bash
set -euo pipefail

# Install Freyja Director as a user LaunchAgent on macOS.
# Must be run as the freyja user (not root).

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_NAME="com.freyja-os.director.plist"
LABEL="${PLIST_NAME%.plist}"
PLIST_SRC="${PROJECT_DIR}/scripts/${PLIST_NAME}"
PLIST_DST="${AGENTS_DIR}/${PLIST_NAME}"
LOG_DIR="${PROJECT_DIR}/logs"
SERVICE_DOMAIN="gui/$(id -u freyja)"
SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "Error: project directory not found: ${PROJECT_DIR}" >&2
    exit 1
fi

if [[ ! -f "${PROJECT_DIR}/.venv/bin/uvicorn" ]]; then
    echo "Error: virtual environment uvicorn not found at ${PROJECT_DIR}/.venv/bin/uvicorn" >&2
    exit 1
fi

mkdir -p "${LOG_DIR}" "${AGENTS_DIR}"

# Remove any previously loaded instance.
launchctl bootout "${SERVICE_TARGET}" 2>/dev/null || true
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

cp "${PLIST_SRC}" "${PLIST_DST}"
chmod 644 "${PLIST_DST}"

# Validate plist syntax.
plutil -lint "${PLIST_DST}" >/dev/null

# Bootstrap the LaunchAgent.
launchctl bootstrap "${SERVICE_DOMAIN}" "${PLIST_DST}"
sleep 2

# Verify it loaded and started.
if ! launchctl list "${LABEL}" >/dev/null 2>&1; then
    echo "Error: LaunchAgent ${PLIST_NAME} did not load." >&2
    exit 1
fi

if ! curl -s --max-time 3 "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo "Warning: LaunchAgent loaded but Director health check is not yet reachable." >&2
    echo "Check logs at ${LOG_DIR}/director.log" >&2
fi

echo "Freyja Director LaunchAgent installed and loaded."
echo "Plist: ${PLIST_DST}"
echo "Logs:  ${LOG_DIR}/director.log"
