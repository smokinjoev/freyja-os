#!/bin/bash
set -euo pipefail

# Sync the checked-out Freyja iMessage runtime files into the LaunchAgent runtime
# checkout, then restart the native iMessage connector.

CHECKOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="/Users/freyja/freyja-os-imessage-runtime"
MANIFEST_FILE="${CHECKOUT_DIR}/scripts/imessage-runtime-files.txt"
DRY_RUN=0
RESTART=1
BACKUP_DIR=""
SYNC_COMMITTED=0

check_runtime_imports() {
    if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
        echo "Error: runtime python missing or not executable: ${PROJECT_DIR}/.venv/bin/python" >&2
        return 1
    fi
    PYTHONPATH="${PROJECT_DIR}/src:${PROJECT_DIR}" "${PROJECT_DIR}/.venv/bin/python" - <<'PY'
import importlib

for module_name in ("freyja.router", "connectors.imessage.gateway"):
    importlib.import_module(module_name)
PY
}

restore_runtime_backup() {
    if [[ -z "${BACKUP_DIR}" || ! -d "${BACKUP_DIR}" || "${SYNC_COMMITTED}" -eq 1 ]]; then
        return 0
    fi
    echo "Restoring previous iMessage runtime files after failed sync" >&2
    for REL_PATH in "${SYNC_PATHS[@]}"; do
        DST="${PROJECT_DIR}/${REL_PATH}"
        BACKUP_FILE="${BACKUP_DIR}/files/${REL_PATH}"
        MISSING_MARKER="${BACKUP_DIR}/missing/${REL_PATH}"
        if [[ -f "${BACKUP_FILE}" ]]; then
            mkdir -p "$(dirname "${DST}")"
            cp -p "${BACKUP_FILE}" "${DST}"
        elif [[ -f "${MISSING_MARKER}" ]]; then
            rm -f "${DST}"
        fi
    done
}

backup_runtime_file() {
    REL_PATH="$1"
    DST="${PROJECT_DIR}/${REL_PATH}"
    if [[ -f "${DST}" ]]; then
        mkdir -p "${BACKUP_DIR}/files/$(dirname "${REL_PATH}")"
        cp -p "${DST}" "${BACKUP_DIR}/files/${REL_PATH}"
    else
        mkdir -p "${BACKUP_DIR}/missing/$(dirname "${REL_PATH}")"
        : > "${BACKUP_DIR}/missing/${REL_PATH}"
    fi
}

usage() {
    cat <<EOF
Usage: scripts/sync-imessage-runtime.sh [--dry-run] [--no-restart]

Copies the iMessage runtime-critical files from:
  ${CHECKOUT_DIR}
to:
  ${PROJECT_DIR}

Then runs ${PROJECT_DIR}/scripts/install-imessage-connector.sh unless --no-restart is set.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --no-restart)
            RESTART=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    exit 1
fi

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "Error: runtime directory not found: ${PROJECT_DIR}" >&2
    exit 1
fi

if [[ ! -x "${PROJECT_DIR}/scripts/install-imessage-connector.sh" ]]; then
    echo "Error: runtime install script is missing or not executable: ${PROJECT_DIR}/scripts/install-imessage-connector.sh" >&2
    exit 1
fi

if [[ ! -f "${MANIFEST_FILE}" ]]; then
    echo "Error: runtime manifest missing: ${MANIFEST_FILE}" >&2
    exit 1
fi
SYNC_PATHS=()
while IFS= read -r REL_PATH || [[ -n "${REL_PATH}" ]]; do
    if [[ -z "${REL_PATH}" || "${REL_PATH}" =~ ^# ]]; then
        continue
    fi
    SYNC_PATHS+=("${REL_PATH}")
done < "${MANIFEST_FILE}"

RSYNC_FLAGS=(-a)
if [[ "${DRY_RUN}" -eq 1 ]]; then
    RSYNC_FLAGS+=(--dry-run --itemize-changes)
fi

echo "Syncing iMessage runtime files"
echo "Checkout: ${CHECKOUT_DIR}"
echo "Runtime:  ${PROJECT_DIR}"

if [[ "${DRY_RUN}" -ne 1 ]]; then
    BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/freyja-imessage-runtime-backup.XXXXXX")"
    trap 'restore_runtime_backup' ERR
fi

for REL_PATH in "${SYNC_PATHS[@]}"; do
    SRC="${CHECKOUT_DIR}/${REL_PATH}"
    DST="${PROJECT_DIR}/${REL_PATH}"
    if [[ ! -f "${SRC}" ]]; then
        echo "Error: checkout file missing: ${SRC}" >&2
        exit 1
    fi

    if [[ "${DRY_RUN}" -ne 1 ]]; then
        backup_runtime_file "${REL_PATH}"
    fi
    mkdir -p "$(dirname "${DST}")"
    rsync "${RSYNC_FLAGS[@]}" "${SRC}" "${DST}"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        echo "  would sync ${REL_PATH}"
    else
        echo "  synced ${REL_PATH}"
    fi
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "Dry run complete; runtime was not modified."
    exit 0
fi

echo "Verifying runtime imports"
if ! check_runtime_imports; then
    restore_runtime_backup
    rm -rf "${BACKUP_DIR}"
    exit 1
fi
echo "  runtime imports ok"
SYNC_COMMITTED=1
rm -rf "${BACKUP_DIR}"

if [[ "${RESTART}" -eq 1 ]]; then
    "${PROJECT_DIR}/scripts/install-imessage-connector.sh"
else
    echo "Skipped LaunchAgent restart because --no-restart was set."
fi

"${CHECKOUT_DIR}/scripts/status-imessage-connector.sh" --fail-on-drift
