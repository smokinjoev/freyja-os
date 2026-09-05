# Freyja Channels on Atlas

This Compose project runs the deterministic Open WebUI messaging gateway on
Atlas. It does not route models or contain independent agent intelligence. Each
message follows:

`Telegram/Signal sender -> verified family identity -> permitted agent -> Open WebUI API -> response`

Open WebUI remains the agent platform. Vulcan remains the local inference path
behind Open WebUI. WhatsApp stays disabled until a secured public webhook is
explicitly approved.

## Secrets

Copy `.env.example` to `.env`, set mode `0600`, and keep it uncommitted. The
preferred Open WebUI credential is the Atlas key file:

```bash
OPEN_WEBUI_API_KEY_HOST_FILE=/home/joe/.freyja/open-webui-api-key
OPEN_WEBUI_API_KEY_FILE=/run/secrets/open_webui_api_key
```

Do not put bot tokens, phone numbers, or API keys in source control.

## Telegram Pilot

Telegram is profile-gated and remains off until explicitly started. Configure:

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
- `SIGNAL_ACCOUNT_NUMBER`
- `SIGNAL_ALLOWED_SENDERS`
- `SIGNAL_IDENTITY_MAP`, for example `+15555550100:beth`

An empty allowlist is deny-all.

Validate without sending:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile operator run --rm signal-dry-run
```

Enable Signal receive/send only after dry-run readiness is true:

```bash
docker compose --env-file deploy/compose/freyja-channels/.env \
  -f deploy/compose/freyja-channels/compose.yaml \
  --profile signal up -d --build signal-pilot
```

## Persistence and Audit

The `freyja-channel-state` volume stores thread mappings and audit records. The
service hashes senders in state and audit data and does not log raw sender IDs
or message bodies.
