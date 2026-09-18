# Freyja Core Runbook

Freyja Core is the Iris-owned tool gateway. Vulcan/Msty Nexus remains inference only.

## Service

- LaunchAgent label: `com.freyja-os.core`
- Source plist: `scripts/com.freyja-os.core.plist`
- Installed plist: `/Users/freyja/Library/LaunchAgents/com.freyja-os.core.plist`
- Program: `scripts/run-freyja-core.sh`
- Bind: `100.115.228.56:8510`
- Log: `logs/freyja-core.log`

Environment set by launchd:

- `FREYJA_CORE_HOST=100.115.228.56`
- `FREYJA_CORE_PORT=8510`
- `NEXUS_BASE_URL=http://100.94.80.21:3939`
- `NEXUS_API_KEY_FILE=/Users/freyja/.config/freyja/msty-nexus-token`
- `APPLE_CALENDAR_TIMEOUT_SECONDS=30`
- `FREYJA_CORE_STATUS_TIMEOUT_SECONDS=8`

## Commands

Install or reinstall:

```bash
scripts/install-freyja-core.sh
```

Inspect:

```bash
launchctl print gui/$(id -u)/com.freyja-os.core
tail -n 100 logs/freyja-core.log
curl -fsS http://100.115.228.56:8510/health
curl -fsS http://100.115.228.56:8510/tools
```

Restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.freyja-os.core
```

Stop:

```bash
launchctl bootout gui/$(id -u)/com.freyja-os.core
```

Rollback launchd plist:

```bash
cp /path/to/known-good/com.freyja-os.core.plist /Users/freyja/Library/LaunchAgents/com.freyja-os.core.plist
launchctl bootout gui/$(id -u)/com.freyja-os.core 2>/dev/null || true
launchctl bootstrap gui/$(id -u) /Users/freyja/Library/LaunchAgents/com.freyja-os.core.plist
```

## Post-Restart Smoke

```bash
FREYJA_CORE_URL=http://100.115.228.56:8510 \
FREYJA_SMOKE_OPENCODE_ALIAS=freyja-core-hardening \
FREYJA_SMOKE_OPENCODE_SEND_TIMEOUT=20 \
scripts/smoke-freyja-core-tools.sh
```

This proves:

- `status.check`
- `calendar.resolve_date`
- missing-calendar validation for `calendar.create_event`
- guarded `calendar.delete_event` skip unless cleanup env vars are set
- `opencode.start/status/send/read/stop`
- `memory.write/search`

Live calendar create and cleanup:

```bash
FREYJA_CORE_URL=http://100.115.228.56:8510 \
FREYJA_SMOKE_CALENDAR_ID=joe \
FREYJA_SMOKE_START=2026-09-18T07:20:00-04:00 \
FREYJA_SMOKE_END=2026-09-18T07:25:00-04:00 \
scripts/smoke-freyja-core-tools.sh
```

To delete a known smoke event:

```bash
FREYJA_CORE_URL=http://100.115.228.56:8510 \
FREYJA_SMOKE_CLEANUP_EVENT_ID='EVENT_ID_FROM_CREATE' \
FREYJA_SMOKE_CLEANUP_PROVIDER=apple \
FREYJA_SMOKE_CLEANUP_APPROVAL=DELETE_FREYJA_CORE_SMOKE_EVENT \
scripts/smoke-freyja-core-tools.sh
```

The cleanup tool refuses to delete without `approval=DELETE_FREYJA_CORE_SMOKE_EVENT`.

## Msty Go

Freyja's Msty Go bot row is configured for:

- model: `@preset/freyja-coder`
- shell access: enabled
- Core routing block in custom instructions

Backups made before live Msty edits:

- `/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-freyja-core-routing-20260917-093842`
- `/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-freyja-core-tool-model-20260917-094530`

Verifier:

```bash
scripts/verify-msty-freyja-core-routing.py \
  --core-url http://100.115.228.56:8510 \
  --since 2026-09-17T13:46:00Z \
  --output certification/reports/msty-freyja-core-routing-20260917.json
```

Current evidence:

- Completed Msty shell/Core proof exists for loopback Core from the first validation.
- Post-restart service endpoint is directly smoke-tested at `100.115.228.56:8510`.
- A later Msty service-endpoint attempt generated the correct shell command but was stopped before approval, so it is recorded as denied and is not counted as completed proof.
- Do not add an Msty MCP row until Msty's `mcp_servers.transport_config` shape is verified from docs or a working export.

## MCP Wrapper

Freyja Core also has a minimal MCP-compatible wrapper. It is a protocol adapter only; it delegates to `freyja.core.call_tool` and does not duplicate calendar, OpenCode, memory, or policy logic.

Run locally:

```bash
PYTHONPATH=src:. FREYJA_CORE_MCP_HOST=127.0.0.1 FREYJA_CORE_MCP_PORT=8766 \
.venv/bin/python scripts/freyja-core-mcp-server.py
```

Health:

```bash
curl -fsS http://127.0.0.1:8766/healthz
```

MCP transport:

```text
http://127.0.0.1:8766/mcp
```

Optional bearer auth:

```bash
FREYJA_CORE_MCP_TOKEN='local-token' \
PYTHONPATH=src:. .venv/bin/python scripts/freyja-core-mcp-server.py
```

The MCP wrapper exposes the canonical Core tool names:

- `status.check`
- `calendar.resolve_date`
- `calendar.create_event`
- `calendar.delete_event`
- `opencode.start`
- `opencode.stop`
- `opencode.status`
- `opencode.send`
- `opencode.read`
- `memory.search`
- `memory.write`

Smoke from shell without an MCP client:

```bash
.venv/bin/python - <<'PY'
import asyncio, importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location("freyja_core_mcp_server", Path("scripts/freyja-core-mcp-server.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def main():
    tools = [tool.name for tool in await module.mcp.list_tools()]
    resolved = json.loads(await module.calendar_resolve_date("this weekend"))
    print(json.dumps({"tools": tools, "resolved": resolved}, indent=2))

asyncio.run(main())
PY
```

## Failure Modes

- Core healthy but downstream unhealthy: inspect `status.check.downstream`.
- Apple Calendar timeout: verify MacAgent health and `APPLE_CALENDAR_TIMEOUT_SECONDS=30`.
- Nexus unavailable: direct tool calls still work; only synthesis/inference paths are affected.
- OpenCode unknown alias: run `opencode.start` before `opencode.status/read/send`.
- Calendar cleanup denied: include the exact approval token only for known smoke event IDs.
- MCP wrapper unhealthy: verify the wrapper process separately from the Core launchd service. The wrapper can be down while HTTP Core remains healthy.
