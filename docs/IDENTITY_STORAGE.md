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

### Apple Contacts on Freyja's Mac

The preferred Mac path reads Freyja's Contacts database through Apple's native
Contacts framework. It does not require MacAgent. First validate the available
records and review only the aggregate count:

```bash
freyja-identity-import-apple --dry-run
```

The importer never triggers the initial macOS permission dialog implicitly. If
access has not been decided, explicitly authorize that one prompt and perform a
dry run with `freyja-identity-import-apple --dry-run --request-access`. Later
imports do not need `--request-access` once access has been granted.
After backing up an existing identity database, replace it intentionally:

```bash
freyja-identity-backup backup ~/.local/state/freyja/identity.sqlite3 \
  ~/.local/state/freyja/identity-backup.sqlite3
freyja-identity-import-apple --replace \
  --database ~/.local/state/freyja/identity.sqlite3
```

The native helper sends contact data only through a local process pipe. The CLI
prints aggregate counts, not names, addresses, phone numbers, or native contact
identifiers. Native identifiers are stored only as domain-separated SHA-256
digests so imports remain stable without retaining the source identifier or a
general-purpose hash that can be correlated with unrelated datasets.

### vCard fallback

If native access is unavailable, export a `.vcf` file to a private path outside
the repository and validate it without writing:

```bash
freyja-identity-import-vcard /private/path/contacts.vcf --dry-run
```

Then back up and import the reviewed file:

```bash
freyja-identity-backup backup ~/.local/state/freyja/identity.sqlite3 \
  ~/.local/state/freyja/identity-backup.sqlite3
freyja-identity-import-vcard /private/path/contacts.vcf \
  --replace \
  --database ~/.local/state/freyja/identity.sqlite3
```

### JSON fallback

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
- Native Apple import is read-only from Contacts; it does not edit or synchronize
  any Apple, Google, Yahoo, or local Contacts account.
- Keep `.vcf` exports private. They are ignored by this repository but remain
  sensitive plaintext files on disk.
