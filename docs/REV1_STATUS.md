# Rev 1 Status

**Date:** 2026-07-30
**Status:** architecture and deployment layout aligned; Mars/Hera local reasoning deployed

## Authoritative host roles

- Mars: Freyja Director and control plane.
- Atlas: always-on infrastructure services and Signal connector.
- Hera: primary complex local_reasoning provider over Tailscale; not core
  always-on infrastructure.
- Iris: fast local inference tier; inference-focused.

## Conflicting or stale assignments found

- `README.md` assigned the Director to Iris and later described Mars as hosting
  both the Director and Signal connector.
- `deploy/compose/signal/README.md` described a combined Mars control-plane
  stack with `director`, `signal-api`, and `signal-connector`.
- `deploy/compose/signal/.env.example` described Mars control-plane settings
  and included Director/Ollama/OpenRouter variables in the Signal connector
  deployment example.
- `deploy/compose/signal/compose.yaml` defined a combined stack that ran the
  Director next to the Signal connector.
- `ARCHITECTURE.md` described the unnamed Mac mini as the Director node and did
  not capture the Mars/Atlas/Iris/Hera Rev 1 role split.
- `docs/telegram/milestone-20-travel-mode.md` referred to a future
  `Hera/Atlas` transport, which conflicted with Hera's separate benchmark role.
- `ROADMAP.md` used generic host language for the Signal bridge and Mac mini
  inference validation instead of the Rev 1 host names.

## Current status

- Mars is the documented Director/control-plane host.
- Atlas is the documented host for always-on infrastructure and the Signal
  connector.
- The Signal Compose stack is documented as an Atlas stack and no longer
  defines a local Director service.
- A separate Mars Director Compose project preserves repeatable control-plane
  deployment.
- Hera is documented and deployed as the primary complex local_reasoning
  provider for the Mars Director.
- Iris is documented as the fast local inference tier.
- Hera remains separate from the core always-on control path; Director routing
  must tolerate Hera being unavailable.
- OpenRouter fallback requires configured credentials, approved models, and
  routing budget headroom.

## Blockers before deployment

- Set the same strong `FREYJA_CONNECTOR_TOKEN` on Mars and Atlas.
- Register or link the Signal account manually in the Atlas REST wrapper state
  volume.
- Review and set `SIGNAL_ACCOUNT_NUMBER` and `SIGNAL_ALLOWED_SENDERS`.
- Keep populated `.env` files untracked and mode `0600`.

## Deployment order

1. On Hera, validate `gpt-oss:20b` model availability and expose Ollama only on
   localhost plus a private Tailscale path to Mars.
2. On Mars, configure and verify the Freyja Director against Hera
   `local_reasoning` and the configured fast local inference tier.
3. Configure OpenRouter fallback credentials and allowlist if cloud fallback is
   required.
4. From Atlas, verify private-network reachability to the Mars Director health
   endpoint.
5. On Atlas, create `deploy/compose/signal/.env` from the example and populate
   `FREYJA_DIRECTOR_URL`.
6. On Atlas, validate the Signal Compose config.
7. Manually register or link the Signal account in the REST wrapper.
8. Set the Signal account number and sender allowlist.
9. Enable Signal and start the Atlas Signal connector stack.
10. Send an authorized Signal message and confirm the request is routed to the
   Mars Director and then to Hera, Iris, or OpenRouter according to policy and
   availability.
