# Identity-to-Memory Migration

This migration converts legacy platform-scoped shared-memory subjects to a
canonical `Person` subject. Canonical family-member subjects share recall across
Signal, iMessage, and other trusted connectors; anonymous platform subjects
remain isolated.

Use synthetic or copied databases first. Never run an unreviewed migration on a
live production database.

## Dry run

```bash
freyja-memory-identity-migrate \
  --memory-database /private/copy/freyja.db \
  --identity-database /private/copy/identity.sqlite3
```

The report contains counts only and does not expose raw identifiers. Any
ambiguous identity mapping or target memory-ID collision makes the report unsafe
to apply.

## Apply

```bash
freyja-memory-identity-migrate \
  --memory-database /private/copy/freyja.db \
  --identity-database /private/copy/identity.sqlite3 \
  --backup /private/copy/freyja.pre-identity-migration.sqlite3 \
  --apply
```

Apply creates a consistent SQLite backup before beginning a transaction.
Failures roll back the transaction. Re-running after success is idempotent.
Timestamps, content, source, conversation IDs, and existing metadata remain
unchanged; migration provenance is appended to metadata.

## Verification and rollback

Run the command again without `--apply`; `migratable` should be zero. Verify
with `--verify` for a non-zero exit status when further migration or conflicts
remain. Backup files are created with mode `0600`.
Verify
recall through synthetic Signal and iMessage principals for the same canonical
person. To roll back while services are stopped, replace the migrated database
with the backup.
