#!/bin/bash
set -euo pipefail

BASE_URL="${FREYJA_CORE_URL:-http://127.0.0.1:8510}"
CALENDAR_ID="${FREYJA_SMOKE_CALENDAR_ID:-}"
START="${FREYJA_SMOKE_START:-}"
END="${FREYJA_SMOKE_END:-}"
OPENCODE_ALIAS="${FREYJA_SMOKE_OPENCODE_ALIAS:-freyja-core-smoke}"
OPENCODE_DIRECTORY="${FREYJA_SMOKE_OPENCODE_DIRECTORY:-/Users/freyja/freyja-os}"
OPENCODE_SEND_TIMEOUT="${FREYJA_SMOKE_OPENCODE_SEND_TIMEOUT:-30}"
CLEANUP_EVENT_ID="${FREYJA_SMOKE_CLEANUP_EVENT_ID:-}"
CLEANUP_PROVIDER="${FREYJA_SMOKE_CLEANUP_PROVIDER:-apple}"
CLEANUP_APPROVAL="${FREYJA_SMOKE_CLEANUP_APPROVAL:-}"

call_tool() {
    local tool="$1"
    local arguments="$2"
    curl -fsS "${BASE_URL}/tools/call" \
        -H 'content-type: application/json' \
        -d "{\"tool\":\"${tool}\",\"arguments\":${arguments}}"
    printf '\n'
}

echo "== status.check =="
call_tool "status.check" '{}'

echo "== calendar.resolve_date:this weekend =="
call_tool "calendar.resolve_date" '{"phrase":"this weekend"}'

echo "== calendar.create_event validation =="
call_tool "calendar.create_event" '{"title":"Freyja Core missing calendar smoke","start":"2026-09-19T10:00:00-04:00","end":"2026-09-19T10:15:00-04:00"}'

if [[ -n "${CALENDAR_ID}" && -n "${START}" && -n "${END}" ]]; then
    echo "== calendar.create_event live =="
    call_tool "calendar.create_event" "{\"title\":\"Freyja Core smoke test\",\"calendar_id\":\"${CALENDAR_ID}\",\"start\":\"${START}\",\"end\":\"${END}\",\"description\":\"Created by scripts/smoke-freyja-core-tools.sh\"}"
else
    echo "Skipping live calendar.create_event; set FREYJA_SMOKE_CALENDAR_ID, FREYJA_SMOKE_START, and FREYJA_SMOKE_END."
fi

if [[ -n "${CLEANUP_EVENT_ID}" ]]; then
    echo "== calendar.delete_event cleanup =="
    call_tool "calendar.delete_event" "{\"event_id\":\"${CLEANUP_EVENT_ID}\",\"provider\":\"${CLEANUP_PROVIDER}\",\"approval\":\"${CLEANUP_APPROVAL}\"}"
else
    echo "Skipping calendar.delete_event cleanup; set FREYJA_SMOKE_CLEANUP_EVENT_ID and FREYJA_SMOKE_CLEANUP_APPROVAL=DELETE_FREYJA_CORE_SMOKE_EVENT."
fi

echo "== opencode.start =="
call_tool "opencode.start" "{\"alias\":\"${OPENCODE_ALIAS}\",\"directory\":\"${OPENCODE_DIRECTORY}\"}"

echo "== opencode.status =="
call_tool "opencode.status" "{\"alias\":\"${OPENCODE_ALIAS}\"}"

echo "== opencode.send =="
call_tool "opencode.send" "{\"alias\":\"${OPENCODE_ALIAS}\",\"prompt\":\"Smoke test only. Reply with READY and do not edit files.\",\"timeout_seconds\":${OPENCODE_SEND_TIMEOUT}}"

echo "== opencode.read =="
call_tool "opencode.read" "{\"alias\":\"${OPENCODE_ALIAS}\",\"limit\":2}"

echo "== opencode.stop =="
call_tool "opencode.stop" "{\"alias\":\"${OPENCODE_ALIAS}\"}"

echo "== memory.write =="
call_tool "memory.write" '{"memory_id":"core-smoke","content":"Freyja Core smoke test memory hook is writable.","kind":"project_state"}'

echo "== memory.search =="
call_tool "memory.search" '{"query":"smoke test memory hook","limit":5}'
