#!/usr/bin/env sh
set -eu

COMPOSE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="$COMPOSE_DIR/.env"
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"

catalog='
qwen2.5:32b-instruct
qwen2.5vl:72b
qwen3:30b-a3b
qwen3-coder-next:q4_K_M
gpt-oss:20b
gpt-oss-freyja:20b-analysis-prefill
gpt-oss:120b
'

usage() {
  cat <<EOF
Usage: $0 <model-id>

Approved model IDs:
$catalog
Policy: Open WebUI may pick from the approved catalog; Vulcan should keep only
one model resident at a time.
EOF
}

model="${1:-}"
if [ -z "$model" ]; then
  usage
  exit 2
fi

if ! printf '%s\n' "$catalog" | grep -Fxq "$model"; then
  echo "Refusing unknown model: $model" >&2
  usage >&2
  exit 2
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE; copy .env.example first." >&2
  exit 1
fi

set_env() {
  key="$1"
  value="$2"
  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$value|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env DEFAULT_MODELS "$model"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

echo
echo "Default Open WebUI model:"
grep -E '^DEFAULT_MODELS=' "$ENV_FILE"

echo
echo "Vulcan resident models:"
curl -fsS "${VULCAN_PS_URL:-http://100.94.80.21:8088/api/ps}" || true
echo
