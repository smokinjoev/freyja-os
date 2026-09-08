# Freyja Channels on Atlas

This Compose project runs the deterministic Open WebUI messaging gateway on
Atlas. It does not route models or contain independent agent intelligence. Each
message follows:

`Telegram/Signal sender -> verified family identity -> permitted agent -> Open WebUI API -> response`

Open WebUI remains the agent platform. Vulcan remains the local inference path
behind Open WebUI. WhatsApp stays disabled until a secured public webhook is
explicitly approved.

The Freyja 5 messaging agent surface is configured in
`config/freyja-channels.yaml`. Telegram and Signal can expose `freyja`, `cloyd`,
`benedict`, `agent-44`, and `jenna`; the gateway still enforces each sender's
identity-specific `permitted_agents` list before forwarding anything.

Allowed senders can choose a permitted agent with either command form:

```text
/agent cloyd check the repo
@benedict review this
```

If no command prefix is present, the sender's configured default agent is used.
Unknown aliases are left as normal message text and do not bypass the
permitted-agent check.

The channel services publish no ports. Telegram uses outbound long polling, and
Signal reaches `signal-cli-rest-api` on the private Docker network.

## Secrets

Copy `.env.example` to `.env`, set mode `0600`, and keep it uncommitted. The
preferred Open WebUI credential is the Atlas key file:

```bash
OPEN_WEBUI_API_KEY_HOST_FILE=/home/joe/.freyja/open-webui-api-key
OPEN_WEBUI_API_KEY_FILE=/run/secrets/open_webui_api_key
```

Do not put bot tokens, phone numbers, or API keys in source control.
The containers run as `FREYJA_CHANNELS_UID:FREYJA_CHANNELS_GID` so
`FREYJA_CHANNEL_STATE_DIR` can persist dry-run reports, thread mappings, and
audit records.

## Telegram Pilot

Telegram is profile-gated and remains off until explicitly started. The
preferred setup is one Telegram bot per exposed person/agent lane. Configure the
matching token, allowlist, identity map, and forced agent in `.env`:

```text
TELEGRAM_FREYJA_JOE_BOT_TOKEN=...
TELEGRAM_FREYJA_JOE_ALLOWED_USER_IDS=<joe telegram numeric id>
TELEGRAM_FREYJA_JOE_IDENTITY_MAP=<joe telegram numeric id>:joe
TELEGRAM_FREYJA_JOE_AGENT=freyja

TELEGRAM_CLOYD_JOE_BOT_TOKEN=...
TELEGRAM_CLOYD_JOE_ALLOWED_USER_IDS=<joe telegram numeric id>
TELEGRAM_CLOYD_JOE_IDENTITY_MAP=<joe telegram numeric id>:joe
TELEGRAM_CLOYD_JOE_AGENT=cloyd

TELEGRAM_BENEDICT_BETH_BOT_TOKEN=...
TELEGRAM_BENEDICT_BETH_ALLOWED_USER_IDS=<beth telegram numeric id>
TELEGRAM_BENEDICT_BETH_IDENTITY_MAP=<beth telegram numeric id>:beth
TELEGRAM_BENEDICT_BETH_AGENT=benedict

TELEGRAM_AGENT44_LIAM_BOT_TOKEN=...
TELEGRAM_AGENT44_LIAM_ALLOWED_USER_IDS=<liam telegram numeric id>
TELEGRAM_AGENT44_LIAM_IDENTITY_MAP=<liam telegram numeric id>:liam
TELEGRAM_AGENT44_LIAM_AGENT=agent-44

TELEGRAM_JENNA_BOT_TOKEN=...
TELEGRAM_JENNA_ALLOWED_USER_IDS=<jenna telegram numeric id>
TELEGRAM_JENNA_IDENTITY_MAP=<jenna telegram numeric id>:jenna
TELEGRAM_JENNA_AGENT=jenna
```

Each profile uses its own bot token and offset file. The forced agent is applied
before the gateway routes the message, so a Cloyd bot cannot be turned into a
Benedict bot by prompt text. The shared `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALLOWED_USER_IDS`, and `TELEGRAM_IDENTITY_MAP` variables remain
available as the legacy single-bot pilot path.

For the legacy single bot, configure:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- `TELEGRAM_IDENTITY_MAP`, for example `123456789:joe`
- `TELEGRAM_MAX_ATTACHMENT_BYTES`, default `8388608`

An empty allowlist is deny-all.
Telegram images and documents under the size cap are forwarded to Open WebUI as
base64 payloads. Oversized files are skipped with metadata only.

Validate without sending:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile operator run --rm telegram-dry-run
```

The dry-run report is written to `/state/telegram-dry-run.json`, backed by
`data/freyja-channels` by default.

Enable long polling only after dry-run readiness is true:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile telegram up -d --build telegram-pilot
```

## Signal

Signal uses the existing `signal-cli-rest-api` pathway. Configure it only after
registration/linking is complete:

- `SIGNAL_REST_API_URL`
- `SIGNAL_PRIVATE_NETWORK`, default `freyja-signal-atlas_signal-private`
- `SIGNAL_ACCOUNT_NUMBER`
- `SIGNAL_ALLOWED_SENDERS`
- `SIGNAL_IDENTITY_MAP`, for example `+15555550100:beth`

An empty allowlist is deny-all.
The Signal services join the existing `freyja-signal-atlas_signal-private`
network so `http://signal-api:8080` remains private.

Validate without sending:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile operator run --rm signal-dry-run
```

The dry-run report is written to `/state/signal-dry-run.json`, backed by
`data/freyja-channels` by default.

Enable Signal receive/send only after dry-run readiness is true:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile signal up -d --build signal-pilot
```

## Persistence and Audit

The `data/freyja-channels` state directory stores thread mappings and audit
records. The service hashes senders in state and audit data and does not log raw
sender IDs or message bodies.
