#!/bin/bash
set -euo pipefail

# Disable all Agent Smith modes without modifying unrelated configuration.
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

# Preserve backup with timestamp outside the repository; never print contents.
BACKUP_FILE="${BACKUP_DIR}/env.agent-smith-disabled-$(date +%Y%m%d-%H%M%S).bak"
cp -p "${ENV_FILE}" "${BACKUP_FILE}"
chmod 0600 "${BACKUP_FILE}"
echo "Backup created: ${BACKUP_FILE}"

# Disable all Smith modes; do not touch write tool enablement keys if present.
set_env_var() {
    local key="$1"
    local value="$2"
    if grep -qE "^\s*${key}\s*=" "${ENV_FILE}"; then
        sed -i.bak "s/^\s*${key}\s*=.*/${key}=${value}/" "${ENV_FILE}"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

set_env_var "AGENT_SMITH_ENABLED" "false"
set_env_var "AGENT_SMITH_READ_ONLY_ENABLED" "false"
set_env_var "AGENT_SMITH_DRY_RUN_ENABLED" "false"

rm -f "${ENV_FILE}.bak"

# Restrict access to the environment file immediately after modification.
chmod 0600 "${ENV_FILE}"

# Validate configuration.
if grep -qE '^\s*AGENT_SMITH_(ENABLED|READ_ONLY_ENABLED|DRY_RUN_ENABLED)\s*=\s*(true|1|yes)' "${ENV_FILE}"; then
    echo "Error: a Smith mode is still enabled after disable." >&2
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
    -d '{"objective": "show repository status"}')
DRY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/dry-run \
    -H "Content-Type: application/json" \
    -d '{"objective": "show repository status"}')
if [[ "${RO_STATUS}" != "404" || "${DRY_STATUS}" != "404" ]]; then
    echo "Error: Smith endpoints should return 404 when disabled (read-only=${RO_STATUS}, dry-run=${DRY_STATUS})." >&2
    exit 1
fi

echo "Agent Smith disabled. Health check: OK; read-only=${RO_STATUS}, dry-run=${DRY_STATUS}"
exit 0
