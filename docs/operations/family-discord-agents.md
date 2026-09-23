# Family Discord agents

The family deployment is opt-in and separate from the existing `freyja-test` validation bot.

It defines five standalone Discord agents: Freyja (shared household), Cloyd (Joe), Benedict (Beth), Agent 44 (Liam), and Agent Smith. They do not delegate to one another. The paralegal enclave remains agentless.

## Before activation

Create or identify one Discord application and one dedicated Discord channel for each agent. Enable the bot's Message Content intent and install it into the family server with permission to view/send messages only in its own channel. Record only the bot token and channel ID.

Store them in `~/.config/freyja-os/family-discord.env` on Iris with mode 600, following `config/freyja6/family-discord.env.example`. Generate a distinct Core MCP token for each agent and map it in `~/.config/freyja-os/core-mcp.env` to these identities: Freyja -> `freyja`; Cloyd -> `cloyd-gibbler`; Benedict -> `benedict`; Agent 44 -> `agent-47`; Agent Smith -> `smith`.

The existing test bot's token, channel, config, and service are not reused.

## Start and verify

After credentials are present, start only the family overlay:

```sh
cd /Users/freyja/freyja-os/deploy/compose/freyja6
docker compose --env-file .env --env-file ~/.config/freyja-os/family-discord.env -f compose.yaml -f compose.family-agents.yaml up -d
```

Verify every service individually, authenticate to Core with its own token, and send a normal message in each dedicated Discord channel. Do not put tokens in source control, command output, or Discord.
