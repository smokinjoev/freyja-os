#!/usr/bin/env sh
set -eu

repo="${FREYJA_REPO:-/Users/freyja/freyja-os}"
label="com.freyja-os.cloyd-smith-loop"
domain="gui/$(id -u)"
python="$repo/.venv/bin/python"
verbose="${CLOYD_SMITH_STATUS_VERBOSE:-0}"

if [ "${1:-}" = "--verbose" ]; then
  verbose="1"
fi

if [ ! -x "$python" ]; then
  python="python3"
fi

echo "LaunchAgent: $label"
if launchctl print "$domain/$label" >/tmp/cloyd-smith-loop.launchctl 2>/dev/null; then
  grep -E '^[[:space:]]*(state|pid|last exit code) =' /tmp/cloyd-smith-loop.launchctl || true
else
  echo "state = not loaded"
fi
rm -f /tmp/cloyd-smith-loop.launchctl

echo
echo "Monitor: http://100.115.228.56:8000/agent-runs"
PYTHONPATH="$repo/src:$repo" "$python" - <<'PY'
import json
import urllib.error
import urllib.request

url = "http://100.115.228.56:8000/agent-runs/api/status"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.load(response)
except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
    print(f"Monitor API: unavailable ({exc})")
else:
    supervisor = payload.get("supervisor") or {}
    queue = payload.get("queue") or {}
    print(
        "Supervisor: "
        f"ok={supervisor.get('ok')} "
        f"status={supervisor.get('status')} "
        f"age={supervisor.get('age_seconds')}s"
    )
    print(
        "Queue: "
        f"running={queue.get('running', 0)} "
        f"queued={queue.get('queued', 0)} "
        f"review={queue.get('needs_review', 0)} "
        f"blocked={queue.get('blocked', 0)} "
        f"stale={queue.get('stale', 0)}"
    )
    for run in (payload.get("runs") or [])[:5]:
        print(
            "- "
            f"{run.get('job_id')}: "
            f"{run.get('job_status')}/{run.get('phase')} "
            f"retry={run.get('retry_attempts', 0)} "
            f"follow_up={run.get('follow_up_attempts', 0)} "
            f"next={run.get('next_action')}"
        )
PY

if [ "$verbose" = "1" ]; then
  echo
  echo "Log: $repo/logs/cloyd-smith-loop.log"
  if [ -f "$repo/logs/cloyd-smith-loop.log" ]; then
    tail -n 10 "$repo/logs/cloyd-smith-loop.log"
  else
    echo "no log yet"
  fi

  echo
  echo "Raw daemon status:"
  PYTHONPATH="$repo/src:$repo" "$python" "$repo/scripts/cloyd-smith-loop-daemon.py" --status
else
  echo
  echo "Tip: run $0 --verbose for recent log lines and raw ledger JSON."
fi
