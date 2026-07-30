# Milestone 20: Travel-Ready Telegram Gateway and Restricted Agent Access

This document describes the Telegram gateway added to Freyja-OS for remote
operator access while away from the local network. It is strictly opt-in,
disabled by default, and bounded by the same safety model as the local
operator CLI.

## Architecture

```text
┌─────────────────┐      outbound HTTPS       ┌──────────────────┐
│  Telegram app   │ ────────────────────────▶ │  Telegram cloud  │
│  (operator)     │                          │  Bot API         │
└─────────────────┘                          └──────────────────┘
                                                    ▲
                                                    │ outbound HTTPS
                             ┌────────────────────┴──────────────┐
                             │   Telegram Gateway (LaunchAgent)  │
                             │   - long-poll getUpdates          │
                             │   - authorization                 │
                             │   - command routing               │
                             │   - offset persistence            │
                             └────────────┬──────────────────────┘
                                          │ loopback HTTP
                             ┌────────────▼─────────────┐
                             │   Freyja Director        │
                             │   - /route (Freyja)      │
                             │   - /agents/smith/*      │
                             │   - /health, /ollama/*   │
                             │   - /openrouter/*        │
                             └──────────────────────────┘
```

The gateway does **not** expose any inbound internet port. It uses Telegram's
outbound long-polling API (`getUpdates`) over HTTPS.

## Agent routing

Ordinary text messages are routed to the Freyja conversational agent via the
`/route` endpoint. The response includes the selected provider and model
appended to the reply.

Messages that begin with `/smith` are routed to Agent Smith's read-only
runtime (`/agents/smith/read-only`). The gateway never calls the write-pilot
or dry-run endpoints.

Slash commands are handled locally:

- `/help` — command list
- `/status` — Director, Ollama, OpenRouter, and agent enablement summary
- `/health` — bounded Director health check
- `/models` — configured and available models (no secrets)
- `/whoami` — your numeric Telegram user ID and chat type

Unknown slash commands return a concise help message.

## Authorization model

Authorization is strict and numeric:

- Only configured Telegram numeric user IDs are allowed.
- Direct messages (`chat.type == "private"`) only.
- Groups, supergroups, and channels are rejected.
- Anonymous senders (no `from_user`) are rejected.
- Usernames are never used for authorization.
- Rejected attempts are logged without message bodies.
- The bot token is loaded from `.env` and never logged or returned.

## Telegram privacy limitations

Telegram Bot API traffic transits Telegram's cloud. While the bot token and
message content are carried over HTTPS, Telegram's servers can see message
metadata and, for non-secret chats, message bodies. Do not send sensitive
personal data, credentials, or secrets through this gateway. For stronger
privacy in the future, the plan is to migrate to the Signal gateway on Atlas.
Hera is reserved for separate inference and benchmarking, not core messaging
infrastructure.

## Command list

| Command | Handler | Notes |
|---------|---------|-------|
| `text` | Freyja | routed to `/route` with `provider: auto` |
| `/help` | gateway | local help text |
| `/status` | gateway | queries Director, Ollama, OpenRouter, settings |
| `/health` | gateway | bounded `/health` check |
| `/models` | gateway | configured + available models |
| `/whoami` | gateway | user ID and chat type |
| `/smith <request>` | Smith read-only | only when Smith and read-only are enabled |

`/smith` supports shortcuts:

- `/smith status` → repository status
- `/smith repo` → repository status
- `/smith diff` → repository diff summary
- `/smith tests` → run test suite

## LaunchAgent behavior

A separate LaunchAgent runs the gateway:

- `scripts/com.freyja-os.telegram-gateway.plist`
- Label: `com.freyja-os.telegram-gateway`
- RunAtLoad: true
- KeepAlive: restarts on unexpected exit
- ThrottleInterval: 10 seconds
- Logs: `logs/telegram-gateway.log`

The gateway script (`scripts/run-telegram-gateway.py`) uses bounded
exponential backoff when Telegram or Director requests fail, with a minimum
backoff of 1 second and a maximum of 60 seconds.

## Failure recovery

- If Telegram is unreachable, the gateway backs off and retries; Director is
  unaffected.
- If Director is unreachable, replies fail gracefully with a safe error.
- On process restart, the gateway resumes from the last processed `update_id`
  stored in `~/.local/state/freyja/telegram/telegram-offset.json`.
- A heartbeat file is written to the same directory on every processed update.
- State directory permissions are `0o700`; offset and heartbeat files are
  `0o600`.

## State-file location and permissions

```text
~/.local/state/freyja/telegram/
├── telegram-offset.json        (0600, last processed update_id)
└── telegram-heartbeat.json     (0600, last gateway activity)
```

These files are outside the repository and are not tracked by git.

## Enable procedure

Run as the `freyja` user:

```bash
scripts/enable-telegram-travel-mode.sh <YOUR_TELEGRAM_USER_ID>
```

This script will:

- back up `.env` to `~/.local/state/freyja/env-backups/`,
- set `TELEGRAM_ENABLED=true`,
- set `TELEGRAM_ALLOWED_USER_IDS=<id>`,
- set `TELEGRAM_DIRECT_MESSAGES_ONLY=true`,
- set `TELEGRAM_SMITH_READ_ONLY_ENABLED=true`,
- enable `AGENT_SMITH_ENABLED=true` and `AGENT_SMITH_READ_ONLY_ENABLED=true`,
- keep `AGENT_SMITH_WRITE_PILOT_ENABLED=false`,
- restart Director,
- load the Telegram gateway LaunchAgent,
- print the disable command.

## Off-Wi-Fi phone test

After enablement:

1. Disable Wi-Fi on your phone.
2. Send `/whoami` to the Freyja bot.
3. Expect a reply with your numeric user ID and `private` chat type.
4. Send `/status` and confirm Director and Ollama state.

## Disable procedure

Run as the `freyja` user:

```bash
scripts/disable-telegram-travel-mode.sh
```

This disables Telegram, disables Smith read-only mode, and restarts Director.
It is idempotent.

## Emergency kill switch

From any shell on the host running the Telegram gateway:

```bash
launchctl bootout gui/$(id -u)/com.freyja-os.telegram-gateway
scripts/disable-telegram-travel-mode.sh
```

To verify the kill switch worked:

```bash
scripts/verify-telegram-travel-mode.sh
```

## What is and is not allowed during travel

Allowed:

- read-only Freyja conversations,
- read-only Smith diagnostics (`/smith status`, `/smith diff`, etc.),
- `/status`, `/health`, `/models`, `/whoami`, `/help`.

Not allowed:

- file writes,
- git add / commit / push,
- service restart,
- arbitrary shell commands,
- `.env` or secret access,
- enabling Smith write pilot,
- enabling arbitrary controlled-write tools,
- group or channel access.

## Verification script

```bash
scripts/verify-telegram-travel-mode.sh
```

Reports safe information and returns a non-zero exit code if any of these
hold:

- Telegram enabled without an allowlist,
- groups permitted,
- Smith write pilot enabled,
- arbitrary controlled-write tools enabled,
- Director unhealthy.

It never prints the bot token, allowed user IDs, or API keys.

## Future migration path

The gateway is implemented alongside the existing Signal gateway under
`connectors/`. The routing, authorization, and command logic are isolated to
`connectors/telegram/` so that the Atlas Signal gateway can reuse the same
Director endpoints and agent model without changing the core service.

## Files added or changed

- `src/freyja/config.py` — Telegram settings
- `.env.example` — example Telegram configuration
- `connectors/telegram/__init__.py`
- `connectors/telegram/config.py`
- `connectors/telegram/models.py`
- `connectors/telegram/gateway.py`
- `scripts/run-telegram-gateway.py`
- `scripts/com.freyja-os.telegram-gateway.plist`
- `scripts/enable-telegram-travel-mode.sh`
- `scripts/disable-telegram-travel-mode.sh`
- `scripts/verify-telegram-travel-mode.sh`
- `tests/test_telegram_gateway.py`
- `tests/test_telegram_scripts.py`
- `docs/telegram/milestone-20-travel-mode.md`
