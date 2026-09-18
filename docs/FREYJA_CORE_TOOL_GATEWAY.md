# Freyja Core Tool Gateway

Freyja Core runs on Iris and owns the first stable tool surface. Vulcan/Msty Nexus remains inference only. OpenWebUI and Msty Go should call this gateway instead of owning tool implementations.

## Service

- Command: `scripts/run-freyja-core.sh`
- Default bind: `FREYJA_CORE_HOST=100.115.228.56`
- Default port: `FREYJA_CORE_PORT=8510`
- Local test URL: `http://127.0.0.1:8510`
- Health: `GET /health`
- Tool list: `GET /tools`
- Tool call: `POST /tools/call`
- MCP wrapper: `scripts/freyja-core-mcp-server.py` exposes the same tool surface at `/mcp`.
- Apple Calendar timeout: `APPLE_CALENDAR_TIMEOUT_SECONDS` feeds both the Swift bridge and the MacAgent Apple Calendar backend.

Tool call envelope:

```json
{"tool":"calendar.resolve_date","arguments":{"phrase":"this weekend"}}
```

## Tools

- `status.check`: Core health, hostname, local time, configured tools, Nexus reachability, OpenCode reachability, calendar and memory configuration.
- `calendar.resolve_date`: deterministic dates for `today`, `tomorrow`, `this weekend`, `next weekend`, `this Friday`, and `next Friday` style weekday phrases.
- `calendar.create_event`: creates an event through the configured CalendarService provider. Required fields are `title`, `start`, `end`, and `calendar_id`; Freyja Core does not guess the calendar.
- `calendar.delete_event`: deletes a known smoke event only when `approval` is exactly `DELETE_FREYJA_CORE_SMOKE_EVENT`.
- `opencode.start`, `opencode.stop`, `opencode.status`, `opencode.send`, `opencode.read`: one named OpenCode session, backed by the existing OpenCode runtime adapter.
- `memory.search`, `memory.write`: minimal local shared-memory hooks.

## Smoke Tests

Start Core:

```bash
PYTHONPATH=src:. FREYJA_CORE_HOST=127.0.0.1 FREYJA_CORE_PORT=8510 .venv/bin/python -m freyja.core
```

Run direct shell smoke checks:

```bash
FREYJA_CORE_URL=http://127.0.0.1:8510 scripts/smoke-freyja-core-tools.sh
```

The smoke script checks `status.check`, deterministic date resolution, calendar write validation, OpenCode `start/status/send/read/stop`, and local memory `write/search`.

MCP wrapper smoke:

```bash
.venv/bin/pytest tests/test_freyja_core_mcp_server.py tests/test_freyja_terminal_mcp_server.py -q
```

Live wrapper check without a separate MCP client:

```bash
.venv/bin/python - <<'PY'
import asyncio, importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location("freyja_core_mcp_server", Path("scripts/freyja-core-mcp-server.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def main():
    tools = [tool.name for tool in await module.mcp.list_tools()]
    status = json.loads(await module.status_check())
    resolved = json.loads(await module.calendar_resolve_date("this weekend"))
    print(json.dumps({"tool_count": len(tools), "status_ok": status["ok"], "dates": resolved["dates"]}, indent=2))

asyncio.run(main())
PY
```

Live evidence from 2026-09-17:

- `status.check` reported Core healthy, Nexus reachable, OpenCode reachable, and MacAgent authenticated with `apple.calendar.read` and `apple.calendar.write`.
- `calendar.resolve_date` resolved `this weekend` from 2026-09-17 to `2026-09-19` and `2026-09-20`.
- `calendar.create_event` validation returned a clear missing-`calendar_id` error.
- A live Apple Calendar write created `Freyja Core smoke test` on `iCloud::Family` for `2026-09-18T07:10:00-04:00` to `2026-09-18T07:15:00-04:00`; user confirmation received that the Freyja calendar smoke test landed.
- OpenCode `start/status/send/read/stop` passed with smoke alias `freyja-core-smoke-2`; the session replied `READY` and stopped cleanly.
- `memory.write` and `memory.search` passed for `core-smoke`.
- Hardening pass after launchd reinstall confirmed `com.freyja-os.core` running with `APPLE_CALENDAR_TIMEOUT_SECONDS=30`, post-restart service smoke passed at `http://100.115.228.56:8510`, and live create/delete cleanup proved `calendar.delete_event` with explicit approval.

Run a live calendar write only when the target calendar and slot are intentional:

```bash
FREYJA_CORE_URL=http://127.0.0.1:8510 \
APPLE_CALENDAR_TIMEOUT_SECONDS=30 \
FREYJA_SMOKE_CALENDAR_ID=joe \
FREYJA_SMOKE_START=2026-09-19T10:00:00-04:00 \
FREYJA_SMOKE_END=2026-09-19T10:15:00-04:00 \
scripts/smoke-freyja-core-tools.sh
```

## Failure Modes

- Missing tool name returns `ok:false` and lists configured tools.
- Missing `calendar.create_event` title/start/end/calendar_id returns `ok:false` with the missing fields.
- `calendar.delete_event` returns `approval_required:true` unless the exact cleanup approval token is supplied.
- OpenCode errors are returned from the runtime adapter; unknown aliases return a clear alias error.
- `status.check` may report downstream failures while the Core itself remains healthy. When Apple Calendar is configured through MacAgent, status includes MacAgent health.
- Apple Calendar writes can fail if MacAgent is unreachable, not authenticated, lacks Calendar permission, or exceeds `APPLE_CALENDAR_TIMEOUT_SECONDS`.
- Nexus failures do not block direct tool calls; Nexus is only used for inference/synthesis paths.

## Msty Go Routing

The live Msty Go database is:

```text
/Users/freyja/Library/Application Support/Msty Go/msty-go.db
```

Before adding Core routing instructions to the Freyja bot row, this backup was created:

```text
/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-freyja-core-routing-20260917-093842
```

Before aligning Freyja back to the previously proven Msty tool-calling model `@preset/freyja-coder`, this backup was created:

```text
/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-freyja-core-tool-model-20260917-094530
```

Freyja's Msty Go bot instructions now include a Core routing block:

```text
Freyja Core tool gateway:
- Freyja Core owns tools on Iris at http://100.115.228.56:8510 and local loopback http://127.0.0.1:8510 when running on Iris.
- For calendar date resolution, event creation, OpenCode session control, memory hooks, or tool health, route through Freyja Core instead of inventing tool behavior in this prompt or relying on OpenWebUI/Nexus tool classes.
- Use the shell tool to call POST /tools/call with curl when a dedicated Msty MCP tool is not available.
- Do not send private data to cloud services. Nexus/Vulcan is inference only; Freyja Core is the tool authority.
```

Verification so far: the database row contains the routing instructions and Freyja has shell access enabled. A live Msty Go Freyja chat on `@preset/freyja-coder` called Core through Msty's shell tool and returned `["2026-09-19","2026-09-20"]` from `calendar.resolve_date`.

Repeatable verifier:

```bash
PYTHONPATH=src:. FREYJA_CORE_HOST=127.0.0.1 FREYJA_CORE_PORT=8510 .venv/bin/python -m freyja.core
scripts/verify-msty-freyja-core-routing.py \
  --core-url http://127.0.0.1:8510 \
  --since 2026-09-17T13:38:00Z \
  --output certification/reports/msty-freyja-core-routing-20260917.json
```

The verifier passed on 2026-09-17: Core was live with all required tools, the Msty Go Freyja bot row had shell access enabled, and the Core routing block plus `POST /tools/call` instruction were present. The current report also includes live Msty tool-loop proof after `2026-09-17T13:46:00Z`:

- Msty tool event `YaKU5nLbg3wSBe3kIYqMX`
- conversation/session `6AEXCObCur-32NmTWCMJN`
- message `WrU3DIGmhosiuJMq84_9x`
- model `@preset/freyja-coder`
- tool `shell`, status `completed`
- command posted to `http://127.0.0.1:8510/tools/call`
- Core result resolved `this weekend` to `2026-09-19` and `2026-09-20`
