# Family Discord agents

The family deployment is opt-in and separate from the existing `freyja-test` validation bot.

It defines five standalone Discord agents: Freyja (shared household), Cloyd (Joe), Benedict (Beth), Agent 44 (Liam), and Agent Smith. They do not delegate to one another. The paralegal enclave remains agentless.

## Before activation

Create or identify one Discord application and one dedicated Discord channel for each agent. Enable the bot's Message Content intent and install it into the family server with permission to view/send messages only in its own channel. Record only the bot token and channel ID.

Store them in `~/.config/freyja-os/family-discord.env` on Iris with mode 600, following `config/freyja6/family-discord.env.example`. Generate a distinct Core MCP token for each agent and map it in `~/.config/freyja-os/core-mcp.env` to these identities: Freyja -> `freyja`; Cloyd -> `cloyd-gibbler`; Benedict -> `benedict`; Agent 44 -> `agent-47`; Agent Smith -> `smith`.

The existing test bot's token, channel, config, and service are not reused.

## Current Iris Discord runner

As of 2026-09-24, the active Discord path on Iris is the shared Python DM runner:

```text
Discord DM -> scripts/run-discord-dm-connector.py -> connectors.discord.gateway.DiscordGateway -> Director /canonical/route -> Vulcan Nexus -> external-ollama/qwen3.8:27b
```

The media and continuity behavior is implemented in shared code, not in a per-bot fork. Any Discord bot launched through `scripts/run-discord-dm-connector.py` receives the same current behavior:

- PDF and DOCX attachments route through Director document intake and Nexus.
- Image attachments route through Director image intake and Nexus.
- HEIC/HEIF uploads are accepted and converted to JPEG before provider calls when needed.
- Long document generations are allowed to keep running instead of timing out quickly.
- Long Discord replies are split into multiple Discord messages.
- Recent document and image attachments are reused for short followups for 20 minutes unless the message clearly starts a new topic.

The live Iris launchctl jobs currently observed are:

- `com.freyja-os.discord-dm-connector`: Cloyd Bot, submitted directly with `scripts/run-discord-dm-connector.py`.
- `com.freyja-os.discord-dm-connector-freyja`: Freyja, submitted through `scripts/run-discord-dm-connector-with-env.sh /Users/freyja/freyja-os/.env.discord-freyja`.

Benedict, Agent 44, and Smith do not need duplicate media-routing code. They need their own private token/env/service wrappers that launch the same runner with their own `DISCORD_BOT_TOKEN` and `DISCORD_USER_AGENT_MAP`.

## Start and verify

After credentials are present, start only the family overlay:

```sh
cd /Users/freyja/freyja-os/deploy/compose/freyja6
docker compose --env-file .env --env-file ~/.config/freyja-os/family-discord.env -f compose.yaml -f compose.family-agents.yaml up -d
```

Verify every service individually, authenticate to Core with its own token, and send a normal message in each dedicated Discord channel. Do not put tokens in source control, command output, or Discord.
