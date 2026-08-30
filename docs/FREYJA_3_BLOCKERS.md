# Freyja 3.0 Blockers

Last updated: 2026-08-30.

## Active Blockers

- BLOCKER: Joe must review and reconcile the pre-existing dirty worktree before
  any broad live deployment or history cleanup. Starting dirty files included
  `src/freyja/agent_runtime_v3.py`, `src/freyja/config.py`,
  `src/freyja/main.py`, `tests/test_freyja3_architecture.py`,
  `tests/test_host_role_docs.py`, `docs/operations/homepod-shortcuts-voice.md`,
  plus untracked Home Assistant/Open WebUI files.

## External Or Hardware Blockers

- BLOCKER: Install and expose Hera camera/sensor hardware before requiring
  camera-backed semantic perception evidence. Current architecture permits
  no-camera semantic status events until hardware exists.
- BLOCKER: Any live messaging account enrollment, iCloud prompts, Signal captcha,
  or Apple privacy prompt that cannot be completed from the current shell needs
  Joe to complete the prompted account/device action.

## Non-Blockers

- The Freyja 4.0 Nexus evaluation can proceed in docs and local config/tests
  without resolving unrelated dirty files.
- Existing Freyja 3.0 architecture docs under `docs/architecture/` remain valid
  checkpoint evidence.
