# Identity Backup and Restore

Identity databases contain private contact data. Backups must remain outside
git on an encrypted volume with restricted filesystem access.

```bash
freyja-identity-backup backup \
  ~/.local/state/freyja/identity.sqlite3 \
  /private/backups/freyja-identity.sqlite3

freyja-identity-backup verify /private/backups/freyja-identity.sqlite3
```

Backup uses SQLite's consistent backup API, runs an integrity and schema check,
sets the database and checksum manifest to mode `0600`, and records a SHA-256
checksum without exporting contact contents into the manifest.

Restore to a new path first:

```bash
freyja-identity-backup restore \
  /private/backups/freyja-identity.sqlite3 \
  /private/restore-test/identity.sqlite3
```

Replacing an existing database requires `--replace` and automatically creates a
verified pre-restore rollback backup. Stop services before replacing live state.
No backup created by this tool is encrypted independently; rely on FileVault or
an approved encrypted backup destination.
