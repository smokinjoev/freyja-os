# Family Discord Agents

Discord uses the canonical Freyja identities; it does not create a separate
agent roster. The approved identities are Freyja, Cloyd, Benedict, Agent 47,
JennaCide, and Agent Smith.

Freyja and Cloyd are the only live Discord DM connectors today. Each connector
runs on Iris and carries its resolved identity to Director. Cloyd's read-only
OpenCode status action passes through Iris Core at `/mcp/cloyd-gibbler`; other
Director capabilities remain explicitly governed by Director's agent policy.
The full operating procedure is
in [`docs/discord/family-discord-runbook.md`](../discord/family-discord-runbook.md).

Before enabling another identity, choose its owner, conversation scope, and
permitted tool posture. Store credentials in Iris's private runtime
environment with restrictive permissions; never add tokens to source control.

## Current Iris Discord runner

Freyja and Cloyd use the shared Python DM runner on Iris. It passes their
resolved identity to Director and uses the common Discord gateway rather than
per-bot forks. The active runner supports image, PDF, DOCX, and HEIC intake;
preserves recent media context for short follow-ups; and splits long replies
into Discord-safe messages. This capability is live only for Freyja and Cloyd.

Do not create additional agent bots or enable new Discord identities until an
owner, private credential, and scoped Core policy are approved.
