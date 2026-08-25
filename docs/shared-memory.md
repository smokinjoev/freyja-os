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

## Provenance

Every shared-memory write is normalized with provenance metadata. Existing
callers can continue sending the older request shape; the Director derives a
trusted connector provenance record from the authenticated principal when no
explicit provenance is supplied.

The provenance record includes source type, source ID when available, trust
level, memory kind, observed timestamp, authoritative status, optional worker
observation details, and derivation links. It is stored inside the existing
metadata JSON so no schema migration is required.

External-content worker observations are not authoritative facts. If an
untrusted worker attempts to write authoritative shared memory, the Director
records it as a non-authoritative observation for later interpretation or user
confirmation.
