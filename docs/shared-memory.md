# Shared Memory

Freyja Director stores conversation history and shared memory in the configured
SQLite database. The Director container uses `/app/data/freyja.db`, backed by
the host `data/` bind mount, so memory survives container recreation when the
deployment keeps that directory.

Shared memory is scoped by a server-side principal:

- `client_type`
- `client_subject`
- optional `account_owner`
- optional `conversation_id`

Connectors derive those values only after their own authentication and sender
allowlist checks. Request JSON, tool arguments, and model output are not trusted
sources for memory scope. Signal and native iMessage use stable hashed sender
and conversation identifiers; display names are never security identities.

All shared-memory list, read, update, and delete operations include the
authenticated principal. Missing or cross-principal items return the same
generic not-found response so callers cannot enumerate another scope.

Recalled shared memory is included only in local-provider prompts by default.
It is delimited as untrusted quoted data, capped by item count, item size, and
total injected characters, and instruction-like stored content is neutralized.
Cloud prompt recall requires the explicit `MEMORY_RECALL_INCLUDE_IN_CLOUD=true`
policy setting.
