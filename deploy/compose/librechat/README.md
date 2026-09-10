# Freyja LibreChat Evaluation

Parallel LibreChat deployment for comparing terminal-capable Qwen coding agents
against the existing Open WebUI deployment. This compose project uses separate
containers, ports, volumes, and config from `deploy/compose/open-webui`.

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
and a disabled-from-chat-menu `freyja-terminal` Streamable HTTP MCP server for
agent use. Secrets stay in `.env`.

The intended model path is:

```text
LibreChat -> Vulcan Nexus -> Qwen
LibreChat agent -> freyja-terminal MCP -> controlled terminal backend
```

## Terminal MCP Backend

Run the backend on Iris before enabling the LibreChat agent:

```sh
cd ~/freyja-os
FREYJA_TERMINAL_MCP_TOKEN="$(openssl rand -hex 32)" \
FREYJA_TERMINAL_MCP_HOST=127.0.0.1 \
FREYJA_TERMINAL_MCP_PORT=8765 \
.venv/bin/python scripts/freyja-terminal-mcp-server.py
```

Set `FREYJA_TERMINAL_MCP_TOKEN` in this directory's `.env` to the same value.
For Docker Desktop on Iris, LibreChat reaches it as
`http://host.docker.internal:8765/mcp`. For a LAN/Tailscale host, bind the MCP
server to the private interface and keep the bearer token enabled.

The MCP server wraps `scripts/openwebui-terminal-bridge.py`; it does not expose a
raw unauthenticated shell. The available MCP tools are:

- `terminal_start`
- `terminal_status`
- `terminal_send`
- `terminal_ctrl_c`
- `terminal_read`
- `terminal_stop`
