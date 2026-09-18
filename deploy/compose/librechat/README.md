# Freyja LibreChat Pass-Through Evaluation

Parallel LibreChat deployment for evaluating a tablet-friendly pass-through UI.
This compose project uses separate containers, ports, volumes, and config from
`deploy/compose/open-webui`.

The target shape is:

```text
iPad -> LibreChat -> Vulcan Nexus for inference
                  -> Freyja Core MCP for tools
```

LibreChat should not become a separate Freyja tool authority.

## Ports

- LibreChat: `http://localhost:3080`
- LibreChat admin panel: `http://localhost:3090`

Set `LIBRECHAT_BIND_IP` in `.env` to a Tailscale/LAN address if this should not
bind on all interfaces.

## Setup

```sh
cd deploy/compose/librechat
cp .env.example .env
openssl rand -hex 32
docker compose up -d
```

`librechat.yaml` defines the `Vulcan Nexus` OpenAI-compatible custom endpoint
and one `freyja-core` Streamable HTTP MCP server. Secrets stay in `.env`.

The intended model path is:

```text
LibreChat -> Vulcan Nexus -> @preset/freyja-coder / @preset/freyja-strong-local / @preset/freyja-fast-local
LibreChat agent/tools -> freyja-core MCP -> Iris-owned Freyja Core tools
```

## Freyja Core MCP Backend

Run the backend on Iris before enabling the LibreChat trial:

```sh
cd ~/freyja-os
FREYJA_CORE_MCP_TOKEN="$(openssl rand -hex 32)" \
FREYJA_CORE_MCP_HOST=127.0.0.1 \
FREYJA_CORE_MCP_PORT=8766 \
.venv/bin/python scripts/freyja-core-mcp-server.py
```

Set `FREYJA_CORE_MCP_TOKEN` in this directory's `.env` to the same value.
For Docker Desktop on Iris, LibreChat reaches it as
`http://host.docker.internal:8766/mcp`. For a LAN/Tailscale host, bind the MCP
server to the private interface and keep the bearer token enabled.

The MCP server wraps `freyja.core.call_tool`; it does not implement separate
calendar, OpenCode, memory, or policy logic. The available MCP tools are:

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

## Pass/Fail Questions

- Can LibreChat use the `Vulcan Nexus` custom endpoint with `@preset/...` model ids?
- Can LibreChat discover and call the `freyja-core` MCP tools?
- Does the iPad web experience feel better than OpenWebUI for pass-through chat?
- Does LibreChat avoid creating a second tool authority?

## 2026-09-18 Evaluation Status

Config and direct backend checks pass: Nexus is reachable with the expected
Freyja presets, Freyja Core MCP exposes the Core-owned tools, and the compose
configuration renders without errors. The full browser/iPad smoke is still
blocked because the initial LibreChat Docker image pull did not complete within
the bounded trial window. Retry `docker compose up -d` from this directory when
ready to spend the setup time, then test the UI at `http://localhost:3080`.
