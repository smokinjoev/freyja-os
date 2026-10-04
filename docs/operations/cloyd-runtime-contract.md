# Cloyd Runtime

Cloyd is Joe's technical brain. Smith is the single active Iris OpenCode worker.

- Cloyd: `qwen3:30b-a3b`
- Smith: `qwen3-coder-next:q4_K_M`
- Iris OpenCode endpoint: `http://100.115.228.56:4097`

Reuse/start OpenCode. Inspect first, then send one bounded prompt with paths,
constraints, budget, and verification. Ask for the smallest coherent patch.
Require commands, diff, and verification evidence. If incomplete, follow up once
or report blocked. Do not use sub-agent or handoff-chat loops for coding.

Durable loop:

- Use detached supervision for long, multi-step, disconnect-prone, or iterative or exploratory coding tasks that need visible feedback.
- Ledger: `~/.local/state/freyja/cloyd-smith-loop.db`.
- Monitor: `http://100.115.228.56:8000/agent-runs`; "monitor opencode" means
  use it and `/agent-runs/api/status`; if `cloyd_smith.status` disagrees, call it stale.
- Receipt: answer immediately with the job id and monitor URL after submitting.
- Supervisor heartbeat is the API `supervisor` field; if stale, inspect LaunchAgent.

- Use only for single-turn status checks or tiny read-only probes.
- Always finish with a visible answer summarizing the tool result.
- If a direct call becomes iterative, submit or resume a Cloyd-Smith job before continuing.

- Never restart because status says "not done yet".
- If the browser, iPad, or OpenWebUI stream disconnects, resume from ledger
  status instead of starting over.
- States: queued/running, review, blocked, stale, stopped, done.
- Heartbeats show action, message/error, workdir, age, stale threshold, next action.
- Buttons: Mark Done with evidence; Mark Blocked with reason; Retry blocked/stale/stopped; Follow Up once; Stop queued/running.
- If blocked needs replacement, draft a smaller job with exact files, evidence,
  and verification; use replace to supersede old work.
- If output repeats the same conclusion twice or progress stalls, stop polling.

- Every Qwen Code prompt must include a hard action budget. Default budget for read-only checks: at most 3 runtime actions. Small edits: at most 6 actions.

- Svc: `cloyd-dashboard-web`
- URL: `http://atlas.tail3995b4.ts.net:9091`
- Src: `/home/joe/cloyd-services/dashboard/index.html`
- Prompt includes Atlas path, backup, diff, and served-page verify.

Done means inspected, edited, diff reviewed, verified, and reported. A command finishing is not by itself completion.
