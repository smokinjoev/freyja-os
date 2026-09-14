#!/usr/bin/env sh
set -eu

container="${1:-freyja-open-webui-atlas-open-webui-1}"
script="/app/backend/data/cloyd_smith_loop_daemon.py"
pidfile="/app/backend/data/cloyd-smith-loop-daemon.pid"
logfile="/app/backend/data/cloyd-smith-loop-daemon.log"

docker exec "$container" sh -lc "if [ -f '$pidfile' ]; then old=\$(cat '$pidfile' 2>/dev/null || true); if [ -n \"\$old\" ]; then kill \"\$old\" 2>/dev/null || true; fi; fi"
docker cp "$(dirname "$0")/cloyd_smith_loop_daemon.py" "$container:$script"
docker exec -d "$container" sh -lc "nohup python '$script' --interval 15 >> '$logfile' 2>&1 & echo \$! > '$pidfile'"
docker exec "$container" sh -lc "cat '$pidfile'"
