#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 ENV_FILE" >&2
  exit 64
fi

ENV_FILE="$1"
if [ ! -r "$ENV_FILE" ]; then
  echo "env file is not readable: $ENV_FILE" >&2
  exit 66
fi

set -a
. "$ENV_FILE"
set +a

exec /Users/freyja/freyja-os/.venv/bin/python /Users/freyja/freyja-os/scripts/run-discord-dm-connector.py
