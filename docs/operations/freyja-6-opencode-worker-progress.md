# Freyja 6.0 OpenCode Worker Progress

Updated: 2026-10-03 08:29 America/New_York

## Baseline

- Repo: `/Users/freyja/freyja-os`
- Branch: `feature/cloyd-upstream-features`
- OpenCode CLI/server version: `1.18.30`
- Node: `v26.8.1`
- Python: system `3.14.6`, repo venv `3.12.13`
- OpenCode server: running on `http://100.115.228.56:4097`
- OpenCode config: `model=vulcan-coder/qwen3-coder-next:q4_K_M`; Nexus provider has request/header/chunk timeouts disabled in live config; dedicated coder provider points at Vulcan Ollama OpenAI-compatible endpoint.
- Freyja Core LaunchAgent `com.freyja-os.core`: loaded and running, pid observed `76454`.
- Cloyd-Smith LaunchAgent `com.freyja-os.cloyd-smith-loop`: was not loaded at baseline; installed/reloaded during this checkpoint and then observed running as pid `83321`.
- Director/Agent Runs LaunchAgent `com.freyja-os.director`: restarted during this checkpoint and observed running as pid `83620`.
- Agent Runs API: reachable at `http://100.115.228.56:8000/agent-runs/api/status`.
- Baseline heartbeat cause: supervisor heartbeat was stale because the loop LaunchAgent was not loaded. Last stale heartbeat was `2026-10-03T11:03:44.694489+00:00` from pid `75574`.
- Post-deploy heartbeat: supervisor `ok=true`, `status=loop_ok`, age observed `6s`, pid `83321`.
- Runtime status: OpenCode `/session/status` was `{}` and Agent Runs reported `session_count=0`.
- Live Agent Runs API after Director restart includes the new `queue.unknown` field and reported `unknown=0`.
- Second deployment reload after schema work: Cloyd-Smith loop and Director were restarted; live Agent Runs API reported supervisor `ok=true`, heartbeat age `5s`, runtime `ok=true`, `session_count=0`, and run keys present for `session_id`, `submission_id`, `job_phase`, `scope`, `check_commands`, `revision_evidence`, and `stop_intent`.
- Third deployment reload after duplicate-dispatch fencing: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `5s`, queue `queued=0/running=0/unknown=0`, runtime `ok=true`, and `session_count=0`.
- Fourth deployment reload after verification-state work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, and queue fields for `waiting_for_input`, `verifying`, `verified`, `needs_attention`, and `stopping`, all at `0`.
- Fifth deployment reload after repair-cycle work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/needs_attention=0`, and visible run summaries include `repair_attempts`.
- Sixth deployment reload after stale-verification work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `7s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/needs_attention=0/verified=0`, and cycle `check_for_work`.
- Seventh deployment reload after stop-semantics work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/stopping=0/needs_attention=0`, and cycle `check_for_work`.
- Eighth deployment reload after Agent Runs current-card work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/stopping=0/needs_attention=0`, and cycle `check_for_work`.
- Ninth deployment reload after reconnect/permission-wait work: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/unknown=0/waiting_for_input=0`, and cycle `check_for_work`.
- Tenth deployment reload after stop-during-command evidence: Cloyd-Smith loop and Director restarted cleanly; live Agent Runs API reported supervisor `ok=true`, heartbeat age `8s`, runtime `ok=true`, `session_count=0`, queue `queued=0/running=0/unknown=0/waiting_for_input=0/stopping=0/needs_attention=0`, and one existing stopped job.
- Live repair-loop demo job `freyja52-b2e5ef0a3d3b`: first turn ran in session `ses_efe4549f4ffeqDD2vCulxAkdUk`, independent check failed with exit `1`, repair attempt `1` was queued into the same session, second submission `msg_a9ecf38a96f64f468d6873e257ed5382` passed the recorded check, and final Agent Runs status was `verified`.
- Post-demo live recheck: after this progress note changed the working tree, Agent Runs refreshed the same job through `verification_recheck`, kept status `verified`, reported `session_count=0`, and queue `queued=0/running=0/unknown=0/stopping=0/needs_attention=0`.
- Ledger state: no active queued/running jobs; one visible stopped job remains from earlier operator bulk stop. Stopped work was not requeued.

## Checkpoint

This file is the repo checkpoint for subsequent turns. It records the current baseline, implementation direction, tests, blockers, next actions, and rollback notes without changing external state or requeueing stopped jobs.

## Changes This Turn

- `src/freyja/tools/opencode_runtime.py`
  - `opencode_send` now submits through OpenCode 1.18.30 `POST /session/{sessionID}/prompt_async`.
  - Returns a `submission_id`/message id immediately and leaves progress/result observation to status/output polling.
  - Sends `tools: {"task": false, "subagent": false}` to deny worker delegation.

- `scripts/cloyd-smith-loop-daemon.py`
  - Queued dispatch now freezes when OpenCode reports an active external worker session.
  - Running-job status failures now become `unknown` telemetry, not blocked/failed/done.
  - No-activity heartbeat timeout records a warning only.
  - Slow first response past 15 minutes records `first_response_warning` and keeps the worker alive.
  - Same-job repair/retry cycles can reuse the job's existing session instead of starting a replacement session.
  - Smith prompts now include scope and agreed check commands.
  - Output-ready transitions capture revision evidence without crashing the controller if capture fails.
  - Queued jobs with an existing session/submission are reconciled as running instead of being submitted twice after controller recovery.
  - Idle Smith turns now enter a verifier path. Jobs with recorded check commands run those checks locally, bind results to revision evidence, and become `verified` only when all checks pass. Failed checks become `needs_attention`. Jobs without recorded checks keep the old `needs_review` behavior.
  - `needs_attention` jobs with failing check evidence now queue a bounded same-session repair prompt automatically, clear the old submission id, and reuse the existing Smith session.
  - Repair attempts are capped at two. Repeated identical check failures with the same working-tree digest remain `needs_attention` and request operator attention instead of looping.
  - Recent `verified` jobs are audited by the controller. If HEAD or working-tree content changes, recorded checks run again before `verified` is retained; failures demote to `needs_attention`, and no-check jobs demote to `needs_review`.
  - `stopping` jobs are reconciled by the daemon through OpenCode stop before becoming `stopped`.
  - Jobs with `stop_intent=after_current_turn` continue running while Smith is busy, then harvest output at the idle turn boundary and become `stopped` without verification or repair.
  - `unknown` telemetry jobs are reconciled from fresh OpenCode status snapshots. Busy sessions return to `running`; idle sessions harvest output and enter verification.
  - Permission/input waits are detected from OpenCode status snapshots and surfaced as `waiting_for_input`, then reconciled back to `running` when the wait clears.

- `src/freyja/cloyd_smith_loop.py`
  - Added `unknown` as a first-class run state.
  - Agent Runs status now counts `unknown`, treats it as attention, and surfaces a diagnostic to freeze dispatch/reconcile telemetry.
  - Heartbeat staleness no longer converts a running job to stale terminal handling by itself.
  - Job rows now persist scope, check commands, phase, session id, submission id, stop intent, and revision evidence.
  - Added `capture_revision_evidence`, binding verification evidence to git HEAD, dirty tracked diff digest, untracked file hashes, check commands, and check results.
  - Added target run states: `waiting_for_input`, `verifying`, `verified`, `needs_attention`, and `stopping`, with queue/attention summaries.
  - Run summaries expose `repair_attempts`.

- `src/freyja/main.py`
  - Agent Runs SSE refresh is now 2 seconds.
  - Run cards expose unknown count, job phase, session id, submission id, scope, check commands, and revision evidence summary.
  - Summary metrics now show waiting, verifying, verified, attention, and stopping counts.
  - Run cards now show repair attempt counts.
  - Run cards now expose separate `Stop After Turn` and immediate `Stop` controls.
  - Agent Runs now promotes one current task card, exposes Open Session links, shows check results, files/diff, checked revision, blocker, and next action as separate fields, and labels Retry as Resume/Retry.
  - Added a per-job Start control/API for queued jobs. It records operator intent and leaves dispatch to the durable single-worker daemon.
  - Immediate Stop now records an OpenCode status snapshot before aborting the runtime, so active tool/command evidence is preserved when available.

- `scripts/com.freyja-os.cloyd-smith-loop.plist`
  - Heartbeat interval changed to 10 seconds.
  - OpenCode request timeout changed to 300 seconds.

- `config/open-webui-home-agents.yaml`
  - Cloyd prompt now says one active Iris OpenCode worker while preserving the durable Cloyd-Smith loop.
  - Restored durable Cloyd-Smith tool grants additively; OpenWebUI Cloyd keeps `cloyd_smith.status` and durable loop commands.
  - Removed stale `free-running` coding-worker wording from Cloyd's family webpage instructions.

- `docs/operations/cloyd-runtime-contract.md`
  - Compact runtime contract now describes Smith as the single active Iris OpenCode worker.

- `docs/operations/cloyd-smith-live-repair-demo.txt`
  - Added as the bounded live repair-loop artifact. It began as `Freyja 6 live repair demo: broken`; the Cloyd-Smith/OpenCode repair path changed it to `Freyja 6 live repair demo: verified`.

- `scripts/export-open-webui-home-agents.py`
  - Validation now protects both direct OpenCode commands and durable Cloyd-Smith commands.

- `src/freyja/tools/cloyd_smith_loop.py`
  - `cloyd_smith_submit` accepts `scope` and `check_commands` and records them in the durable job.
  - Retry/follow-up controls clear stale submission ids before intentionally queueing a new worker turn.

## Tests

Passed:

```bash
.venv/bin/pytest -q tests/test_opencode_runtime_tools.py tests/test_cloyd_smith_loop.py tests/test_open_webui_home_agent_export.py
```

Result: `105 passed in 0.77s`

Final focused bundle:

```bash
.venv/bin/pytest -q tests/test_opencode_runtime_tools.py tests/test_cloyd_smith_loop.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `117 passed in 0.81s`

Latest focused bundle after schema/API work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `119 passed in 1.05s`

Latest focused bundle after duplicate-dispatch fencing:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `120 passed in 1.19s`

Latest focused bundle after verification-state work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `122 passed in 1.24s`

Latest focused bundle after repair-cycle work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `126 passed in 1.24s`

Latest focused bundle after stale-verification work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `130 passed in 1.23s`

Latest focused bundle after stop-semantics work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `136 passed in 1.28s`

Latest focused bundle after Agent Runs current-card work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `137 passed in 1.29s`

Latest focused bundle after reconnect/permission-wait work:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `142 passed in 1.39s`

Stop-focused coverage after pre-abort runtime evidence:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py -k "stop_job or stop_after_current_turn or runtime_stop_endpoint"
```

Result: `8 passed, 105 deselected in 0.26s`

Latest focused bundle after stop-during-command evidence:

```bash
.venv/bin/pytest -q tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `144 passed in 1.42s`

Direct OpenWebUI home-agent and Cloyd/OpenCode suite after prompt wording cleanup:

```bash
.venv/bin/pytest -q tests/test_open_webui_home_agents.py tests/test_open_webui_home_agent_export.py tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py
```

Result: `137 passed in 1.27s`

Latest broader focused bundle:

```bash
.venv/bin/pytest -q tests/test_open_webui_home_agents.py tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `149 passed in 1.37s`

Latest broader focused bundle after the live repair demo:

```bash
.venv/bin/pytest -q tests/test_open_webui_home_agents.py tests/test_cloyd_smith_loop.py tests/test_opencode_runtime_tools.py tests/test_open_webui_home_agent_export.py tests/test_freyja_continuity.py tests/test_openwebui_opencode_runtime_bind.py tests/test_openwebui_freyja_core_bridge.py
```

Result: `149 passed in 1.40s`

Live repair-loop demonstration:

```bash
grep -qx 'Freyja 6 live repair demo: verified' docs/operations/cloyd-smith-live-repair-demo.txt
```

Result: passed.

Authoritative ledger evidence for job `freyja52-b2e5ef0a3d3b`:

- first check result: exit `1`;
- `repair_queued` attempt `1`;
- same session before and after repair: `ses_efe4549f4ffeqDD2vCulxAkdUk`;
- final check result: exit `0`, no timeout;
- final status: `verified`;
- revision evidence captured HEAD `00a5eb0a5ac8efd7b6a4cd4d8b0d5257a9317b83`, `tracked_diff_sha256`, untracked file hashes, the check command, and the passing check result.

Syntax check:

```bash
.venv/bin/python -m py_compile src/freyja/cloyd_smith_loop.py src/freyja/main.py scripts/cloyd-smith-loop-daemon.py src/freyja/tools/cloyd_smith_loop.py
```

Result: passed.

Covered in focused tests:

- async OpenCode send uses `prompt_async`;
- durable jobs persist scope, check commands, session id, submission id, phase, stop intent, and revision evidence;
- revision evidence covers HEAD, tracked dirty diff, and untracked files;
- duplicate dispatch fencing reconciles queued jobs that already have a session/submission;
- retry/follow-up clears stale submission ids before queueing a new worker turn;
- no-activity warning is non-terminal;
- slow first response warning does not call stop;
- external busy OpenCode session blocks queued dispatch;
- telemetry loss becomes `unknown`;
- idle output without recorded checks remains `needs_review`;
- idle output with passing recorded checks becomes `verified`;
- idle output with failing recorded checks becomes `needs_attention`;
- failed checks queue a repair prompt in the same Smith session;
- queued repairs reuse the existing session and do not start a new one;
- repeated identical failed checks without working-tree progress remain `needs_attention`;
- repair attempts are capped at two;
- verified jobs with unchanged revision evidence do not rerun checks;
- verified jobs with changed HEAD or working-tree digest rerun checks before keeping `verified`;
- stale verified jobs with failing checks demote to `needs_attention`;
- stale verified jobs without recorded checks demote to `needs_review`;
- immediate Stop persists `stopping`, aborts OpenCode, and only marks stopped after a successful stop result;
- immediate Stop records pre-abort OpenCode status evidence, including an active command such as `sleep 60` when exposed by runtime telemetry;
- immediate Stop still attempts runtime abort when the pre-abort status snapshot fails;
- failed immediate Stop leaves the job in `stopping` for reconciliation instead of relabeling stopped;
- stop-after-current-turn persists intent without aborting the runtime;
- the daemon stops after the current turn only when OpenCode reaches idle;
- `stopping` jobs are reconciled by the daemon through OpenCode stop;
- Agent Runs page contains Current task, Open Session, Start, Resume/Retry, check results, files/diff, checked revision, and blocker fields;
- per-job Start for queued work records `operator_start_requested` without bypassing the daemon;
- telemetry loss becomes `unknown`, and fresh busy status reconnects it to `running`;
- telemetry loss followed by idle status harvests output and verifies before any success claim;
- permission waits become `waiting_for_input` and count as attention;
- resolved permission waits reconnect to `running`;
- OpenWebUI Cloyd export preserves durable Cloyd-Smith grants.
- live Cloyd-Smith/OpenCode repair-loop demonstration repaired a real failing check in the same session and earned `verified` only after the controller reran the independent check.

## Residual Risks / Notes

- Live Cloyd-Smith LaunchAgent and Director API were validated after restart; no stopped work was requeued.
- The repo already had unrelated dirty files before this turn: Discord gateway, Core MCP, Home Assistant, shepherd, and continuity changes. They were not reverted.
- Optional UI polish remains possible: a richer visual diff preview in Agent Runs. It is not required for the one-worker controller milestone.

## Next Action

1. Commit/review the accumulated changes when ready.
2. Keep using Agent Runs as the single operator surface for Cloyd-Smith/OpenCode work.
3. Treat richer diff preview as a later UI enhancement, not a controller blocker.

## Rollback

- Code rollback: revert the touched files from this checkpoint if needed:
  - `src/freyja/tools/opencode_runtime.py`
  - `scripts/cloyd-smith-loop-daemon.py`
  - `src/freyja/cloyd_smith_loop.py`
  - `scripts/com.freyja-os.cloyd-smith-loop.plist`
  - `config/open-webui-home-agents.yaml`
  - `scripts/export-open-webui-home-agents.py`
  - related focused tests
- Runtime rollback: if the LaunchAgent is installed and misbehaves, run:

```bash
launchctl bootout gui/$(id -u) /Users/freyja/Library/LaunchAgents/com.freyja-os.cloyd-smith-loop.plist
```

- Director rollback/reload:

```bash
launchctl kickstart -k gui/$(id -u)/com.freyja-os.director
```

- Do not requeue stopped jobs automatically during rollback. Inspect the Agent Runs ledger first.
