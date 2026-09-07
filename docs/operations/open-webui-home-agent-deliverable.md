# Open WebUI Home-Agent Deliverable

Status: `maximally_completed_pending_external_auth`
Verified completion: `86.7%` (13/15 requirements)

## Verification

- Focused tests: `133 passed, 1 warning`
- Full tests: `1582 passed, 1 skipped, 1 warning`
- Live verifier ok: `True`
- Backup rollback audit ok: `True`
- Secret safety audit ok: `True`
- Access metadata audit ok: `True`
- Resource export ok: `True`
- Channels deterministic: `True`
- Channels Atlas deployment ok: `True`
- Proactive all disabled: `True`
- Proactive dry-run suppressed: `True`
- Freyja 4.1 preservation ok: `True`
- Freyja 4.1 legacy endpoints ok: `True`
- Completion audit complete: `False`
- Post-auth activation ready: `False`
- Inference policy ok: `True`
- Authenticated chat smoke: `complete`
- Open WebUI tools gateway ok: `True`
- Open WebUI tools OpenAPI ok: `True`
- Readiness summary: `pending_external_auth_or_credentials`
- Readiness all ready: `False`

## Inference

- `coding`: `qwen3-coder-next:q4_K_M`
- `fast_chat`: `qwen2.5:32b-instruct`
- `strong_reasoning`: `qwen3:30b-a3b`
- `vision_documents`: `qwen2.5vl:72b`
- `agent_models_in_proxy_catalog`: `True`
- `cloud_fallback_disabled_for_open_webui_path`: `True`
- `large_model_guard_enabled`: `True`
- `model_profiles_complete`: `True`
- `model_profiles_local_only`: `True`
- `nexus_not_required`: `True`
- `open_webui_uses_model_proxy`: `True`
- `primary_vulcan_endpoint_configured`: `True`
- `unloads_other_primary_models`: `True`
- `vulcan_ollama_unload_endpoint_configured`: `True`

## Post-Auth Activation

- Ready: `False`
- Missing users: `beth, jenna, joe, liam`
- Missing models: ``
- Resource owner resolved: `False`
- Resource owner policy: `auto_single_user_only`

## Endpoints

- `open_webui_atlas`: `http://100.119.235.114:3001`
- `open_webui_tailnet`: `http://100.119.235.114:3001`
- `open_webui_iris_duplicate`: `http://100.115.228.56:3001`
- `freyja5_gateway_local`: `http://127.0.0.1:8500`
- `freyja_home_memory`: `http://127.0.0.1:8500/freyja-home-memory`
- `vulcan_openai`: `http://100.94.80.21:8088/v1`
- `vulcan_ollama`: `http://100.94.80.21:11434`
- `iris_fallback`: `http://100.115.228.56:11434/v1`

## Endpoint Ownership

- `atlas_freyja5_gateway`: container=freyja5-gateway-1, endpoint=http://127.0.0.1:8500, role=home memory and Open WebUI tool gateway host, status=Up 12 hours (healthy)
- `atlas_model_proxy`: container=freyja-open-webui-atlas-model-proxy-1, endpoint=http://model-proxy:8080/v1, role=Open WebUI to Freyja/Vulcan routing boundary, status=None
- `atlas_open_webui`: container=freyja-open-webui-atlas-open-webui-1, endpoint=http://100.119.235.114:3001, role=central multi-user agent/chat/permissions platform, status=None, tailnet_endpoint=http://100.119.235.114:3001
- `iris_apple_capabilities`: endpoint=http://100.115.228.56:11434/v1, fallback_only_for_inference=True, mcp_host=iris, role=Apple capability server for Calendar, Reminders, iMessage, Shortcuts, HomePod actions
- `vulcan_inference`: nexus_required=False, ollama_endpoint=http://100.94.80.21:11434, openai_endpoint=http://100.94.80.21:8088/v1, role=local inference through Ollama/OpenAI-compatible endpoints

## Agent Policy

- Agents: `agent-44, benedict, cloyd, freyja, jenna`
- Runtime models: `agent/agent-47, agent/benedict, agent/cloyd-gibbler, agent/freyja, agent/jennacide`
- Benedict: groups=`beth`, cloud_fallback=`forbidden`, knowledge=`personal:beth, restricted:benedict`, confirm_tools=`[]`
- Child `agent-44`: allow=`weather.read, calendar.read, pdf.analyze, image.analyze`, deny=`admin, messaging.send, home.device_action, cloud_fallback`, confirm=`[]`
- Child `jenna`: allow=`weather.read, calendar.read, pdf.analyze, image.analyze`, deny=`admin, messaging.send, home.device_action, cloud_fallback`, confirm=`[]`

## Memory

- Native Open WebUI memory: `per_user`
- `home_memory_operations_ok`: `True`
- `home_memory_joe_write_ok`: `True`
- `home_memory_joe_read_ok`: `True`
- `home_memory_recent_events_ok`: `True`
- `home_memory_beth_denied_joe_scope_ok`: `True`

## Tool Authorization

- Operation count: `20`
- `confirmation_required`: `calendar.create, forget, home.device_action, imessage.send.approved, reminders.create, shortcuts.run, update`
- `child_allowed_operations`: `image.analyze, pdf.analyze, recent-events, search, weather.read`
- `destructive_default_all_deny`: `True`
- `live_side_effects_invoked`: `False`
- Execution statuses: `{'confirmed_write': 'confirmed_not_configured', 'image_analysis': 'dry_run_available', 'pdf_analysis': 'dry_run_available', 'read_only': 'dry_run_available'}`

## Channel Safety

- `compose`: `deploy/compose/freyja-channels/compose.yaml`
- `env_example`: `deploy/compose/freyja-channels/.env.example`
- `atlas_deployment_ok`: `True`
- `deterministic_gateway_only`: `True`
- `model_routing_prohibited`: `True`
- `independent_agent_intelligence_prohibited`: `True`
- `telegram_empty_allowlist_policy`: `deny_all`
- `telegram_allowlist_count`: `0`
- `telegram_identity_map_count`: `0`
- `signal_empty_allowlist_policy`: `deny_all`
- `signal_allowlist_count`: `0`
- `signal_identity_map_count`: `0`
- `whatsapp_status`: `disabled`

## Proactive Safety

- Candidate schedules: `27`
- Ready schedules: `0`
- Job candidate counts: `{'calendar_conflict_warning': 6, 'reminder_followup': 12, 'scheduled_briefing': 6, 'system_health_notification': 3}`
- Blocked by job: `{'calendar_conflict_warning': 6, 'reminder_followup': 12, 'scheduled_briefing': 6, 'system_health_notification': 3}`
- Blocked reasons: `{'chat_not_stable': 27, 'destination_not_verified': 27, 'dry_run_required': 27, 'job_disabled': 27, 'recipient_not_verified': 27, 'schedule_not_approved': 27}`
- Enablement gate: `{'chat_stable': 'required', 'destinations_verified': 'required', 'dry_run_first': 'required', 'per_schedule_approval': 'required', 'recipients_verified': 'required'}`
- Prohibitions: `{'enable_globally_by_default': True, 'infer_unverified_destination': True, 'message_children_without_parent_policy': True, 'run_destructive_tools': True}`
- Dry-run would-send count: `0`
- Dry-run all sends suppressed: `True`

## Required Next Actions

- Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
- Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
- Send a message from an allowed Signal sender and archive a report with handled > 0.

## Rollback

- `source_checkpoint`: `.codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch`
- `source_status`: `.codex-checkpoints/pre-open-webui-home-agent-status-20260904T133828-0400.txt`
- `open_webui_volume_backup`: `logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz`
- `offline_model_db_backup`: `None`
- `runbook`: `docs/operations/open-webui-home-agent.md`
- `compose_file`: `{'exists': True, 'path': 'deploy/compose/open-webui/compose.yaml', 'readable': True}`
- `stop_open_webui`: `docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/compose.yaml down`
- `restore_source_checkpoint`: `git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch`
- `restore_open_webui_volume`: `tar -xzf logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz -C <restored-open-webui-data-volume>`
- `start_open_webui`: `docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/compose.yaml up -d`
- `verify_open_webui`: `curl -fsS --max-time 10 http://100.119.235.114:3001/api/version`

## Artifacts

- `readiness_summary`: `certification/reports/open-webui-home-agent-readiness-summary.json`

## Blockers

- Telegram pilot round trip needs bot token, allowlist, and identity map configured outside source control.
- Signal pilot round trip needs signal-cli-rest-api account, allowlist, identity map, and Open WebUI key access.

## External Gates

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

## Requirement Audit

- `preflight_inventory`: `complete`
- `open_webui_host_and_vulcan_path`: `complete`
- `open_webui_backup_and_rollback`: `complete`
- `git_checkpoint`: `complete`
- `secret_safety`: `complete`
- `local_inference`: `complete`
  Command: `OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py --output certification/reports/open-webui-home-agent-chat-smoke.json`
- `model_profiles`: `complete`
- `five_agents`: `complete`
  Command: `scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json`
- `memory_layers`: `complete`
  Command: `scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json`
- `tools`: `complete`
  Command: `scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json`
- `messaging_channels`: `credential_gated`
  Blocker: Telegram/Signal live round trip is not yet proven with handled > 0.
  Action: Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
  Action: Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
  Action: Send a message from an allowed Signal sender and archive a report with handled > 0.
  Command: `scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json`
  Command: `scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json`
- `proactive_behavior`: `complete`
- `verification`: `partial`
  Blocker: Telegram/Signal round trip remains pending.
  Next: Clear all external readiness gates, then rerun the completion audit.
  Action: Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
  Action: Verify the Signal account is registered and accepted by signal-cli-rest-api, then rerun the live Signal pilot.
  Action: Send a message from an allowed Signal sender and archive a report with handled > 0.
  Command: `scripts/summarize-open-webui-home-agent-readiness.py && scripts/audit-open-webui-home-agent-completion.py`
- `freyja41_preservation`: `complete`
- `final_deliverable`: `complete`

## Exact Next Action

Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0.
