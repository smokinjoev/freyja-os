# Freyja Gateway Remote

The remote mobile surface is a Tailscale-only PWA that reaches Freyja 5 Gateway
agents through the existing OpenAI-compatible endpoint. It does not control the
Iris desktop, expose Nexus administrative credentials, or modify Msty Go local
storage.

Msty Go 0.15.4 documents Remote Routes and Channels, including Msty Go mobile
routes, under Settings > Remote Routes. Those routes require operator account
state and mobile pairing. Until that is configured inside Msty Go itself, the
PWA exposes Gateway equivalents for Freyja, Benedict, Benedict Paralegal, Agent
44, Jenna, and Cloyd. Their state is Freyja Gateway state, not Msty Go-local
agent state. Benedict Paralegal uses `agent/benedict-paralegal`, which remains
local-only with no cloud fallback through the Freyja 5 Gateway policy.

The service binds to `127.0.0.1:8010` and proxies to the protected local
Freyja 5 OpenAI-compatible endpoint at `http://127.0.0.1:8503/v1`. Tailscale Serve publishes it
privately:

```bash
tailscale serve --bg https / http://127.0.0.1:8010
```

Use `scripts/com.freyja-os.gateway-remote.plist` for persistent launch on Iris.
Use `scripts/com.freyja-os.freyja5-openai.plist` for the loopback-only Freyja 5
Gateway endpoint. The installed LaunchAgent copy must receive the local
connector token and Nexus token from operator-managed secrets; those values are
not committed.
Tokens are generated under `~/.local/state/freyja/gateway-remote/tokens.json`
as SHA-256 hashes. Raw tokens are printed only when first created.

Health:

```bash
curl http://127.0.0.1:8010/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8010/status
```

Remote URL:

```text
https://joes-mac-mini.tail3995b4.ts.net/
```
