# Freyja Operations TODO

## Agent Roles

- [ ] Treat `freyja` as the family/household agent and shared issue-review coordinator.
- [ ] Treat `cloyd-gibbler` as Joe's private personal agent.
- [ ] Treat `benedict` as Beth's private personal agent.
- [ ] Keep `smith` as the maintenance agent: read-only diagnostics by default, writes only through approval gates.
- [ ] Keep private memories, accounts, and connector credentials scoped to each person's primary agent.
- [ ] Use Freyja for household status, shared home commands, family calendar views, and `/agents/family/issue-review`.

## Iris Account Migration

- [ ] Log in directly as the `freyja` macOS account on Iris.
- [ ] Promote `freyja` to macOS admin.
- [ ] Verify `freyja` can unlock admin prompts without Joe's account.
- [ ] Move Freyja-OS repo checkout, `.env` files, service state, logs, and runtime data under `freyja` ownership.
- [ ] Move or recreate SSH keys, deploy keys, and GitHub access needed for Freyja maintenance.
- [ ] Confirm Tailscale is logged in and reachable from the `freyja` account context.
- [ ] Confirm Ollama runs under the intended service/user context and can serve `qwen2.5:7b`.
- [ ] Confirm `qwen2.5:7b` warms with `keep_alive=-1` and remains resident.
- [ ] Reinstall or move LaunchAgents/services so they do not depend on Joe's home directory or keychain.
- [ ] Reboot Iris and verify Freyja services, Ollama, Tailscale, and local health checks recover automatically.

## Remove Joe Personal Data From Iris

- [ ] Back up Joe's user account data before destructive changes.
- [ ] Sign Joe out of iCloud, Messages, Mail, Calendar, Contacts, Safari, and browser profiles on Iris.
- [ ] Remove saved passwords, tokens, personal browser sessions, and account caches from Iris.
- [ ] Verify Freyja connectors no longer depend on Joe's personal keychain.
- [ ] Delete or archive Joe's local macOS account only after the `freyja` account passes reboot validation.

## Iris Admin Role

- [ ] Treat Iris as `host:iris` / `service:iris`, not `person:joe`.
- [ ] Keep Atlas Director authoritative for routing, tool authorization, and personal-data grants.
- [ ] Give Iris admin capability only for infrastructure operations: service restart, health inspection, model warmup, and local runtime maintenance.
- [ ] Keep the Iris 7B router in shadow mode until promotion criteria are met.
- [ ] Do not give Iris personal-data authority by default.

## Odin Linux Heavy Inference Node

- [ ] Install Linux on the new PC and give it the stable hostname `odin`.
- [ ] Join the tailnet and restrict inference endpoints to private network access.
- [ ] Install GPU drivers, container runtime if needed, and Ollama or the selected inference server.
- [ ] Install the heavy reasoning model and confirm it can remain resident if RAM/VRAM allows.
- [ ] Add health, tags/models, warmup, and residency checks equivalent to Iris.
- [ ] Configure Atlas `OLLAMA_REASONING_BASE_URL` to Odin's private Ollama endpoint.
- [ ] Verify Atlas `/local-reasoning/health` and `/local-reasoning/warm`.
- [ ] Confirm complex internal work routes to Odin through the `local_reasoning` provider.
- [ ] Keep private/sensitive prompts internal; never fall back to cloud for private data.
- [ ] Run router tests and certification gauntlets after Atlas can reach the node.

## Deployment Checks

- [ ] Validate Atlas Director compose config before restart.
- [ ] Restart only the Director service unless another service truly changed.
- [ ] Verify `/health` and `/iris-router/health`.
- [ ] Run Iris shadow smoke and standard gauntlets.
- [ ] Record disagreement patterns, especially under-routing.

## Communications Rollout

- [ ] Configure `GMAIL_IDENTITY` with Freyja's existing Gmail address.
- [ ] Configure `GMAIL_ALLOWED_SENDERS` with only approved work/corporate senders.
- [ ] Configure Gmail IMAP/SMTP transport credentials for Freyja's Gmail mailbox.
- [ ] Install and load `com.freyja-os.gmail-connector` with `scripts/install-gmail-connector.sh`.
- [ ] Confirm LaunchAgent state with `scripts/status-gmail-connector.sh`.
- [ ] Confirm `logs/gmail-connector.log` reports `Gmail connector started`.
- [ ] Smoke test an allowlisted Gmail message and confirm the reply stays in the same Gmail thread.
- [ ] Smoke test Gmail HTML input and confirm scripts, styles, remote images, and tracking URLs are not forwarded to Director.
- [ ] Confirm Gmail-originated consequential actions require approval through a trusted non-Gmail channel.
- [ ] Configure `IMESSAGE_FAMILY_CHAT_IDENTIFIERS` for the authorized family group only.
- [ ] Add Freyja's Apple identity to the family iMessage group from the `freyja` macOS account.
- [ ] Smoke test passive family iMessage observation and confirm no group reply is generated.
- [ ] Smoke test `Freyja, ...` and `@Freyja ...` invocations and confirm addressed messages route through Director.
- [ ] Review extracted family memory candidates before treating them as authoritative or calendar-worthy.
