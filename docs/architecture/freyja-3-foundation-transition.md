# Freyja Foundation Transition

This note documents the small Freyja foundation layer added alongside the
existing Rev 1 Director-centered system.

## Scope

The transition layer defines explicit models and fixtures for:

- machines
- persistent agents
- security domains
- memory scopes and classification metadata
- inference endpoints
- gateway handoffs
- audit events

It also adds an `AgentGateway` skeleton that authenticates a sender, resolves an
explicitly named target agent, resolves a conversation, checks top-level domain
permissions, creates a handoff, and emits audit data.

The `InferenceRegistryV3` skeleton performs capability and security-domain based
endpoint lookup only.

## Non-Goals

This layer is not a replacement Director. It does not remove, rename, or bypass
the existing Rev 1 Director or router endpoints.

The gateway does not classify intent, choose tools, select task strategy, or plan
work. The inference registry does not select agents or decide what a user means.
Those concerns remain outside this foundation pass.

## Migration Direction

The next step is to wire the gateway behind an opt-in internal adapter path and
persist audit events, while keeping existing Rev 1 connector and router behavior
unchanged until parity is proven.
