# Persistent Identity Storage

Freyja can load canonical people and relationships from a local, versioned
SQLite database. The database is runtime state and must not be committed.

## Configuration

The compatibility default remains the deterministic seeded household:

```text
IDENTITY_PROVIDER=seeded
```

To enable persistent storage, set:

```text
IDENTITY_PROVIDER=sqlite
IDENTITY_DATABASE_PATH=/Users/freyja/.local/state/freyja/identity.sqlite3
IDENTITY_SEED_FALLBACK=true
```

With fallback enabled, an empty database uses the development seed. Set it to
`false` after importing reviewed contacts if an empty store should stay empty.

## Private import

Copy `docs/examples/identity-contacts.example.json` to a private path outside
the repository, replace the placeholders, then validate it without writing:

```bash
freyja-identity-import /private/path/contacts.json --dry-run
```

Import transactionally after reviewing the counts:

```bash
freyja-identity-import /private/path/contacts.json \
  --database ~/.local/state/freyja/identity.sqlite3
```

The import replaces the database contents atomically. Duplicate person IDs,
duplicate channel identities, and relationships to unknown people are rejected
before writes. Back up an existing database before intentional replacement.

## Security

- Keep contact JSON and SQLite files outside git and restrict filesystem access.
- The database is not encrypted by Freyja; use FileVault and appropriate file
  permissions for this first local-only phase.
- Do not place Signal state, message databases, tokens, or credentials in the
  contact document.
- Google and Apple contact synchronization are not enabled by this feature.
