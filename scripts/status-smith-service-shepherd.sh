#!/usr/bin/env sh
set -eu

repo="${FREYJA_REPO:-/Users/freyja/freyja-os}"
label="com.freyja-os.smith-service-shepherd"
domain="gui/$(id -u)"
status_file="${SMITH_SHEPHERD_STATUS:-$HOME/.local/state/freyja/smith-service-shepherd-status.json}"

echo "LaunchAgent: $label"
if launchctl print "$domain/$label" >/tmp/smith-service-shepherd.launchctl 2>/dev/null; then
  grep -E '^[[:space:]]*(state|pid|last exit code) =' /tmp/smith-service-shepherd.launchctl || true
else
  echo "state = not loaded"
fi
rm -f /tmp/smith-service-shepherd.launchctl

echo
echo "Status: $status_file"
if [ -f "$status_file" ]; then
  python3 - "$status_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(f"time={payload.get('time')} host={payload.get('host')} dry_run={payload.get('dry_run')}")
routes = payload.get("routes") or {}
for name in ("primary", "openclaw_backdoor"):
    route = routes.get(name) or {}
    print(f"{name}: {route.get('base_url')} model={route.get('model')} available={route.get('available')}")
print(f"docker_action={(payload.get('docker') or {}).get('action')}")
for item in payload.get("compose") or []:
    print(f"compose_action={item.get('action')}")
PY
else
  echo "no status written yet"
fi

echo
echo "Log: $repo/logs/smith-service-shepherd.log"
if [ -f "$repo/logs/smith-service-shepherd.log" ]; then
  tail -n 5 "$repo/logs/smith-service-shepherd.log"
else
  echo "no log yet"
fi
