# Open WebUI Home-Agent Readiness Summary

Status: `pending_external_auth_or_credentials`

## Gates

- `post_auth_activation`: ready - Open WebUI resource/access activation
  Command: `scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json`
- `authenticated_chat_smoke`: ready - Five-agent authenticated Open WebUI chat smoke
  Command: `OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py --output certification/reports/open-webui-home-agent-chat-smoke.json`
- `telegram_pilot`: pending - Telegram Joe pilot round trip
  Next: Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
  Action: Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
  Command: `scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json`
- `signal_pilot`: pending - Signal round trip
  Next: Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
  Action: Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
  Action: Send a message from an allowed Signal sender and archive a report with handled > 0.
  Command: `scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json`

## Exact Next Action

Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.


## Required Next Actions

- Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
- Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
- Send a message from an allowed Signal sender and archive a report with handled > 0.
