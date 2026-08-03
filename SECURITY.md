# Freyja-OS Security

## Contact data

Contact import files and identity SQLite databases are private runtime state.
They are ignored by git and should live in a user-restricted state directory on
an encrypted volume. The local SQLite provider does not itself encrypt data.
Never commit populated contact files or databases.
