# Rev 2 Completion Audit

**Date:** 2026-08-25  
**Status:** local production candidate; Signal onboarding/live smoke still external

This audit maps `docs/REV2_IMPLEMENTATION_PLAN.md` to current evidence. It is
intended to prevent Freyja 2.0 from being marked complete based on broad green
tests alone.

| Workstream | Current state | Evidence | Remaining proof before completion |
| --- | --- | --- | --- |
| A - Host and Deployment Alignment | Candidate implemented | README and Director Compose docs name Atlas as Director; host-role doc tests guard against Mars Director drift; readiness probe can verify attached connector production reports target the certified Atlas Director URL. | Production deployment must confirm live connectors target Atlas. |
| B - Provider Registry | Candidate implemented | `src/freyja/inference.py`; `/providers/health`; inference registry tests; `freyja-certify rev2-readiness` fails when required live provider profiles are missing or not ready. | Live provider endpoints must report expected readiness on Atlas/Iris/heavy-local hosts. |
| C - Iris 7B Route Classifier | Candidate implemented | Strict Iris recommendation model with tier, task, complexity, sensitivity, confidence, target, reason; advisory fallback tests; readiness probe checks live Iris availability. | Live Iris model residency and classifier quality must be certified on the target network. |
| D - Tiered Routing | Candidate implemented | Runtime evidence includes selected tier; router tests cover deterministic, Iris, heavy-local, and cloud paths. | Stage 3 default should wait for live certification and latency reports. |
| E - Runtime Evidence and Latency | Candidate implemented | Runtime evidence records provider profile, classifier metadata, readiness, total latency, warm/cold latency, and time to first token; readiness CLI requires a benchmark report and expected latency-winning target. | Live benchmark reports must show first-request latency and routing improvement. |
| F - MacAgent Boundary | Candidate implemented | MacAgent client requires token and Director authorization; health endpoint is non-authoritative; capability-family tests cover Messages, Calendar, Contacts, Shortcuts; readiness probe checks live authentication and advertised capabilities. | MacAgent service must be installed and authenticated on Iris. |
| G - Capability Broker | Candidate implemented | Capability authorization evidence records actor, permission, risk, approval policy, connector trust, scope, and approval state; final readiness can validate an attached approval exercise report. | Live consequential-action approvals must be exercised in deployment. |
| H - Trust-Aware External Workers | Candidate implemented | Worker policy blocks untrusted authoritative memory write, message send, home control, admin config, and privileged execution. | Any future external worker implementation must use this boundary. |
| I - Memory Provenance | Candidate implemented | Shared memory stores provenance, trust level, kind, observed timestamp, derivation links, and non-authoritative external observations; `freyja-certify rev2-memory-audit` inspects existing shared-memory rows read-only and can feed the final readiness report. | Existing long-lived production memory should be inspected after rollout for expected provenance defaults. |
| J - Certification | Candidate implemented | Rev 2 vertical spine covers the 15 required cases; route requests are executable; expectation keys are guarded by `SUPPORTED_EXPECTATION_KEYS`; `freyja-certify rev2-readiness` validates the required final cutover artifact bundle. | A timestamped Rev 2 certification report, benchmark report, connector report, memory report, approval report, and readiness report should be generated against the target deployment before final cutover. |

## Current Verification

- Focused docs/certification/readiness-bundle checks: `30 passed, 1 warning`
- Full project suite: `1100 passed, 2 skipped, 1 warning`
- Final status-doc guard: `11 passed, 1 warning`
- Live local Rev 2 entrypoint: started `freyja.atlas_app:app` on
  `127.0.0.1:8767`; health, provider, Iris, MacAgent boundary, and Road Mode
  endpoints responded.
- LaunchAgent readiness report:
  `certification/reports/20260824T164147.173324Z0000-rev2-readiness.json`
  passed against the actual unattended Director port `127.0.0.1:8000` with
  authenticated Director probes, authenticated MacAgent LaunchAgent health,
  provider health, latency evidence, memory provenance, approval exercise, and
  read-only iMessage production preflight evidence. MacAgent native handlers are
  implemented for Apple Calendar, iMessage, Contacts, and Shortcuts; live
  iMessage read and unapproved-send denial were exercised against the installed
  MacAgent service.
- Current status scripts confirm the Director and MacAgent LaunchAgents are
  loaded and running. Director `/health` is reachable, protected Rev 2 health
  checks pass, and MacAgent authenticated health returns the expected Rev 2
  Apple capability families.
- Current read-only iMessage production-check evidence reports connector
  prerequisites present, `imsg status` OK, the configured sender not locally
  known as an iMessage handle, and Messages AppleScript timing out.
- iMessage live-smoke dry-run produced an allowlisted one-recipient send plan
  and sent `0` messages; final outbound send still requires explicit operator
  approval via `scripts/imessage-operator.py live-smoke --yes`.
- Strict readiness with `certification/reports/imessage-live-smoke-dry-run.json`
  attached failed only `imessage-live-smoke-report`, proving the final gate will
  not pass from a dry-run.
- Strict readiness with `--require-smoke-report` and no smoke report generated
  `certification/reports/20260824T165923.877188Z0000-rev2-readiness.json`; every
  non-smoke check passed against the running local LaunchAgents, and the only
  failure was the missing required sent iMessage smoke report.
- The approved live-smoke attempt wrote
  `certification/reports/imessage-live-smoke-sent.json` with `sent: 0`,
  `failed: 1`, and a timeout error. The smoke operator resolves the configured
  `joe=` allowlist alias through authenticated MacAgent Contacts to Joseph
  Verant's locally known iMessage phone handle, but the underlying `imsg send`
  transport still times out for both that handle and an existing chat id.
  Messages AppleScript service/chat queries also time out, so that fallback is
  not currently viable. The follow-up strict readiness report
  `certification/reports/20260825T040632.268989Z0000-rev2-readiness.json`
  passed every non-smoke check and failed only because the smoke report does not
  prove a sent message.
- The final smoke-plus-readiness handoff is consolidated behind
  `scripts/rev2-readiness-bundle.py --imessage-live-smoke`; it dry-runs and
  stops before readiness unless `--yes` is supplied.
- The current Freyja 2.0 live evidence bundle supersedes the earlier iMessage
  timeout evidence. `certification/reports/freyja-live-evidence-summary.json`
  reports `ok: true`, `all_gates_passed: true`, iMessage runtime synced,
  terminal-equivalent iMessage route smoke passing, `freyja_qa_100` at `100.0%`
  with mean generation speed `31.238` tokens/sec, and
  `freyja_iterative_coding` at `100.0%` with mean generation speed `30.372`
  tokens/sec.
- The current approved iMessage smoke report
  `certification/reports/imessage-live-smoke-sent.json` reports `status: sent`,
  `sent: 1`, and `failed: 0`.
- Current Signal production evidence
  `certification/reports/freyja-live-signal-route-evidence.json` proves Atlas
  Director targeting and protected Rev 2 health, but Signal live smoke remains
  blocked by external account setup: the Compose Signal REST API is healthy and
  the dedicated account number is configured in private env, but Signal rejected
  SMS and voice registration requests with HTTP 400 pending captcha/linking;
  `SIGNAL_ENABLED=false` and no reviewed allowed sender is configured.
- Current Vulcan operator evidence shows Atlas can reach the configured Vulcan
  Ollama endpoint and the `fast`, `reason`, `code`, and `vision` logical
  profiles are installed. `scripts/vulcan-operator.py readiness` reports
  `ready_for_certification: true` after installing the configured `moondream`
  vision profile model.
- Package wheel build via `pip wheel . --no-deps`: `passed`
- Installed-wheel preflight console command reports both the safe dry-run review
  command and the approval-only final command with shell-safe quoting.
- Repository hygiene, compileall, and `git diff --check`: `passed`
- Ruff, mypy, and pyright are not installed in the local virtual environment;
  no lint/typecheck pass is claimed.

## Completion Decision

Do not mark the Freyja 2.0 goal complete until the Signal onboarding/live-smoke
gap is resolved or explicitly accepted as an external-service action item under
the active goal's completion criteria.
