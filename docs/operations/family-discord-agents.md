# Family Discord Agents

Discord uses the canonical Freyja identities; it does not create a separate
agent roster. The approved identities are Freyja, Cloyd, Benedict, Agent 47,
JennaCide, and Agent Smith.

Freyja and Cloyd are the only live Discord DM connectors today. Each connector
runs on Iris, carries its resolved identity to Director, and accesses tools
only through that identity's Iris Core policy. The full operating procedure is
in [`docs/discord/family-discord-runbook.md`](../discord/family-discord-runbook.md).

Before enabling another identity, choose its owner, conversation scope, and
permitted tool posture. Store credentials in Iris's private runtime
environment with restrictive permissions; never add tokens to source control.
