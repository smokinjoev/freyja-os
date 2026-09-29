# Production Baseline Merge Gate

Target: merge `feature/cloyd-upstream-features` into `main` only after these
conditions are met. This document prevents a documentation or reachability
pass from being mistaken for production certification.

## Current branch state (2026-09-29)

- `feature/cloyd-upstream-features` is clean and is 32 commits ahead of
  `origin/main`, with no commits unique to `origin/main`.
- The no-secret operational baseline passes with:

  ```sh
  python3 scripts/freyja-live-readiness.py
  ```

- Atlas portals, Vulcan Director/Nexus/Ollama, Iris Core, per-agent MCP
  initialization, the Agent Smith monitor, and both Discord connector
  processes have current live evidence.

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
4. Run the repository verification available in the release environment:

   ```sh
   python -m compileall -q src connectors certification tests
   python -m pytest
   python3 scripts/freyja-live-readiness.py
   ```

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
