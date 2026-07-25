# Freyja-OS

Freyja-OS is a locally controlled personal-agent platform.

## Initial architecture

- Iris Mac mini: Freyja Director, OpenClaw, Ollama and OpenRouter routing
- Raspberry Pi: future persistent messaging and edge gateway
- Atlas or another infrastructure host: containers, databases and supporting services
- Additional computers: optional worker nodes

## Current phase

Phase 1: repository foundation and Director skeleton.

## Signal connector

Atlas is the always-on host for the Signal connector deployment. The
deployment uses
[`bbernhard/signal-cli-rest-api`](https://github.com/bbernhard/signal-cli-rest-api)
in `native` mode: a transport adapter polls its receive endpoint, normalizes
supported messages, passes them to `SignalGateway`, and sends the resulting
responses through the REST wrapper. Transport code does not make authorization
or group-policy decisions. The gateway continues to enforce sender allowlists,
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

For the Atlas Compose layout, environment-file instructions, private networking,
and configuration validation, see
[`deploy/compose/signal/README.md`](deploy/compose/signal/README.md). The Signal
REST API has no public port in that deployment and is reachable only on its
private Docker network.
