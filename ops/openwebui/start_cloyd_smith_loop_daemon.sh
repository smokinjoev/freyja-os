#!/usr/bin/env sh
set -eu

cat >&2 <<'EOF'
The OpenWebUI container JSON-ledger Cloyd-Smith daemon is deprecated.

Use the canonical local SQLite loop instead:

  scripts/install-cloyd-smith-loop-launchagent.sh
  scripts/status-cloyd-smith-loop.sh
  scripts/cloyd-smith-loop-daemon.py --status

Canonical ledger:
  ~/.local/state/freyja/cloyd-smith-loop.db
EOF
exit 2
