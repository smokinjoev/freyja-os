# Freyja LibreChat Deployment

LibreChat is the operational web home for the five named Freyja agents. This
compose project uses separate containers, ports, volumes, and config from
`deploy/compose/open-webui`, which remains a raw-model and fallback UI.

The target shape is:

```text
browser -> LibreChat named agent -> Vulcan Nexus for inference
                                  -> Iris Freyja Core MCP for tools
```

LibreChat must not become a separate Freyja tool authority or model proxy.

## Ports

- LibreChat on Atlas: `http://100.119.235.114:3080`
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

`librechat.yaml` defines the `Vulcan Nexus` OpenAI-compatible endpoint and five
Iris Core Streamable HTTP MCP connections. Each MCP connection has its own
opaque agent token; secrets stay in `.env`.

The intended model path is:

```text
LibreChat -> Vulcan Nexus -> @preset/freyja-coder / @preset/freyja-strong-local / @preset/freyja-fast-local
LibreChat agent/tools -> agent-specific Freyja Core MCP -> Iris-owned tools
```

## Freyja Core MCP Backend

Run the backend on Iris before enabling LibreChat. On a cross-host Tailscale
deployment, bind it specifically to Iris's Tailscale address, not `0.0.0.0`:

```sh
cd ~/freyja-os
FREYJA_CORE_MCP_TOKEN="$(openssl rand -hex 32)" \
FREYJA_CORE_MCP_HOST=100.115.228.56 \
FREYJA_CORE_MCP_PORT=8766 \
.venv/bin/python scripts/freyja-core-mcp-server.py
```

Add a separate opaque token for every named agent to Iris's
`FREYJA_MCP_AGENT_TOKENS_JSON` map, then put the corresponding values in this
directory's `.env`. The server maps the presented token to its agent identity;
LibreChat therefore does not decide the tool permission set.

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

## Source-controlled agent contract

The five agent profiles are persisted in LibreChat's database and are described
in [`config/librechat-family-agents.yaml`](../../../config/librechat-family-agents.yaml).
The manifest is the recoverable source of truth; it contains no credentials.

## Operational checks

- Can each profile use its mapped `@preset/...` Nexus model?
- Can each profile discover `tools.search`, `tools.profile`, and `tools.call`?
- Does Iris reject a token belonging to a different named agent?
- Does LibreChat remain a client while Iris Core enforces the tool policy?

## 2026-09-29 operational status

LibreChat is live on Atlas. The five named agent profiles use direct Nexus
presets and each has a separate Iris Core MCP connection. The Iris MCP listener
is private to the Tailscale address on port 8766 and its bearer tokens remain
outside the repository.
