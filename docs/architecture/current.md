# Current Freyja Architecture

The active Freyja system is a single local agent platform, not a set of
separate numbered products.

- **LibreChat on Atlas** is the named-agent web home.
- **Vulcan Nexus** selects and serves local models.
- **Iris Freyja Core** owns tool policy, MacAgent, Apple capabilities, Home
  Assistant access, OpenCode control, and explicit shared-memory writes.
- **Director** owns messaging-channel identity and delivery policy. It does not
  compose portal-model responses.
- **Agent Smith** is the bounded Freyja hardware watchdog. It is separate from
  the household/personal agent roster.

The canonical identity and boundary definition is
[`freyja.md`](freyja.md). The corresponding deployable LibreChat profile
manifest is [`config/librechat-family-agents.yaml`](../../config/librechat-family-agents.yaml).

Older validation stacks and their evidence live under `archive/`. They are
preserved for recovery and history but are not operational architecture.
