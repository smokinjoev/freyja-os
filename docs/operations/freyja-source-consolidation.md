# Freyja Source Consolidation

The shared integration branch, `codex/freyja-consolidation`, is the reviewed
source for changes that have passed the repository test suite.  Promotion to
`main` remains an explicit review step; no host should treat an unreviewed
working tree as the shared baseline.

## Current host boundary

| Host | Runtime source | State | Migration rule |
| --- | --- | --- | --- |
| Atlas | `/home/joe/freyja-os` | Canonical checkout, deployed through the Director and Signal compose projects | Update only by fast-forwarding the consolidation branch, rebuilding affected services, and checking health plus runtime-data mounts. |
| Iris | `/Users/freyja/freyja-os-canonical-staging` for MacAgent; `/Users/freyja/freyja-os` for Director and iMessage | MacAgent runs the clean canonical staging checkout; the remaining active services use the preserved dirty overlay | Preserve and review the overlay before redirecting each remaining LaunchAgent. Keep the canonical staging checkout clean and validate authenticated MacAgent health after every service change. |
| Vulcan | `/home/joe/freyja-os-consolidation` | Active Paralegal Director runs the clean canonical checkout | Update only after focused and full-suite validation, then restart the systemd user service and check its health. The prior dirty Paralegal checkout is retained in a dated recovery location. |

## Host-specific overlays

Host-specific configuration belongs outside the shared checkout: service unit
files, LaunchAgent environment files, runtime data, credentials, and machine
paths.  Code may move into the canonical branch only with focused tests and a
clear owner.  In particular, the Iris OpenWebUI-to-Apple bridge must not be
promoted as generic code while it contains deployment-specific authenticated
identity mappings or SSH transport assumptions.

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
