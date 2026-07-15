# Milestone 18 Operator Test Runbook

This runbook describes the exact procedure for a single controlled local
operator test of the Agent Smith write-pilot approval transport. The default
system state remains disabled; the test must be enabled only for the duration
of the pilot and disabled immediately afterward.

## Target

Exactly one file:

```text
docs/smith-pilot/operator-test.md
```

With content similar to:

```markdown
# Agent Smith Operator Pilot

This file was created through the approved-write pilot.

Request ID: <request-id>
```

## Prerequisites

* You are the `freyja` user on the local machine.
* Freyja Director is installed and running on `http://127.0.0.1:8000`.
* The working tree is clean and the repository is on `main`.
* No unrelated files are staged or untracked.
* `scripts/enable-smith-write-pilot-test.sh` and
  `scripts/disable-smith-write-pilot-test.sh` exist and are executable.

## 1. Preflight checks

```bash
cd /Users/freyja/freyja-os

whoami                         # must be freyja
git status --short             # must be empty
git log -1 --oneline           # confirm expected baseline

# Confirm health
curl -s http://127.0.0.1:8000/health

# Confirm Smith is currently disabled
curl -s -o /dev/null -w "%{http_code}" -X POST \
  http://127.0.0.1:8000/agents/smith/write-pilot \
  -H "Content-Type: application/json" \
  -d '{"objective":"test"}'
# Expected: 404
```

## 2. Create the proposed-content source file outside the repository

```bash
PROPOSED_CONTENT="/Users/freyja/.local/state/freyja/smith-operator/operator-test-content.md"
mkdir -p "$(dirname "$PROPOSED_CONTENT")"
cat > "$PROPOSED_CONTENT" <<'EOF'
# Agent Smith Operator Pilot

This file was created through the approved-write pilot.

Request ID: __REQUEST_ID__
EOF
chmod 0600 "$PROPOSED_CONTENT"
```

Do not place this file inside the Freyja-OS repository.

## 3. Enable write-pilot test mode

```bash
cd /Users/freyja/freyja-os
./scripts/enable-smith-write-pilot-test.sh
```

This script:

* backs up `.env` under `~/.local/state/freyja/backups/`;
* sets `AGENT_SMITH_ENABLED=true`;
* sets `AGENT_SMITH_WRITE_PILOT_ENABLED=true`;
* keeps `AGENT_SMITH_READ_ONLY_ENABLED=false` and
  `AGENT_SMITH_DRY_RUN_ENABLED=false`;
* verifies `.env` mode `0600`;
* restarts Director;
* verifies the write-pilot endpoint returns `200` and read-only/dry-run return
  `403`/`404`.

## 4. Start the pilot

```bash
scripts/smith-approval run-pilot \
  --content-file "$PROPOSED_CONTENT" \
  --commit-message "docs: add operator pilot note" \
  --actor "operator-$(whoami)" \
  --repo-root /Users/freyja/freyja-os
```

The CLI will:

1. start the write-pilot request;
2. display the pending path approval;
3. require explicit `APPROVE` input;
4. submit the approval;
5. resume the run;
6. repeat for content, staging, and commit gates.

At every gate you may abort by typing anything other than `APPROVE`.

## 5. Gate-by-gate review

### Path approval

Confirm:

* target path is `docs/smith-pilot/operator-test.md`;
* no other path is mentioned.

### Content approval

Confirm:

* content SHA-256 matches the source file;
* the complete content is not printed by the CLI.

### Staging approval

Before staging the CLI runs:

```bash
git status --short
git diff --check -- docs/smith-pilot/operator-test.md
git diff --stat -- docs/smith-pilot/operator-test.md
```

Confirm:

* only `docs/smith-pilot/operator-test.md` changed;
* `git diff --check` passes;
* no unrelated tracked, staged, or untracked files appeared.

### Commit approval

The CLI prints:

```text
WARNING: This approval will create a local Git commit. It will not push.
```

It shows:

* exact staged file list;
* `git diff --cached --stat -- docs/smith-pilot/operator-test.md`;
* the commit message.

Confirm all of the above before approving.

## 6. Verify the result

After the CLI reports completion:

```bash
cd /Users/freyja/freyja-os

# Confirm only the approved file changed
git status --short
# Expected: nothing (clean working tree after commit)

# Confirm the file content
cat docs/smith-pilot/operator-test.md

# Confirm the commit
git log -1 --stat

# Confirm the commit contains exactly one file
git diff-tree --no-commit-id --name-only -r HEAD
# Expected: docs/smith-pilot/operator-test.md

# Confirm no push occurred
git status --short --branch
# Expected: no [ahead N] marker
```

## 7. Disable write-pilot test mode

```bash
cd /Users/freyja/freyja-os
./scripts/disable-smith-write-pilot-test.sh
```

This script:

* backs up `.env` again;
* sets `AGENT_SMITH_ENABLED=false`;
* sets `AGENT_SMITH_WRITE_PILOT_ENABLED=false`;
* sets `AGENT_SMITH_READ_ONLY_ENABLED=false`;
* sets `AGENT_SMITH_DRY_RUN_ENABLED=false`;
* restarts Director;
* verifies all Smith endpoints return `404`.

## 8. Final verification

```bash
cd /Users/freyja/freyja-os

# Confirm disabled state
curl -s -o /dev/null -w "%{http_code}" -X POST \
  http://127.0.0.1:8000/agents/smith/write-pilot \
  -H "Content-Type: application/json" \
  -d '{"objective":"test"}'
# Expected: 404

# Confirm .env was restored
git diff -- .env
# Expected: empty

# Confirm working tree clean except for the one new commit
git status --short
# Expected: empty
```

## Abort procedures

### Abort before path approval

* Do not type `APPROVE`.
* The CLI exits.
* Disable test mode:
  `./scripts/disable-smith-write-pilot-test.sh`.
* No repository change occurred.

### Abort before content approval

* Do not type `APPROVE`.
* The CLI exits.
* Disable test mode.
* No file was written.

### Abort before staging approval

* Do not type `APPROVE`.
* The CLI exits.
* The file was written but not staged.
* Review `git diff -- docs/smith-pilot/operator-test.md`.
* If desired, remove the file and restore the working tree, then disable test mode.

### Abort before commit approval

* Answer `N` at the commit prompt.
* The CLI exits.
* The file is staged but not committed.
* To unstage:
  `git restore --staged -- docs/smith-pilot/operator-test.md`
* To remove the file:
  `git checkout -- docs/smith-pilot/operator-test.md` and
  `rm docs/smith-pilot/operator-test.md`
* Disable test mode.

### Rollback after commit

If the commit must be undone after the fact:

```bash
git revert HEAD --no-edit
```

This creates a new commit that reverses the change. Do not rewrite published
history; in this local-only pilot no push has occurred.

## Cleanup

After the test:

```bash
rm -f /Users/freyja/.local/state/freyja/smith-operator/operator-test-content.md
# Optionally archive the operator state file for audit purposes.
```

## Safety reminders

* Never run the activation script unattended.
* Never approve a gate without reviewing the displayed fields.
* Never push the commit produced by the pilot.
* Never leave test mode enabled after the pilot.
* Never place the proposed-content source file inside the repository.
