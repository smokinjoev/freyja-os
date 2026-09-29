# Family Discord Runbook

Discord is a messaging channel, not an independent agent runtime. A Discord
DM must resolve to the same canonical identity, model policy, tool boundary,
and memory scope used by that person's LibreChat agent.

## Current state

- Freyja and Cloyd Discord DM connectors are active on Iris.
- The connector sends identity and delivery metadata to Director; Director
  applies channel policy and routes to the canonical named agent.
- Iris Freyja Core remains the tool authority. Do not give a Discord bot a
  direct shell, Home Assistant, MacAgent, or OpenCode credential.
- Benedict, Agent 47, JennaCide, and Agent Smith are not activated as Discord
  personas until their owner, channel, and approval boundary are explicitly
  chosen.

## Add or repair a connector

1. Create a private Discord application and enable only the message intent
   needed for its assigned DM flow.
2. Store its token and routing configuration only in the private Iris runtime
   environment (`~/.config/freyja-os/family-discord.env`, mode 600). Never
   place it in this repository, command output, or chat.
3. Bind the bot to one approved canonical identity and its distinct Iris Core
   MCP token. Do not reuse a household identity for a private agent.
4. Restart only that connector, then send a text-only DM and verify its reply
   names the expected agent and preserves the expected conversation scope.
5. Confirm Core audit records show the correct identity before enabling tools
   beyond read-only status and search.

## Source checks

Run the repository-only safety check before editing connector code:

```sh
.venv/bin/python scripts/verify-discord-messaging.py
```

The historical multi-container experiment, legacy bot notes, and its
acceptance evidence are retained at
`archive/hermes-validation/docs/family-discord-runbook-legacy.md`.
