#!/bin/bash
set -euo pipefail

# Enable Agent Smith write-pilot test mode for a single controlled local pilot.
# Only the minimum required flags are toggled; all other controlled-write
# features remain disabled. A backup is created outside the repository before
# editing .env, and the exact rollback command is printed.
# Must be run as the freyja user.

if [[ "$(id -un)" != "freyja" ]]; then
    echo "Error: this script must be run as the freyja user." >&2
    echo "Run: su - freyja -c '$(realpath "$0")'" &
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
BACKUP_FILE="${BACKUP_DIR}/env.agent-smith-write-pilot-$(date +%Y%m%d-%H%M%S).bak"
cp -p "${ENV_FILE}" "${BACKUP_FILE}"
chmod 0600 "${BACKUP_FILE}"
echo "Backup created: ${BACKUP_FILE}"

set_env_var() {
    local key="$1"
    local value="$2"
    if grep -qE "^\s*${key}\s*=" "${ENV_FILE}"; then
        sed -i.bak "s/^\s*${key}\s*=.*/${key}=${value}/" "${ENV_FILE}"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

# Enable only the minimum required Smith modes.
set_env_var "AGENT_SMITH_ENABLED" "true"
set_env_var "AGENT_SMITH_WRITE_PILOT_ENABLED" "true"

# Keep all other controlled modes disabled.
set_env_var "AGENT_SMITH_READ_ONLY_ENABLED" "false"
set_env_var "AGENT_SMITH_DRY_RUN_ENABLED" "false"

rm -f "${ENV_FILE}.bak"

# Restrict access to the environment file immediately after modification.
chmod 0600 "${ENV_FILE}"

# Verify file mode.
ENV_MODE=$(stat -f '%Lp' "${ENV_FILE}" 2>/dev/null || stat -c '%a' "${ENV_FILE}" 2>/dev/null || true)
if [[ "${ENV_MODE}" != "600" ]]; then
    echo "Error: .env mode is ${ENV_MODE}, expected 600." >&2
    exit 1
fi

# Validate configuration.
if ! grep -qE '^\s*AGENT_SMITH_ENABLED\s*=\s*true' "${ENV_FILE}"; then
    echo "Error: failed to enable AGENT_SMITH_ENABLED." >&2
    exit 1
fi
if ! grep -qE '^\s*AGENT_SMITH_WRITE_PILOT_ENABLED\s*=\s*true' "${ENV_FILE}"; then
    echo "Error: failed to enable AGENT_SMITH_WRITE_PILOT_ENABLED." >&2
    exit 1
fi
for key in AGENT_SMITH_READ_ONLY_ENABLED AGENT_SMITH_DRY_RUN_ENABLED; do
    if grep -qE "^\s*${key}\s*=\s*(true|1|yes)" "${ENV_FILE}"; then
        echo "Error: ${key} must remain disabled for the write-pilot test." >&2
        exit 1
    fi
done

# Restart Director using the existing, reviewed script.
echo "Restarting Freyja Director..."
"${RESTART_SCRIPT}"

# Enable only the three approved write-pilot tools in the registry.
PYTHONPATH="${PROJECT_DIR}/src" "${PROJECT_DIR}/.venv/bin/python" -c "
import sys
sys.path.insert(0, '${PROJECT_DIR}/src')
import freyja.main  # Registers tools at import time
from freyja.tools.registry import get_registry
registry = get_registry()
for name in ('write_pilot_file_write', 'write_pilot_git_add', 'write_pilot_git_commit'):
    if registry.get_tool(name) is None:
        print(f'Error: write-pilot tool {name} is not registered.', file=sys.stderr)
        sys.exit(1)
    registry.set_enabled(name, True)
print('Write-pilot tools enabled in registry.')
"

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

# Verify the approval endpoints are loopback-only by confirming the setting.
if ! grep -qE '^\s*AGENT_SMITH_APPROVAL_LOOPBACK_ONLY\s*=\s*true' "${ENV_FILE}"; then
    echo "Warning: AGENT_SMITH_APPROVAL_LOOPBACK_ONLY is not explicitly true; leaving unchanged." >&2
fi

# Confirm write-pilot endpoint is reachable and read-only/dry-run remain disabled.
WP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/write-pilot \
    -H "Content-Type: application/json" \
    -d '{"objective": "operator test", "target_path": "docs/smith-pilot/operator-test.md", "proposed_content": "# test\n", "commit_message": "test", "request_id": "verify-wp-enabled"}' \
    || true)
RO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/read-only \
    -H "Content-Type: application/json" \
    -d '{"objective": "operator test"}' \
    || true)
DRY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST \
    http://127.0.0.1:8000/agents/smith/dry-run \
    -H "Content-Type: application/json" \
    -d '{"objective": "operator test"}' \
    || true)

if [[ "${WP_STATUS}" != "200" ]]; then
    echo "Error: write-pilot endpoint did not return 200 (got ${WP_STATUS})." >&2
    exit 1
fi
if [[ "${RO_STATUS}" != "403" && "${RO_STATUS}" != "404" ]]; then
    echo "Error: read-only endpoint should be disabled (403/404); got ${RO_STATUS}." >&2
    exit 1
fi
if [[ "${DRY_STATUS}" != "403" && "${DRY_STATUS}" != "404" ]]; then
    echo "Error: dry-run endpoint should be disabled (403/404); got ${DRY_STATUS}." >&2
    exit 1
fi

echo "Agent Smith write-pilot test mode enabled."
echo "Health check: OK"
echo "Write-pilot: ${WP_STATUS}, read-only: ${RO_STATUS}, dry-run: ${DRY_STATUS}"
echo ""
echo "Rollback command:"
echo "  ${PROJECT_DIR}/scripts/disable-smith-write-pilot-test.sh"
echo "Or restore backup:"
echo "  cp ${BACKUP_FILE} ${ENV_FILE}"
exit 0
