#!/bin/bash
set -euo pipefail

# Show the current state of Freyja's native iMessage connector LaunchAgent.

PROJECT_DIR="/Users/freyja/freyja-os-imessage-runtime"
CHECKOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.freyja-os.imessage-connector.plist"
LABEL="${PLIST_NAME%.plist}"
LOG_FILE="${PROJECT_DIR}/logs/imessage-connector.log"
FAIL_ON_DRIFT=0
MANIFEST_FILE="${CHECKOUT_DIR}/scripts/imessage-runtime-files.txt"

check_runtime_imports() {
    if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
        echo "  FAIL    runtime python missing or not executable: ${PROJECT_DIR}/.venv/bin/python"
        return 1
    fi
    if PYTHONPATH="${PROJECT_DIR}/src:${PROJECT_DIR}" "${PROJECT_DIR}/.venv/bin/python" - <<'PY'
import importlib

for module_name in ("freyja.router", "connectors.imessage.gateway"):
    importlib.import_module(module_name)
PY
    then
        echo "  OK      freyja.router and connectors.imessage.gateway import from runtime"
        return 0
    fi
    echo "  FAIL    runtime import check failed"
    return 1
}

usage() {
    cat <<EOF
Usage: scripts/status-imessage-connector.sh [--fail-on-drift]

Shows LaunchAgent status, monitored runtime source drift, and recent logs.

Options:
  --fail-on-drift   Exit nonzero if monitored runtime files differ from this checkout.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fail-on-drift)
            FAIL_ON_DRIFT=1
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

if UID_VAL="$(id -u freyja 2>/dev/null)"; then
    SERVICE_DOMAIN="gui/${UID_VAL}"
else
    echo "Error: freyja user not found" >&2
    exit 1
fi

SERVICE_TARGET="${SERVICE_DOMAIN}/${LABEL}"

if [[ ! -f "${MANIFEST_FILE}" ]]; then
    echo "Error: runtime manifest missing: ${MANIFEST_FILE}" >&2
    exit 1
fi
DRIFT_PATHS=()
while IFS= read -r REL_PATH || [[ -n "${REL_PATH}" ]]; do
    if [[ -z "${REL_PATH}" || "${REL_PATH}" =~ ^# ]]; then
        continue
    fi
    DRIFT_PATHS+=("${REL_PATH}")
done < "${MANIFEST_FILE}"

echo "=== Freyja iMessage connector status ==="
echo "LaunchAgent: ${PLIST_NAME}"
echo "Runtime: ${PROJECT_DIR}"
echo "Checkout: ${CHECKOUT_DIR}"
echo "Service target: ${SERVICE_TARGET}"

if SERVICE_INFO="$(launchctl print "${SERVICE_TARGET}" 2>/dev/null)"; then
    echo "State: loaded"
    echo "${SERVICE_INFO}" | sed 's/^/  /'
else
    echo "State: not loaded"
fi

echo ""
echo "=== Processes ==="
ps -axo pid,ppid,command 2>/dev/null | grep -E "[r]un-imessage-connector|[i]msg watch" || true

echo ""
echo "=== Runtime source drift ==="
DRIFT_COUNT=0
for REL_PATH in "${DRIFT_PATHS[@]}"; do
    CHECKOUT_FILE="${CHECKOUT_DIR}/${REL_PATH}"
    RUNTIME_FILE="${PROJECT_DIR}/${REL_PATH}"
    if [[ ! -f "${CHECKOUT_FILE}" ]]; then
        echo "  MISSING checkout ${REL_PATH}"
        DRIFT_COUNT=$((DRIFT_COUNT + 1))
    elif [[ ! -f "${RUNTIME_FILE}" ]]; then
        echo "  MISSING runtime  ${REL_PATH}"
        DRIFT_COUNT=$((DRIFT_COUNT + 1))
    elif cmp -s "${CHECKOUT_FILE}" "${RUNTIME_FILE}"; then
        echo "  OK      ${REL_PATH}"
    else
        CHECKOUT_SHA="$(shasum -a 256 "${CHECKOUT_FILE}" | awk '{print $1}')"
        RUNTIME_SHA="$(shasum -a 256 "${RUNTIME_FILE}" | awk '{print $1}')"
        echo "  DIFF    ${REL_PATH}"
        echo "          checkout ${CHECKOUT_SHA}"
        echo "          runtime  ${RUNTIME_SHA}"
        DRIFT_COUNT=$((DRIFT_COUNT + 1))
    fi
done

if [[ "${DRIFT_COUNT}" -gt 0 ]]; then
    echo ""
    echo "  WARNING: LaunchAgent runs ${PROJECT_DIR}, and it differs from ${CHECKOUT_DIR}."
    echo "  Run scripts/sync-imessage-runtime.sh before trusting live iMessage behavior."
else
    echo "  Runtime source matches this checkout for monitored files."
fi

echo ""
echo "=== Runtime import check ==="
IMPORT_OK=0
if check_runtime_imports; then
    IMPORT_OK=1
fi

echo ""
echo "=== Recent log lines ==="
if [[ -f "${LOG_FILE}" ]]; then
    tail -n 40 "${LOG_FILE}" | sed 's/^/  /'
else
    echo "  No log file yet at ${LOG_FILE}"
fi

if [[ "${FAIL_ON_DRIFT}" -eq 1 && ( "${DRIFT_COUNT}" -gt 0 || "${IMPORT_OK}" -ne 1 ) ]]; then
    exit 1
fi
