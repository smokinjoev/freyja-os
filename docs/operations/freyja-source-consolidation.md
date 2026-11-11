# Freyja Source Consolidation

`main` is the reviewed shared source for Freyja. The former
`codex/freyja-consolidation` branch is a historical integration record; its
reviewed slices were promoted to `main` individually. No host should treat an
unreviewed working tree as the shared baseline.

## Current host boundary

| Host | Runtime source | State | Migration rule |
| --- | --- | --- | --- |
| Atlas | `/home/joe/freyja-os` | Canonical checkout, deployed through the Director and Signal compose projects | Update from reviewed `main`, rebuild affected services, and check health plus runtime-data mounts. |
| Iris | `/Users/freyja/freyja-os-canonical-staging` | MacAgent, the iMessage runtime manifest, Director, OpenAI-compatible API, Cloyd/Smith workers, Core-MCP, and both Discord DM connectors run canonical staging | Keep the canonical staging checkout clean, validate authenticated MacAgent and Director health, require zero iMessage manifest drift plus a single managed connector, and check Core-MCP and both Discord workers after every service change. The former dirty checkout is retained only as a dated recovery archive. |
| Vulcan | `/home/joe/freyja-os-consolidation` | Active Paralegal Director runs the clean canonical checkout | Update from reviewed `main` after focused and full-suite validation, then restart the systemd user service and check its health. The prior dirty Paralegal checkout is retained in a dated recovery location. |

## Host-specific overlays

Host-specific configuration belongs outside the shared checkout: service unit
files, LaunchAgent environment files, runtime data, credentials, and machine
paths.  Code may move into the canonical branch only with focused tests and a
clear owner.  In particular, the Iris OpenWebUI-to-Apple bridge must not be
promoted as generic code while it contains deployment-specific authenticated
identity mappings or SSH transport assumptions.

## Iris migration record

The canonical staging migration includes the Core-MCP server and both Discord
DM connectors.  Their LaunchAgent definitions and credentials are host
configuration: Core-MCP and the Freyja-specific Discord connector load their
private environment from external, owner-only files.  The checkout-relative
wrappers are tested in the shared branch, so the staged services no longer
depend on the legacy checkout path.  After the full Iris service audit passed,
the former dirty checkout and inactive legacy LaunchAgent stubs were moved to
dated recovery locations rather than deleted.

## Required migration gate

Before replacing a live overlay:

1. Inventory tracked and untracked changes, including the active service path.
2. Integrate or explicitly retain each unique capability with tests.
3. Create or verify a clean canonical checkout on the host.
4. Rebuild or restart only the affected service.
5. Verify service health, source/runtime-data mounts, and recent logs.
6. Rename the old checkout to a dated recovery location only after the new
   runtime is healthy.

This keeps one reviewed source of truth without losing machine-specific
capabilities during migration.
