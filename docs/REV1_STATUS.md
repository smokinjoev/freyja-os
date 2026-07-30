# Rev 1 Status

**Date:** 2026-07-30
**Status:** architecture and deployment layout aligned; staged rollout in progress

## Authoritative host roles

- Mars: Freyja Director and control plane.
- Atlas: always-on infrastructure services and Signal connector.
- Iris: local LLM inference; inference-focused.
- Hera: development, testing, and inference benchmarking; not core Freyja infrastructure.

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
- Iris is documented as the preferred local Ollama inference host.
- Hera is documented as the development and benchmark machine, separate from
  the core Freyja control path.

## Blockers before deployment

- Deploy the split Mars Director stack on its private Tailscale address and
  verify that Atlas can reach its health endpoint.
- Set the same strong `FREYJA_CONNECTOR_TOKEN` on Mars and Atlas.
- Register or link the Signal account manually in the Atlas REST wrapper state
  volume.
- Review and set `SIGNAL_ACCOUNT_NUMBER` and `SIGNAL_ALLOWED_SENDERS`.
- Keep populated `.env` files untracked and mode `0600`.

## Deployment order

1. On Iris, validate Ollama model availability and record the private endpoint
   Mars should use.
2. On Mars, configure and verify the Freyja Director against Iris Ollama and
   OpenRouter fallback.
3. From Atlas, verify private-network reachability to the Mars Director health
   endpoint.
4. On Atlas, create `deploy/compose/signal/.env` from the example and populate
   `FREYJA_DIRECTOR_URL`.
5. On Atlas, validate the Signal Compose config.
6. Manually register or link the Signal account in the REST wrapper.
7. Set the Signal account number and sender allowlist.
8. Enable Signal and start the Atlas Signal connector stack.
9. Send an authorized Signal message and confirm the request is routed to the
   Mars Director and then to Iris Ollama or OpenRouter according to policy.
