#!/bin/bash
set -uo pipefail

# Verify Telegram travel mode safety without exposing secrets.
# Returns non-zero if the configuration is unsafe.

PROJECT_DIR="/Users/freyja/freyja-os"
ENV_FILE="${PROJECT_DIR}/.env"
STATE_DIR="${HOME}/.local/state/freyja/telegram"
HEARTBEAT_FILE="${STATE_DIR}/telegram-heartbeat.json"
PLIST_NAME="com.freyja-os.telegram-gateway.plist"
LABEL="${PLIST_NAME%.plist}"
UNSAFE=0

_env_value() {
    local key="$1"
    if [[ -f "${ENV_FILE}" ]]; then
        grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | cut -d '=' -f 2- || true
    fi
}

_bool() {
    local value="${1:-}"
    [[ "${value,,}" == "true" ]] || [[ "${value,,}" == "1" ]]
}

echo "=== Freyja Telegram travel-mode verification ==="
echo ""

echo "Director health:"
if curl -fsS --max-time 3 http://127.0.0.1:8000/health 2>/dev/null; then
    echo ""
else
    echo "unreachable"
    ((UNSAFE++))
fi

if [[ "$(id -un)" == "freyja" ]]; then
    SERVICE_DOMAIN="gui/$(id -u)"
else
    UID_VAL=$(id -u freyja 2>/dev/null || true)
    if [[ -n "${UID_VAL}" ]]; then
        SERVICE_DOMAIN="gui/${UID_VAL}"
    else
        SERVICE_DOMAIN=""
    fi
fi

echo ""
echo "Telegram gateway process state:"
if [[ -n "${SERVICE_DOMAIN}" ]] && launchctl list "${LABEL}" >/dev/null 2>&1; then
    echo "loaded"
else
    echo "not loaded"
fi

echo ""
echo "Bot token configured:"
if [[ -f "${ENV_FILE}" ]] && grep -qE "^TELEGRAM_BOT_TOKEN=[^[:space:]]+$" "${ENV_FILE}"; then
    echo "yes"
else
    echo "no"
fi

ALLOWED_USERS=$(_env_value TELEGRAM_ALLOWED_USER_IDS)
ALLOWED_COUNT=0
if [[ -n "${ALLOWED_USERS}" ]]; then
    ALLOWED_COUNT=$(echo "${ALLOWED_USERS}" | tr ',' '\n' | grep -cE '^[0-9]+$' || true)
fi
echo "Allowed-user count: ${ALLOWED_COUNT}"

DM_ONLY=$(_env_value TELEGRAM_DIRECT_MESSAGES_ONLY)
echo "Direct-messages-only: ${DM_ONLY:-not set}"

SMITH_ENABLED=$(_env_value AGENT_SMITH_ENABLED)
SMITH_READ_ONLY=$(_env_value AGENT_SMITH_READ_ONLY_ENABLED)
SMITH_WRITE=$(_env_value AGENT_SMITH_WRITE_PILOT_ENABLED)
CONTROLLED_ENABLED=$(_env_value AGENT_SMITH_CONTROLLED_TOOLS_ENABLED)

echo "Agent Smith enabled: ${SMITH_ENABLED:-false}"
echo "Smith read-only enabled: ${SMITH_READ_ONLY:-false}"
echo "Smith write enabled: ${SMITH_WRITE:-false}"
echo "Controlled-write tools enabled: ${CONTROLLED_ENABLED:-false}"

echo ""
echo "Ollama health:"
OLLAMA_URL=$(_env_value OLLAMA_BASE_URL)
if [[ -n "${OLLAMA_URL}" ]]; then
    if curl -fsS --max-time 3 "${OLLAMA_URL}" >/dev/null 2>&1; then
        echo "healthy"
    else
        echo "unhealthy"
    fi
else
    echo "not configured"
fi

echo ""
echo "OpenRouter configured:"
if [[ -f "${ENV_FILE}" ]] && grep -qE "^OPENROUTER_API_KEY=[^[:space:]]+$" "${ENV_FILE}"; then
    echo "yes"
else
    echo "no"
fi

echo ""
echo "Latest gateway heartbeat:"
if [[ -f "${HEARTBEAT_FILE}" ]]; then
    stat -f "%Sm" "${HEARTBEAT_FILE}"
else
    echo "none"
fi

echo ""
echo "LaunchAgent status:"
if [[ -n "${SERVICE_DOMAIN}" ]] && launchctl print "${SERVICE_DOMAIN}/${LABEL}" >/dev/null 2>&1; then
    echo "loaded"
else
    echo "not loaded"
fi

echo ""
echo "=== Safety checks ==="

TELEGRAM_ENABLED=$(_env_value TELEGRAM_ENABLED)
if _bool "${TELEGRAM_ENABLED}"; then
    if [[ "${ALLOWED_COUNT}" -eq 0 ]]; then
        echo "UNSAFE: Telegram enabled without allowed user IDs."
        ((UNSAFE++))
    fi
    if ! _bool "${DM_ONLY}"; then
        echo "UNSAFE: Telegram enabled with groups permitted."
        ((UNSAFE++))
    fi
fi

if _bool "${SMITH_WRITE}"; then
    echo "UNSAFE: Agent Smith write pilot is enabled."
    ((UNSAFE++))
fi

if _bool "${CONTROLLED_ENABLED}"; then
    echo "UNSAFE: Arbitrary controlled-write tools are enabled."
    ((UNSAFE++))
fi

if ! curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "UNSAFE: Director is not healthy."
    ((UNSAFE++))
fi

if [[ "${UNSAFE}" -gt 0 ]]; then
    echo ""
    echo "Result: UNSAFE (${UNSAFE} issue(s))"
    exit 1
fi

echo ""
echo "Result: OK"
exit 0
