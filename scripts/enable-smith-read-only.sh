#!/bin/bash
set -euo pipefail

# Enable Agent Smith read-only mode without allowing write tools.
# Only toggles approved Agent Smith configuration flags and restarts the Director.
# Must be run as the freyja user.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" >&2
    exit 1
fi

PROJECT_DIR="/Users/freyja/freyja-os"
ENV_FILE="${PROJECT_DIR}/.env"
RESTART_SCRIPT="${PROJECT_DIR}/scripts/restart-director.sh"
BACKUP_DIR="/Users/freyja/.local/state/freyja/backups"

mkdir -p "${BACKUP_DIR}"
chmod 0700 "${BACKUP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: environment file not found at ${ENV_FILE}" >&2
    exit 1
fi

if [[ ! -x "${RESTART_SCRIPT}" ]]; then
    echo "Error: restart script not found or not executable at ${RESTART_SCRIPT}" >&2
    exit 1
fi

# Verify no write-enable flags are present before touching config.
if grep -qE '^\s*AGENT_SMITH_WRITE_ENABLED\s*=\s*(true|1|yes)' "${ENV_FILE}" 2>/dev/null; then
    echo "Error: refusing to enable read-only mode while write mode is enabled." >&2
    exit 1
fi

# Preserve backup with timestamp outside the repository; never print contents.
BACKUP_FILE="${BACKUP_DIR}/env.agent-smith-read-only-$(date +%Y%m%d-%H%M%S).bak"
cp -p "${ENV_FILE}" "${BACKUP_FILE}"
chmod 0600 "${BACKUP_FILE}"
echo "Backup created: ${BACKUP_FILE}"

# Update only approved Smith flags; never enable write tools or package installation.
set_env_var() {
    local key="$1"
    local value="$2"
    if grep -qE "^\s*${key}\s*=" "${ENV_FILE}"; then
        sed -i.bak "s/^\s*${key}\s*=.*/${key}=${value}/" "${ENV_FILE}"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

set_env_var "AGENT_SMITH_ENABLED" "true"
set_env_var "AGENT_SMITH_READ_ONLY_ENABLED" "true"

# Ensure dry-run and write tools remain disabled.
set_env_var "AGENT_SMITH_DRY_RUN_ENABLED" "false"
if grep -qE '^\s*AGENT_SMITH_WRITE_ENABLED\s*=' "${ENV_FILE}"; then
    set_env_var "AGENT_SMITH_WRITE_ENABLED" "false"
fi

rm -f "${ENV_FILE}.bak"

# Restrict access to the environment file immediately after modification.
chmod 0600 "${ENV_FILE}"

# Validate configuration: only allowed flags are touched.
if ! grep -qE '^\s*AGENT_SMITH_ENABLED\s*=\s*true' "${ENV_FILE}"; then
    echo "Error: failed to enable AGENT_SMITH_ENABLED." >&2
    exit 1
fi
if ! grep -qE '^\s*AGENT_SMITH_READ_ONLY_ENABLED\s*=\s*true' "${ENV_FILE}"; then
    echo "Error: failed to enable AGENT_SMITH_READ_ONLY_ENABLED." >&2
    exit 1
fi

# Ensure controlled-write mode was not enabled.
if grep -qE '^\s*AGENT_SMITH_WRITE_ENABLED\s*=\s*(true|1|yes)' "${ENV_FILE}" 2>/dev/null; then
    echo "Error: write mode is enabled after read-only enable; refusing to continue." >&2
    exit 1
fi

# Restart Director using the existing, reviewed script.
echo "Restarting Freyja Director..."
"${RESTART_SCRIPT}"

# Verify endpoints after the Director comes back.
for i in $(seq 1 30); do
    if curl -s --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -s --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "Error: Director /health did not become reachable after restart." >&2
    exit 1
fi

RO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/read-only \
    -H "Content-Type: application/json" \
    -d '{"objective": "show repository status", "actor": "operator", "request_id": "verify-ro"}')
if [[ "${RO_STATUS}" != "200" ]]; then
    echo "Error: read-only endpoint did not return 200 (got ${RO_STATUS})." >&2
    exit 1
fi

DRY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/dry-run \
    -H "Content-Type: application/json" \
    -d '{"objective": "show repository status"}')
if [[ "${DRY_STATUS}" != "403" ]]; then
    echo "Error: dry-run endpoint should be disabled (403); got ${DRY_STATUS}." >&2
    exit 1
fi

echo "Agent Smith read-only mode enabled. Health check: OK; read-only=${RO_STATUS}, dry-run=${DRY_STATUS}"
exit 0
