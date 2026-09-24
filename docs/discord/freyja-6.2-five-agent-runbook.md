# Freyja 6.2 Five-Agent Discord Runbook

Status: Discord DM connector is enabled for `Cloyd Bot` only. The private `.env` contains a verified `Cloyd Bot` token, and the live runner has reached Discord Gateway READY as `Cloyd Bot`.

## Invariants

- Discord is private, DM-only, text-only, and final-only.
- Each approved Discord user id maps to exactly one default approved agent.
- Multiple approved Discord user ids may share Freyja as their default agent.
- Approved agents are Freyja, Cloyd Gibbler, Benedict, Agent 44, and Agent Smith.
- Signal remains available. iMessage is out of scope for this setup.
- Do not restart, reconfigure, or disrupt Nexus, Msty Go, OpenCode, OpenWeb, OpenCodex, Signal, or existing endpoints/services.
- Never print, commit, or store Discord bot tokens or Director connector tokens in tracked files.

## Portal Steps

Stop for operator confirmation before each action in this section.

1. Create or select the private Discord application for Freyja 6.2.
2. Create the bot user.
3. Enable Message Content intent.
4. Generate or reset the bot token only after explicit confirmation.
5. Build a private invite URL with bot scope only and least required permissions for DM handling.
6. Record, privately, the Discord application/client id, bot token, Director connector token, and approved Discord user ids.

## Current Portal Evidence

Observed in the logged-in Safari Discord Developer Portal session on 2026-09-22:

Five-agent application roster currently visible in the portal:

| Agent | Portal application | Application/client id | Status |
| --- | --- | --- | --- |
| Freyja | `Freyja` | `1552077476384219177` | Private bot settings configured and saved |
| Cloyd Gibbler | `Cloyd Bot` | `1505770810164645969` | Private bot settings configured and saved |
| Benedict | `Benedict` | `1551998761717207080` | Private bot settings configured and saved |
| Agent 44 | `Agent 44` | `1552077623771799623` | Private bot settings configured and saved |
| Agent Smith | `Agent Smith` | `1552127809151828098` | Private bot settings configured and saved |

Additional visible applications not assigned to the five-agent roster:

- `Freyja-test6` (`1551292401706868856`), configured as the private Freyja 6.2 test bot below.
- `Iris Gateway` (`1550930810813554811`).
- `Jenna` (`1552077719020371978`).

Private Freyja 6.2 test bot evidence:

- Existing application: `Freyja-test6`
- Application/client id: `1551292401706868856`
- Bot username: `Freyja-test6`
- Message Content Intent: enabled
- Bot token: present but not viewable; reset is required only if no private token is already held
- Installation default authorization link: None
- Public Bot: disabled
- Server Members Intent: disabled
- Presence Intent: disabled
- Bot permissions integer: `0`
- Prepared bot-only invite: `https://discord.com/oauth2/authorize?client_id=1551292401706868856&scope=bot&permissions=0`

Current live-enable scope:

- The private token currently loaded into `.env` identifies `Cloyd Bot` (`1505770810164645969`) when queried through Discord's API.
- The connector was enabled only after the validation gates below passed and the operator explicitly confirmed live transport startup.
- The current private map routes Smokinjoe (`895679349225820212`) to Cloyd Gibbler (`cloyd-gibbler`) by default.
- The five roster applications (`Freyja`, `Cloyd Bot`, `Benedict`, `Agent 44`, and `Agent Smith`) are configured privately in the Discord Developer Portal but do not come online automatically. They require separate private bot tokens and live runner wiring before they can run as distinct bots.
- A Cloyd-specific private Discord bot token is present in `.env`; the value must never be printed, committed, or copied into tracked files.

Five-agent private bot evidence:

| Agent | Bot username | Discriminator | Installation link | Public Bot | Presence Intent | Server Members Intent | Message Content Intent | Bot permissions integer | Token action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Freyja | `Freyja` | `4389` | None | disabled | disabled | disabled | enabled | `0` | token privately stored and verified |
| Cloyd Gibbler | `Cloyd Bot` | `4433` | None | disabled | disabled | disabled | enabled | `0` | token privately stored and verified |
| Benedict | `Benedict` | `0909` | None | disabled | disabled | disabled | enabled | `0` | not viewed, reset, or generated |
| Agent 44 | `Agent 44` | `6695` | None | disabled | disabled | disabled | enabled | `0` | not viewed, reset, or generated |
| Agent Smith | `Agent Smith` | `1959` | None | disabled | disabled | disabled | enabled | `0` | not viewed, reset, or generated |

Each roster application showed a saved Discord Developer Portal confirmation after its Installation and Bot settings were changed. No token value was revealed, copied, reset, or generated during this portal pass.

Prepared bot-only invite URLs with `permissions=0`:

| Agent | Invite URL |
| --- | --- |
| Freyja | `https://discord.com/oauth2/authorize?client_id=1552077476384219177&scope=bot&permissions=0` |
| Cloyd Gibbler | `https://discord.com/oauth2/authorize?client_id=1505770810164645969&scope=bot&permissions=0` |
| Benedict | `https://discord.com/oauth2/authorize?client_id=1551998761717207080&scope=bot&permissions=0` |
| Agent 44 | `https://discord.com/oauth2/authorize?client_id=1552077623771799623&scope=bot&permissions=0` |
| Agent Smith | `https://discord.com/oauth2/authorize?client_id=1552127809151828098&scope=bot&permissions=0` |

## Local Environment

Configure local private environment values only after explicit operator authorization:

```sh
DISCORD_ENABLED=false
DISCORD_BOT_TOKEN=<private>
FREYJA_CONNECTOR_TOKEN=<private>
FREYJA_DIRECTOR_URL=http://127.0.0.1:8000
DISCORD_USER_AGENT_MAP=<discord-user-id>=freyja,<discord-user-id>=cloyd-gibbler,<discord-user-id>=benedict,<discord-user-id>=agent-47,<discord-user-id>=smith
```

Keep `DISCORD_ENABLED=false` until live validation succeeds. Current live Cloyd validation has explicitly enabled this value.

Current redacted local env evidence on 2026-09-22:

- `.env`, `deploy/compose/signal/.env`, `deploy/compose/director/.env`, and `deploy/compose/freyja6/.env` are ignored by git.
- A Director connector token is already present in private ignored env files, but must be reused only with operator authorization.
- A private `FREYJA6_DISCORD_BOT_TOKEN` exists in `deploy/compose/freyja6/.env`; it was not printed or copied during this audit.
- The connector currently reads `DISCORD_BOT_TOKEN`, so enablement must either map the approved private token into that key or update the runner to consume the existing private key.
- `DISCORD_USER_AGENT_MAP` is now present in private `.env` with Smokinjoe mapped to Cloyd Gibbler by default.
- The current private `DISCORD_BOT_TOKEN` identifies `Cloyd Bot` (`1505770810164645969`) when queried through Discord's API.
- Recent messages in the existing Discord channel show one candidate human author id for Smokinjoe: `895679349225820212`.
- The Discord app's visible `IRIS` / `freyja-6-test` member list shows one human member, Smokinjoe, plus the `Iris Gateway` and `Freyja-test6` app/bot accounts.
- A REST attempt to enumerate guild members with the existing private bot token returned Discord `403 Missing Access`, so the locked-down bot cannot discover additional household user ids from the guild member API.
- No authoritative source has identified the other approved Discord user ids. The operator clarified that everyone else should default to Freyja when those ids are available.
- Re-run `scripts/discord-user-id-audit.py` to safely re-audit candidate human author ids from the private Discord env without printing the bot token.
- Re-run `scripts/validate-discord-private-env.py --env-file .env` to validate private env readiness without printing secrets.
- Live DM transport runner prepared at `scripts/run-discord-dm-connector.py`; it uses Discord Gateway direct-message events only and routes them through the DM-only `DiscordGateway`.
- `websockets` is declared in `pyproject.toml` for the live Discord Gateway connection and has been installed in the current `.venv`.
- Disabled-start preflight command confirms the live runner imports and refuses to start while `DISCORD_ENABLED=false`:

```sh
set -a; . ./.env; set +a; .venv/bin/python scripts/run-discord-dm-connector.py
# Expected before live enablement: "Discord connector not started: Discord transport is disabled." and exit status 1.
```
- Live enablement attempt after operator approval:
  - The connector was temporarily enabled with the only loaded private token.
  - Discord Gateway READY was observed for bot id `1551292401706868856`, username `Freyja-test6`.
  - Operator identified that this was the old test bot and asked about Cloyd.
  - The connector process was stopped, and `DISCORD_ENABLED=false` was restored in private `.env`.
  - Cloyd Bot token provisioning is complete.
  - After focused validation and explicit operator confirmation, the connector was enabled and started.
  - Discord Gateway READY was observed for bot id `1505770810164645969`, username `Cloyd Bot`.
  - The live runner is currently launched through launchd label `com.freyja-os.discord-dm-connector`.
  - Stop command: `launchctl remove com.freyja-os.discord-dm-connector`
  - Cloyd Bot was installed into the `IRIS` Discord server.
  - Bot-initiated DM channel establishment to Smokinjoe succeeded after install.
  - A Smokinjoe DM was received from Discord user id `895679349225820212`, routed to `cloyd-gibbler`, and replied successfully with trace id `discord-10fb903ee2c94ce6a13b593b3e09a141`.
  - Operator-observed agent runtime evidence: Cloyd Gibbler received the objective, recalled 8 memory records, selected no tools for that message, and used `vulcan-nexus-strong`.

Next private enablement inputs required from the operator:

- Freyja app pre-token check: Bot page remains private with Public Bot disabled, Presence Intent disabled, Server Members Intent disabled, Message Content Intent enabled, permissions integer `0`; Installation page remains `Install Link: None`.
- Freyja token provisioning is complete; the private `FREYJA_DISCORD_BOT_TOKEN` identifies bot id `1552077476384219177`, username `Freyja`.
- Freyja is installed in the `IRIS` Discord server.
- Freyja live runner is started through launchd label `com.freyja-os.discord-dm-connector-freyja`.
- Freyja stop command: `launchctl remove com.freyja-os.discord-dm-connector-freyja`
- Freyja Discord Gateway READY was observed for bot id `1552077476384219177`, username `Freyja`.
- Freyja DM channel establishment to Smokinjoe succeeded.
- A Smokinjoe DM was received from Discord user id `895679349225820212`, routed to `freyja`, and replied successfully with trace id `discord-025d95eab22d4e17a9108ad3ea7f428c`.
- Add the remaining authorized numeric Discord user ids as they become available. Smokinjoe is currently configured privately as:

```sh
DISCORD_USER_AGENT_MAP=895679349225820212=cloyd-gibbler
```

Future authorized users should default to `freyja` unless the operator gives a different per-user default. Add each numeric Discord user id privately and re-run deterministic validation before changing live routing.

Current media-routing checkpoint on 2026-09-24:

- Cloyd and Freyja use the shared `scripts/run-discord-dm-connector.py` runner and `connectors.discord.gateway.DiscordGateway`; media handling is not bot-specific.
- The active Discord funnel is Discord DM -> Director `/canonical/route` -> Vulcan Nexus -> `external-ollama/qwen3.8:27b`.
- PDF and DOCX attachments are extracted by Director and answered through Nexus document intake.
- Image attachments are sent through Nexus image intake; HEIC/HEIF is accepted and converted to JPEG when required.
- Long local document answers are allowed to continue for up to 240 seconds in Director and 300 seconds in the Discord gateway.
- Long bot replies are split into Discord-sized chunks instead of being truncated.
- Recent PDF/DOCX/image attachments are reused for short followups for 20 minutes unless the message clearly starts a new topic.
- The same behavior applies to Benedict, Agent 44, and Smith when they are launched through the same runner with their own private bot token and `DISCORD_USER_AGENT_MAP`.

## Validation Gates

Run these before enabling the live transport:

```sh
python scripts/verify-freyja-6.2-messaging.py
pytest -q
```

On this host, bare `python` and `pytest` are not currently on `PATH`; use the repo venv equivalents unless the shell environment is updated:

```sh
.venv/bin/python scripts/verify-freyja-6.2-messaging.py
.venv/bin/python -m pytest -q
```

Current validation evidence on 2026-09-22:

- Deterministic Discord verifier passes with Discord disabled and `live_transport_ready=false`.
- Focused Discord/messaging tests pass: `16 passed`.
- Family Discord roster artifacts now consistently use Agent Smith (`smith`) as the fifth agent instead of the earlier Jenna/Jennacide reservation. Updated artifacts include the family env example, family compose overlay, future-agent isolation manifest, migration/preservation/schedule guardrails, and family Discord runbook.
- Freyja 6 scaffold slices covering future-agent isolation, gateway isolation, preservation, migration readiness, memory boundary, and messaging boundary pass: `98 passed, 421 deselected`.
- `scripts/freyja6-gateway-isolation-audit.py`, `scripts/freyja6-preservation-audit.py`, and `scripts/freyja6-schedule-boundary-audit.py` pass with the Agent Smith roster.
- Tracked Discord setup files were scanned for live token-shaped values; findings were limited to placeholders and fake test values.
- Full `.venv/bin/python -m pytest -q` has been run and is not yet clean: `2369 passed, 1 skipped, 12 failed, 2 warnings`.
- The observed full-suite failures are outside the new Discord connector tests and cover existing Freyja 5 Agent Smith export/config drift, Freyja 6 LiteLLM/Hermes/model privacy scaffold drift, OpenWebUI evidence/completion metrics, home memory evidence, and tool registry count expectations.

Live transport was started only after the operator confirmed the final enable/run step. Keep the runner limited to the DM-only Cloyd validation until the remaining authorized users and bot tokens are provisioned.
