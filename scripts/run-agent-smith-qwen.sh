#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/Users/freyja/.local/npm/bin:/Users/freyja/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export TERM="${TERM:-xterm-256color}"

export QWEN_HOME="${FREYJA_GATEWAY_REMOTE_QWEN_HOME:-$HOME/.local/state/freyja/gateway-remote/qwen-smith}"
export OPENAI_BASE_URL="${FREYJA_GATEWAY_REMOTE_VULCAN_MODEL_BASE_URL:-http://100.94.80.21:3939/v1}"
export FREYJA_GATEWAY_REMOTE_VULCAN_MODEL="${FREYJA_GATEWAY_REMOTE_VULCAN_MODEL:-@preset/freyja-coder}"

TOKEN_FILE="${FREYJA_GATEWAY_REMOTE_NEXUS_TOKEN_FILE:-$HOME/.local/state/freyja/gateway-remote/msty-nexus-token}"
QWEN_BIN="${FREYJA_GATEWAY_REMOTE_QWEN_BIN:-/opt/homebrew/bin/qwen}"
TMUX_BIN="${AGENT_SMITH_TMUX_BIN:-/opt/homebrew/bin/tmux}"
TMUX_SESSION="${AGENT_SMITH_TMUX_SESSION:-agent-smith}"
WORKDIR="${AGENT_SMITH_WORKDIR:-$HOME}"

unset OPENROUTER_API_KEY
unset ANTHROPIC_API_KEY
unset GEMINI_API_KEY
unset GOOGLE_API_KEY
unset DASHSCOPE_API_KEY

mkdir -p "$QWEN_HOME"

python3 - "$QWEN_HOME/settings.json" "$OPENAI_BASE_URL" "$FREYJA_GATEWAY_REMOTE_VULCAN_MODEL" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
base_url = sys.argv[2]
model = sys.argv[3]
settings = {
    "$version": 4,
    "general": {
        "enableAutoUpdate": False,
    },
    "model": {
        "name": model,
        "baseUrl": base_url,
    },
    "modelProviders": {
        "openai": [
            {
                "id": model,
                "name": "Vulcan Nexus",
                "baseUrl": base_url,
                "envKey": "OPENAI_API_KEY",
                "generationConfig": {
                    "contextWindowSize": 128000,
                },
                "models": [model],
            }
        ]
    },
    "security": {
        "auth": {
            "baseUrl": base_url,
            "selectedType": "openai",
        }
    },
    "ui": {
        "autoModeAcknowledged": True,
    },
}
settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
PY

if [[ -r "$TOKEN_FILE" ]]; then
  export OPENAI_API_KEY="$(tr -d '\r\n' < "$TOKEN_FILE")"
else
  echo "Agent Smith: missing Nexus bearer token at $TOKEN_FILE"
  echo "Create or sync that file, then restart Agent Smith."
  exit 78
fi

if [[ ! -x "$QWEN_BIN" ]]; then
  echo "Agent Smith: qwen executable not found at $QWEN_BIN"
  exit 78
fi

if [[ ! -x "$TMUX_BIN" ]]; then
  echo "Agent Smith: tmux executable not found at $TMUX_BIN"
  exit 78
fi

if [[ ! -d "$WORKDIR" ]]; then
  echo "Agent Smith: working directory not found at $WORKDIR"
  exit 78
fi

QWEN_COMMAND="$(printf "%q " "$QWEN_BIN" --model "$FREYJA_GATEWAY_REMOTE_VULCAN_MODEL")"
exec "$TMUX_BIN" new-session -A -s "$TMUX_SESSION" -c "$WORKDIR" "$QWEN_COMMAND"
