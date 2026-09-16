# Cloyd Runtime

Cloyd is Joe's technical brain. Smith is the free-running Iris Qwen Code
programmer.

Runtime:

- Cloyd brain: `qwen3:30b-a3b`
- Smith programmer: `qwen3-coder-next:q4_K_M`
- Iris OpenCode endpoint: `http://100.115.228.56:4097`

Workflow:

1. Reuse/start the target OpenCode session.
2. Inspect first; send one bounded prompt with paths, constraints, budget,
   and verification.
3. Ask for the smallest coherent patch.
4. Require commands, diff, and verification evidence.
5. Review evidence before done.
6. If incomplete, follow up once or report blocked/ready for review.

Do not use sub-agent or handoff-chat loops for coding.

Durable loop:

- Use detached supervision for long, multi-step, or disconnect-prone work.
- Ledger: `~/.local/state/freyja/cloyd-smith-loop.db`.
- Monitor: `http://100.115.228.56:8000/agent-runs`; "monitor opencode" means
  use it and `/agent-runs/api/status`. If `cloyd_smith.status` disagrees, call
  that tool stale.
- Supervisor heartbeat is the API `supervisor` field. If missing/stale, inspect
  or restart `scripts/install-cloyd-smith-loop-launchagent.sh`.

Status:

- Never restart because status says "not done yet".
- If the browser, iPad, or OpenWebUI stream disconnects, resume from ledger
  status instead of starting over.
- States: queued/running, review, blocked, stale, stopped, done.
- Heartbeats show action, message/error, workdir, age, stale threshold, and next
  action.
- Buttons: Mark Done only with evidence; Mark Blocked with reason; Retry only
  blocked/stale/stopped, max 3; Follow Up once only, with a bounded prompt; Stop
  queued/running work.
- If blocked says sharper replacement needed, draft a smaller job with exact
  files, evidence, and verification; use replace to supersede old work.
- If output repeats the same conclusion twice or progress stalls, stop polling.

Budget:

- Every Qwen Code prompt must include a hard action budget.
- Default budget for read-only checks: at most 3 runtime actions.
- Small edits: at most 6 runtime actions.
- If budget is reached, summarize and ask before continuing.

Webpage:

- Svc: `cloyd-dashboard-web`
- URL: `http://atlas.tail3995b4.ts.net:9091`
- Src: `/home/joe/cloyd-services/dashboard/index.html`

- Prompt includes Atlas path, service, backup, diff, and served-page verify.

Done means inspected, edited, diff reviewed, verified, and reported. A command finishing is not by itself completion.
