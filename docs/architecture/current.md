# Current Freyja Architecture

**Status:** architecture-first baseline, updated 2026-08-25.

Freyja's current architecture is Atlas as control plane, Vulcan as cognitive
runtime, and Iris as Apple bridge. Older Jarvis, Cortex, Sentinel, and
Iris-as-brain language is historical where it conflicts with this baseline.

## Machine Roles

- Atlas owns Director, identity, memory policy, tool authorization, connector
  coordination, health, deployment state, and durable service configuration.
- Vulcan owns inference. Atlas requests logical model profiles: `fast`,
  `reason`, `code`, and `vision`.
- Iris owns macOS and Apple-native capabilities: iMessage, Apple Calendar,
  Contacts, Shortcuts, and related bridge work.
- Hera is a presence/interface node and must use the same Atlas ingress path.
- Cloyd is a personal-agent identity, not the Raspberry Pi itself.

## Implemented Compatibility Layer

The repository still contains older provider names because deployment scripts,
tests, and certification artifacts depend on them. They now map to logical
profiles:

| Logical profile | Compatibility provider | Purpose |
| --- | --- | --- |
| `fast` | `legacy_ollama` | low-latency chat/classification compatibility |
| `reason` | `heavy_local` / `local_reasoning` | Vulcan reasoning profile |
| `code` | `qwen_coding` | bounded coding profile |
| `vision` | `local_vision` | image/document-adjacent vision profile |

New code should use profile semantics rather than choosing physical model names
directly. Existing provider names remain acceptable only as compatibility
surface until callers are migrated.

## Channel Boundary State

`POST /canonical/route` is the canonical Director ingress endpoint. Gmail,
Signal, iMessage, and Telegram now use it directly. `POST /route` remains
available for compatibility scripts, local smoke tools, and older callers
during rollout.

## Stale Documentation

`ARCHITECTURE.md` Rev 2 describes Iris as a hot reflex/router node and permits
simple conversational use. Treat that as stale for any request requiring
intelligence. Iris may bridge Apple capabilities and provide explicitly
observable advisory classification only when Atlas remains authoritative. It
must not silently answer as a connector-local brain.

## External Gaps

The current completion audit reports iMessage evidence as passing and Signal
live smoke as externally blocked by account/service setup. Signal code may be
complete while live certification remains blocked.
