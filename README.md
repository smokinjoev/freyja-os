# Freyja-OS

Freyja-OS is a locally controlled personal-agent platform.

## Initial architecture

- Mars: Freyja Director and control plane
- Atlas: always-on infrastructure services and Signal connector
- Iris: local LLM inference; inference-focused
- Hera: development, testing, and inference benchmarking; not core Freyja infrastructure
- Raspberry Pi: future edge automation node
- Additional computers: optional worker nodes

## Current phase

Phase 1: repository foundation and Director skeleton.

## Rev 1 host roles

Mars is the Freyja Director and control-plane host. Atlas runs always-on
infrastructure services and the Signal connector. Iris is focused on local LLM
inference. Hera is the development, testing, and inference-benchmark machine,
not a required Freyja infrastructure host.

The Signal connector deployment uses
[`bbernhard/signal-cli-rest-api`](https://github.com/bbernhard/signal-cli-rest-api)
in `native` mode on Atlas: a transport adapter polls its receive endpoint,
normalizes supported messages, passes them to `SignalGateway`, forwards
authorized requests to the Director on Mars, and sends the resulting responses
through the REST wrapper. Transport code does not make authorization or
group-policy decisions. The gateway continues to enforce sender allowlists,
reject groups, and suppress duplicates.

Copy the repository `.env.example` to `.env` for local execution, fill in only
local values, and restrict it to the owner:

```bash
cp .env.example .env
chmod 600 .env
source .venv/bin/activate
python scripts/run-signal-connector.py
```

The Signal account must already be registered or linked in the REST wrapper.
First-time registration or linking is a deliberate operator action; follow the
wrapper's upstream instructions from a trusted Atlas session and never commit
the resulting account data or phone numbers.

For the Atlas Signal connector Compose layout, environment-file instructions,
private networking, and validation, see
[`deploy/compose/signal/README.md`](deploy/compose/signal/README.md). The Signal
REST API has no public port in that deployment and is reachable only on its
private Docker network.
