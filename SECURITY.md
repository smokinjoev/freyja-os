# Freyja-OS Security

## Contact data

Contact import files and identity SQLite databases are private runtime state.
They are ignored by git and should live in a user-restricted state directory on
an encrypted volume. The local SQLite provider does not itself encrypt data.
Never commit populated contact files or databases.

Memory-principal migrations must run against stopped services or private copies,
create a consistent backup before writing, and refuse ambiguous identity matches
or memory-ID collisions. Migration reports must not print raw contact values.
