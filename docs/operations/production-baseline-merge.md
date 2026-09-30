# Production Baseline Merge Gate

Target: merge `feature/cloyd-upstream-features` into `main` only after these
conditions are met. This document prevents a documentation or reachability
pass from being mistaken for production certification.

## Current branch state (2026-09-29)

- `feature/cloyd-upstream-features` is ahead of `origin/main`, with no commits
  unique to `origin/main` at the time of review. Confirm the live count before
  merging with `git rev-list --left-right --count origin/main...HEAD` rather
  than relying on a stale number in this gate.
- The no-secret operational baseline passes with:

  ```sh
  python3 scripts/freyja-live-readiness.py
  ```

- Atlas portals, Vulcan Director/Nexus/Ollama, Iris Core, per-agent MCP
  initialization, the Agent Smith monitor, and both Discord connector
  processes have current live evidence.
- The focused portal configuration and agent-routing suite passes: `81 passed`
  (`tests/test_librechat_pass_through.py` and `tests/test_health.py`).
- A full local suite run currently reports `1856 passed, 32 failed, 6 skipped`.
  The failures are primarily legacy Open WebUI evidence expectations and
  macOS-specific launch-agent/tmux paths evaluated on Linux. They must be
  triaged, fixed, or formally separated from this release before a production
  merge; they are not evidence that the live portal path is certified.

## Required before merge

1. Complete every row in `docs/operations/freyja-live-acceptance.md` using an
   approved LibreChat account:
   - written response;
   - read-only Core MCP action;
   - isolated-memory check for Freyja, Cloyd, Benedict, Agent 47, and
     JennaCide;
   - bounded, non-destructive OpenCode handoff for Agent 47.
2. Choose and test Agent Smith's one-recipient alert route. The recommended
   initial route is Cloyd through the already-running Discord DM connector.
   Do not grant repair authority during this test.
3. Keep Signal and Telegram out of the production claim until one is explicitly
   configured and successfully certified. Signal currently has a failing
   receive loop; Telegram has no live connector.
4. Run the repository verification in the matching release environment:

   ```sh
   python -m compileall -q src connectors certification tests
   python -m pytest
   python3 scripts/freyja-live-readiness.py
   ```

   The full suite must pass, or every remaining failure must have an approved,
   documented exclusion with a matching-host verification plan.
5. Review the diff against `origin/main`, confirm no secret files are staged,
   and obtain the operator's explicit merge approval.

## Merge procedure

1. Fetch `origin/main` and re-run the checks above.
2. Open a pull request or perform the approved merge from a clean worktree.
3. After the merge, rerun `scripts/freyja-live-readiness.py` against the live
   deployment and record the result in the acceptance record.
4. Tag the merge commit with a neutral production-baseline tag after the
   post-merge verification succeeds.

No merge, tag, account activation, credential rotation, or channel enablement
is authorized merely by this checklist.
