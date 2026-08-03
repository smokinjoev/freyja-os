# Freyja-OS Where We Left Off

**Date:** 2026-08-03  
**Repository:** `git@github.com:smokinjoev/freyja-os.git`  
**Local path inspected:** `/home/joe/freyja-os`  
**Branch inspected:** `main`  
**Git state at handoff:** clean worktree, `main` is ahead of `origin/main` by 7 commits  
**Latest local commit:** `15ca096 Add canonical identity service`  
**Verification:** `.venv/bin/pytest` passed with `629 passed, 4 skipped, 1 warning` on Linux Python 3.14.4

This document is self-contained. It assumes the next Codex task does not have
access to prior conversation context.

## 1. Current Purpose and Intended Outcome

Freyja-OS is a locally controlled personal-agent orchestration platform. Its
intended outcome is a secure, local-first personal AI control plane that can be
used from phones and computers through trusted connectors, while centralizing
policy, routing, memory, identity, tool execution, logging, cost controls, and
fallback behavior.

The design is explicitly not a pile of independent chatbots. The intended shape
is one Freyja Director that receives requests, resolves identity and memory
context, applies policy, selects local or cloud inference, invokes approved
tools, and returns sanitized responses through controlled entry points.

The current product direction is:

- Mars runs the Freyja Director and control plane.
- Atlas runs always-on infrastructure and the Signal connector.
- Hera provides complex local reasoning over Tailscale, currently
  `gpt-oss:20b`, but is not core always-on infrastructure.
- Iris provides the fast local inference tier.
- Signal is the primary secure remote interface.
- iMessage is a secondary Apple-native interface.
- Telegram is useful for testing and travel-mode work but should not become the
  primary secure path.
- OpenRouter is the approved cloud fallback path when enabled, keyed, allowed,
  and within budget.

## 2. Completed Work

### Repository and Documentation Foundation

- Base Python package exists under `src/freyja`.
- Tests exist under `tests`.
- Connector code exists under `connectors`.
- Certification framework exists under `certification`.
- Deployment assets exist under `deploy`.
- Existing baseline docs:
  - `README.md`
  - `ARCHITECTURE.md`
  - `ROADMAP.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `docs/HANDOFF.md`
  - `docs/REV1_STATUS.md`
  - `docs/shared-memory.md`
  - `certification/README.md`

### Director and Routing

- FastAPI Director service exists in `src/freyja/main.py`.
- Public endpoints include:
  - `GET /`
  - `GET /health`
  - `GET /ollama/health`
  - `GET /local-reasoning/health`
  - `GET /ollama/models`
  - `POST /chat`
  - `GET /openrouter/health`
  - `POST /openrouter/chat`
  - `POST /route`
- Non-public endpoints require bearer-token auth when `FREYJA_CONNECTOR_TOKEN`
  is configured.
- Routing models live in `src/freyja/router.py`.
- Router supports provider choices `auto`, local Ollama, local reasoning, and
  OpenRouter fallback according to task type, privacy, context size, tool needs,
  prompt complexity, and config.
- Router blocks sub-3B models from full chat by default through
  `OLLAMA_MIN_CHAT_PARAMETERS_B=3`.
- Tool-required route responses expose only sanitized tool result metadata.

### Model Provider Adapters

- Ollama client exists in `src/freyja/ollama_client.py`.
- OpenRouter client exists in `src/freyja/openrouter_client.py`.
- Config supports separate model roles:
  - `OLLAMA_MODEL`
  - `OLLAMA_CHAT_MODEL`
  - `OLLAMA_CLASSIFICATION_MODEL`
  - `OLLAMA_REASONING_MODEL`
- Default reasoning model is `gpt-oss:20b`.
- Default cloud model is `openai/gpt-4o-mini`.
- OpenRouter allowlist support exists through `OPENROUTER_ALLOWLIST`.

### Memory

- Memory package exists under `src/freyja/memory`.
- Conversation and shared-memory APIs are wired into the Director.
- Memory principals prevent known people from being stored only as raw platform
  IDs.
- Shared memory has configurable limits for per-principal item count, global
  item count, item size, recall count, recall size, and cloud-inclusion policy.
- Default memory database path in code is repo-local `data/freyja.db`.
- Runtime state outside the repo was also observed at
  `~/.local/state/freyja`.

### Identity Service

- Canonical identity service exists under `src/freyja/identity`.
- Models include `Person`, `Identity`, `Alias`, and `Relationship`.
- `IdentityService` resolves aliases, phone numbers, email addresses, Signal
  identities, iMessage identities, and calendar owners.
- Directed relationships such as spouse and child are queryable.
- Director tools exist for:
  - `identity_resolution`
  - `identity_relationships`
- Signal and iMessage can map approved senders to canonical Person metadata
  while preserving legacy allowlist behavior.
- Calendar tools can accept person IDs or aliases and can default to the
  resolved sender when present.
- Identity certification suites exist under `certification/suites/identity`.

### Communications

- Shared messaging abstractions exist under `connectors/messaging.py`.
- Signal connector code exists under `connectors/signal`.
- iMessage connector code exists under `connectors/imessage`.
- Telegram connector code exists under `connectors/telegram`.
- Signal and iMessage gateways enforce sender policy, reject unauthorized
  senders, forward authorized requests to `/route`, and return sanitized
  responses.
- Allowed sender aliases are supported, for example:

```text
SIGNAL_ALLOWED_SENDERS=joe=+15551234567,beth=+15557654321
IMESSAGE_ALLOWED_SENDERS=joe=joe@example.com,beth=+15557654321
```

### Family Calendar Personal Intelligence Service

- Calendar package exists under `src/freyja/calendar`.
- `CalendarService` owns schedule reasoning.
- Provider adapters isolate calendar backends.
- Google and Apple provider boundaries are represented without requiring live
  accounts in tests.
- Director tools expose schedule, free/busy, event search, CRUD, ranked time
  finding, and conflict-aware event movement.
- Long-term preferences from memory can influence scheduling, while explicit
  user instructions remain higher priority.

### Agent Smith

- Agent Smith orchestration exists under `src/freyja/agents`.
- Policy config exists at `config/agent-smith-policy.yaml`.
- Approval store code exists with persistent SQLite state.
- CLI helper exists at `src/freyja/cli/smith_approval.py` and script wrapper
  exists at `scripts/smith-approval`.
- Dry-run, read-only, and write-pilot modes are present but disabled by
  default through config flags.
- Approved write-pilot tools are only enabled when both
  `AGENT_SMITH_ENABLED=true` and `AGENT_SMITH_WRITE_PILOT_ENABLED=true`.
- Agent Smith audit log default is `logs/agent-smith-audit.jsonl`.
- Observed runtime approval DB path:
  `~/.local/state/freyja/smith-approvals.sqlite3`.

### Certification and Benchmarking

- CLI entry point is `freyja-certify = certification.cli:main`.
- Certification suites exist for core behavior, tools, routing, memory, vision,
  planning, connectors, calendar, and identity.
- Reports are written under `certification/reports/` by default.
- Benchmark and comparison framework has been added.
- Existing generated benchmark/quality artifacts were observed under `logs/`.

### Deployment Assets

- Mars Director Compose project exists:
  - `deploy/compose/director/compose.yaml`
  - `deploy/compose/director/.env.example`
  - `deploy/compose/director/README.md`
- Atlas Signal connector Compose project exists:
  - `deploy/compose/signal/compose.yaml`
  - `deploy/compose/signal/.env.example`
  - `deploy/compose/signal/README.md`
- Dockerfiles exist:
  - `deploy/docker/director.Dockerfile`
  - `deploy/docker/signal-connector.Dockerfile`
- macOS LaunchAgent templates exist:
  - `scripts/com.freyja-os.director.plist`
  - `scripts/com.freyja-os.imessage-connector.plist`
  - `scripts/com.freyja-os.telegram-gateway.plist`

## 3. Partially Completed or In Progress

- Identity currently has an in-code/default seed model. It needs a durable
  contacts source.
- Production contact import/sync is not implemented yet.
- Google Contacts, Apple Contacts, or encrypted local contact-file sync needs a
  decision and implementation.
- Relationship modeling is intentionally minimal and should be expanded.
- Identity-backed voice/avatar adapters are future work.
- Router policy does not yet use identity benchmark history automatically.
- Signal deployment is documented but requires live account linking and
  reviewed sender allowlists before production use.
- OpenRouter fallback exists but requires credentials, allowlist review, and
  budget settings before production use.
- iMessage support exists, but native operation depends on a macOS host,
  Messages permissions, Full Disk Access where needed, and LaunchAgent setup.
- Agent Smith write-pilot mode exists but should remain gated behind explicit
  approval and policy.
- The Rev 1 host split is documented, but actual deployment needs validation
  on Mars, Atlas, Hera, and Iris.
- CI, lint, type checking, issue templates, PR templates, and secret scanning
  are listed on the roadmap but were not observed as completed.

## 4. Known Bugs, Blockers, Risks, and Open Questions

### Blockers

1. Push local commits: local `main` is ahead of `origin/main` by 7 commits.
2. Set the same strong `FREYJA_CONNECTOR_TOKEN` on Mars and Atlas.
3. Register or link Signal deliberately in the Atlas REST wrapper state volume.
4. Review and set `SIGNAL_ACCOUNT_NUMBER` and `SIGNAL_ALLOWED_SENDERS`.
5. Configure OpenRouter API key and allowlist if cloud fallback is required.
6. Confirm Hera's `gpt-oss:20b` is available from Mars over Tailscale.
7. Confirm Iris fast-local inference endpoint and model availability.
8. Decide on and implement persistent identity/contact storage.

### Risks

- Telegram should not accidentally become the primary secure control path.
- Hera must not be treated as always-on infrastructure. Director routing must
  tolerate Hera being unavailable.
- The populated `.env` files, Signal account state, connector token, phone
  numbers, and contact data must never be committed.
- `data/freyja.db` exists locally but runtime databases should be treated as
  state, not source.
- The repo contains ignored local `.venv`, pycache, pytest cache, logs, and
  runtime data. Do not bulk add ignored files.
- Running tests emitted sandbox-related lines:
  `Failed to create stream fd: Operation not permitted`. The suite still
  passed; keep an eye on this if subprocess or PTY behavior changes.
- FastAPI/Starlette warning observed:
  `Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

### Open Questions

- Which contact source is canonical: Google Contacts, Apple Contacts, encrypted
  local file, or a combination?
- Which Mac account should run native iMessage in production: `freyja`, Joe's
  interactive account, or a dedicated service account?
- Should Mars run under Docker Compose only, LaunchAgent only, or both for
  different modes?
- How should budget usage be persisted and audited for OpenRouter?
- Which tasks are allowed for Agent Smith read-only and write-pilot modes in
  production?
- What is the desired backup policy for `data/freyja.db`, Smith approvals, and
  Signal state?

## 5. Exact Next Recommended Steps

1. Preserve current local work:

```bash
cd /home/joe/freyja-os
git status --short --branch
git log --oneline --decorate --max-count=10
```

2. Push the seven local commits to GitHub after review:

```bash
cd /home/joe/freyja-os
git push origin main
```

3. On the MacBook Pro, clone or update the repo:

```bash
git clone git@github.com:smokinjoev/freyja-os.git ~/freyja-os
cd ~/freyja-os
```

4. Create a local virtualenv and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

5. Run tests on the MacBook:

```bash
pytest
```

6. Create local config and keep it private:

```bash
cp .env.example .env
chmod 600 .env
```

7. For local Director development, start the API:

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn freyja.main:app --host 127.0.0.1 --port 8000 --reload
curl --fail http://127.0.0.1:8000/health
```

8. Verify local or remote Ollama configuration:

```bash
curl --fail http://127.0.0.1:11434/api/tags
curl --fail http://127.0.0.1:8000/ollama/health
curl --fail http://127.0.0.1:8000/local-reasoning/health
```

9. Backfill the missing docs listed in section 9, starting with setup and
   operations runbooks.

10. Implement persistent identity contacts:

- Pick one source for the first pass.
- Add provider interface and tests.
- Migrate seeded household data out of code.
- Keep raw contact data out of git.

11. Validate Mars/Atlas/Hera/Iris deployment in order:

- Hera: confirm `gpt-oss:20b` and private Ollama reachability.
- Mars: configure Director with Hera and Iris endpoints.
- Atlas: verify Mars `/health` over Tailscale.
- Atlas: create Signal `.env`, keep `SIGNAL_ENABLED=false`.
- Link/register Signal manually.
- Set sender allowlist.
- Enable Signal connector.
- Send one authorized test message.

## 6. Relevant Files, Folders, Branches, Repositories, Services, Commands, URLs, and Environment Details

### Repository

- Remote: `git@github.com:smokinjoev/freyja-os.git`
- Local inspected path: `/home/joe/freyja-os`
- Branches observed:
  - `main` at `15ca096`, ahead of `origin/main` by 7 commits
  - `feature/certification-framework` at `d340f9b`
- Recent local commits not on `origin/main`:
  - `15ca096 Add canonical identity service`
  - `ba992fb Complete multi-user communications integration`
  - `873e8e2 Add family calendar intelligence service`
  - `fc94331 Add certification benchmark framework`
  - `51295e5 Record runtime evidence in Director certification`
  - `53ab1e6 Integrate certification runtime evidence`
  - `d34e17c Build certification gauntlet`

### Important Source Folders

- `src/freyja/main.py`: FastAPI Director and endpoint wiring.
- `src/freyja/router.py`: routing policy and provider selection.
- `src/freyja/config.py`: environment-backed settings.
- `src/freyja/ollama_client.py`: Ollama provider adapter.
- `src/freyja/openrouter_client.py`: OpenRouter provider adapter.
- `src/freyja/memory`: memory models, principals, store, APIs.
- `src/freyja/identity`: canonical people and relationship service.
- `src/freyja/calendar`: Family Calendar service and providers.
- `src/freyja/tools`: tool registry and built-in tools.
- `src/freyja/agents`: Agent Smith orchestration, policy, runtime, approvals.
- `connectors/signal`: Signal gateway and transport.
- `connectors/imessage`: native iMessage gateway and transport.
- `connectors/telegram`: Telegram gateway and scripts.
- `certification`: certification CLI, runner, grader, benchmark, suites.
- `deploy`: Dockerfiles and Compose projects.
- `scripts`: install, status, connector, LaunchAgent, and operator scripts.
- `tests`: 633 collected tests at handoff.

### Runtime and State Paths Observed on Linux Host

- `~/.config/freyja/hermes-connector-token`
- `~/.local/state/freyja/smith-approvals.sqlite3`
- `~/.local/state/freyja/telegram/telegram-heartbeat.json`
- `~/.config/systemd/user/freyja-wake.service`
- `~/.config/systemd/user/freyja-openwakeword.service`
- `~/.config/systemd/user/freyja-inhibit.service`
- `~/.config/systemd/user/freyja-vision.service`
- `~/.config/systemd/user/freyja-agent.service`
- `~/.config/systemd/user/freyja-avatar.service`
- `~/.config/systemd/user/freyja-hermes-adapter.service`
- `~/.config/systemd/user/freyja-kiosk.service`

### Primary Commands

```bash
cd /home/joe/freyja-os
source .venv/bin/activate
pytest
freyja-certify
PYTHONPATH=src uvicorn freyja.main:app --host 127.0.0.1 --port 8000 --reload
curl --fail http://127.0.0.1:8000/health
```

### Mars Director Compose

```bash
cp deploy/compose/director/.env.example deploy/compose/director/.env
chmod 600 deploy/compose/director/.env
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml config
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml up -d --build
curl --fail http://<mars-tailscale-host>:8000/health
```

### Atlas Signal Compose

```bash
cp deploy/compose/signal/.env.example deploy/compose/signal/.env
chmod 600 deploy/compose/signal/.env
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml config
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml up -d --build
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml ps
```

### Relevant URLs

- Local Director health: `http://127.0.0.1:8000/health`
- Local Ollama default: `http://127.0.0.1:11434`
- Mars Director over tailnet: `http://<mars-tailscale-host>:8000`
- Hera Ollama over tailnet: `http://<hera-tailscale-host>:11434`
- OpenRouter API: `https://openrouter.ai/api/v1`
- Signal REST wrapper upstream image: `bbernhard/signal-cli-rest-api:0.100`

### Key Environment Variables

- `FREYJA_ENV`
- `FREYJA_HOST`
- `FREYJA_PORT`
- `FREYJA_CONNECTOR_TOKEN`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_CHAT_MODEL`
- `OLLAMA_CLASSIFICATION_MODEL`
- `OLLAMA_REASONING_MODEL`
- `OLLAMA_MIN_CHAT_PARAMETERS_B`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL`
- `OPENROUTER_ALLOWLIST`
- `CLOUD_ENABLED`
- `OPENROUTER_MONTHLY_SOFT_LIMIT`
- `OPENROUTER_MONTHLY_HARD_LIMIT`
- `OPENROUTER_PER_REQUEST_LIMIT`
- `MEMORY_ENABLED`
- `MEMORY_DATABASE_PATH`
- `MEMORY_SHARED_ENABLED`
- `MEMORY_RECALL_INCLUDE_IN_CLOUD`
- `TOOLS_ENABLED`
- `WEATHER_TOOL_ENABLED`
- `AGENT_SMITH_ENABLED`
- `AGENT_SMITH_DRY_RUN_ENABLED`
- `AGENT_SMITH_READ_ONLY_ENABLED`
- `AGENT_SMITH_WRITE_PILOT_ENABLED`
- `TELEGRAM_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- `SIGNAL_ENABLED`
- `SIGNAL_ACCOUNT_NUMBER`
- `SIGNAL_ALLOWED_SENDERS`
- `SIGNAL_REST_API_URL`
- `SIGNAL_MAX_MESSAGE_CHARS`
- `IMESSAGE_ALLOWED_SENDERS`

## 7. Setup Needed to Continue on the MacBook Pro

Minimum setup:

```bash
xcode-select --install
brew install git python docker ollama
git clone git@github.com:smokinjoev/freyja-os.git ~/freyja-os
cd ~/freyja-os
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
pytest
cp .env.example .env
chmod 600 .env
```

For local-only development:

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
PYTHONPATH=src uvicorn freyja.main:app --host 127.0.0.1 --port 8000 --reload
```

For production-like local testing on the MacBook Pro:

- Fill `.env` with local or tailnet endpoints.
- Set `FREYJA_CONNECTOR_TOKEN` if testing connector-auth flows.
- Do not put real phone numbers, tokens, API keys, contact files, Signal state,
  or iMessage database copies into git.
- For iMessage, use a logged-in macOS Aqua session. LaunchAgents that interact
  with Messages should not be expected to work headlessly.
- Grant any required macOS privacy permissions deliberately, especially Full
  Disk Access or Automation permissions if native message reads/sends require
  them.
- Adjust LaunchAgent paths if using a username other than `freyja`; existing
  plists reference `/Users/freyja/...`.

## 8. Important Context and Decisions That Must Not Be Lost

- Mars is the Director and control plane.
- Atlas is the always-on Signal/infrastructure node.
- Hera is useful and important for complex local reasoning, but is deliberately
  not core always-on infrastructure.
- Iris is the fast local inference tier.
- All user-facing connectors should forward into the Director instead of
  making independent routing decisions.
- Signal is preferred for secure remote control.
- Telegram is not the primary secure control path.
- Identity is a shared service, not a parallel Director.
- Known people should use canonical `Person` records and stable memory
  principals, not raw phone numbers or email addresses.
- Connectors authorize platform senders first, then pass sanitized identity
  context to the Director.
- Calendar scheduling logic should work in canonical person IDs where possible;
  provider account IDs remain provider data.
- Explicit user instructions outrank memory-derived preferences.
- OpenRouter fallback is allowed only when configured, allowlisted, and within
  budget.
- Agent Smith write actions must remain policy-gated and approval-gated.
- Keep populated `.env`, account state, contact data, and private IDs out of
  git.

## 9. Proposed Project Structure and Docs to Backfill

The existing structure is close. The next cleanup should make operational docs
more discoverable and separate architecture from runbooks.

Proposed structure:

```text
freyja-os/
  README.md
  ARCHITECTURE.md
  ROADMAP.md
  CONTRIBUTING.md
  SECURITY.md
  pyproject.toml
  .env.example
  src/freyja/
    main.py
    router.py
    config.py
    agents/
    calendar/
    identity/
    memory/
    tools/
  connectors/
    signal/
    imessage/
    telegram/
  certification/
    README.md
    suites/
    reports/
  deploy/
    docker/
    compose/
      director/
      signal/
  docs/
    WHERE_WE_LEFT_OFF.md
    CURRENT_STATUS.md
    SETUP_MACBOOK.md
    OPERATIONS.md
    HOST_ROLES.md
    IDENTITY_ARCHITECTURE.md
    CONTACTS_SYNC_PLAN.md
    SIGNAL_RUNBOOK.md
    IMESSAGE_RUNBOOK.md
    AGENT_SMITH_RUNBOOK.md
    SECURITY_MODEL.md
    DECISIONS/
      0001-host-roles.md
      0002-canonical-identity.md
      0003-connector-auth.md
      0004-cloud-fallback-policy.md
  tests/
  scripts/
  config/
  data/
  logs/
```

Backfill these docs first:

1. `docs/CURRENT_STATUS.md`
2. `docs/SETUP_MACBOOK.md`
3. `docs/HOST_ROLES.md`
4. `docs/IDENTITY_ARCHITECTURE.md`
5. `docs/CONTACTS_SYNC_PLAN.md`
6. `docs/SIGNAL_RUNBOOK.md`
7. `docs/IMESSAGE_RUNBOOK.md`
8. `docs/AGENT_SMITH_RUNBOOK.md`
9. `docs/DECISIONS/0001-host-roles.md`
10. `docs/DECISIONS/0002-canonical-identity.md`

## 10. Copyable Contents for Essential Missing Documents

The repository already has README, architecture, roadmap, and handoff docs, but
the following copyable versions can be used to refresh or backfill concise
operator-facing docs.

### Copyable `docs/CURRENT_STATUS.md`

```markdown
# Freyja-OS Current Status

**Updated:** 2026-08-03
**Branch:** main
**Latest verified commit:** 15ca096 Add canonical identity service
**Verification:** pytest passed with 629 passed, 4 skipped

## Current Phase

Freyja-OS is in the Identity Service phase. The core Director, Router, Memory,
Certification, Communications, Family Calendar, and Agent Smith foundations are
present. The current milestone is making `Person` the canonical representation
for people across messaging, memory, calendar, tools, and future voice/avatar
interfaces.

## Completed

- FastAPI Director and `/route` flow.
- Ollama and OpenRouter provider adapters.
- Local-first routing with cloud fallback controls.
- Memory principals and shared memory.
- Canonical identity service.
- Signal, iMessage, and Telegram connector foundations.
- Family Calendar service and tools.
- Agent Smith dry-run/read-only/write-pilot foundations.
- Certification CLI, suites, reports, benchmark, and runtime evidence.
- Mars/Atlas/Hera/Iris Rev 1 host-role documentation.

## In Progress

- Persistent contact source for identity.
- Production deployment validation across Mars, Atlas, Hera, and Iris.
- Signal account linking and allowlist review.
- MacBook-native iMessage setup.
- Operational runbooks and ADR backfill.

## Blockers

- Push local commits if not already pushed.
- Configure strong shared `FREYJA_CONNECTOR_TOKEN`.
- Link/register Signal manually on Atlas.
- Configure approved sender allowlists.
- Configure OpenRouter credentials only if cloud fallback is required.
- Confirm Hera and Iris model reachability from Mars.
```

### Copyable `docs/SETUP_MACBOOK.md`

~~~markdown
# MacBook Pro Setup

## Prerequisites

Install command-line tools and dependencies:

```bash
xcode-select --install
brew install git python docker ollama
```

## Clone and Install

```bash
git clone git@github.com:smokinjoev/freyja-os.git ~/freyja-os
cd ~/freyja-os
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
pytest
```

## Local Configuration

```bash
cp .env.example .env
chmod 600 .env
```

Do not commit `.env`, phone numbers, API keys, account state, contact exports,
or message database copies.

## Local Director

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn freyja.main:app --host 127.0.0.1 --port 8000 --reload
curl --fail http://127.0.0.1:8000/health
```

## Local Ollama

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
curl --fail http://127.0.0.1:11434/api/tags
```

Use Hera and Iris tailnet endpoints in `.env` when testing production routing.
~~~

### Copyable `docs/HOST_ROLES.md`

```markdown
# Freyja-OS Host Roles

## Mars

Mars is the Director and control-plane host. It owns routing, policy,
connector authentication, memory APIs, tool orchestration, OpenRouter access,
and provider fallback behavior.

## Atlas

Atlas is the always-on infrastructure host and Signal connector host. It should
run the Signal REST wrapper and Freyja Signal connector. It forwards authorized
requests to Mars and does not make independent routing decisions.

## Hera

Hera is the complex local reasoning provider over Tailscale, currently intended
for `gpt-oss:20b`. Hera is not core always-on infrastructure. Mars must handle
Hera outages cleanly.

## Iris

Iris is the fast local inference tier for low-latency local model work.

## Rule

No connector or worker should accept arbitrary public commands. External input
must enter through an approved connector and flow to the Director.
```

### Copyable `docs/IDENTITY_ARCHITECTURE.md`

```markdown
# Identity Architecture

Freyja identity centers on canonical `Person` records. Raw platform addresses
such as phone numbers, email addresses, Signal IDs, iMessage handles, and
calendar owner IDs are identities attached to a person, not the person itself.

## Current Model

- `Person`: canonical household or trusted person.
- `Identity`: platform-specific address or account identifier.
- `Alias`: human-friendly name used in configs and requests.
- `Relationship`: directed relationship edges such as spouse or child.

## Connector Flow

1. Connector receives a platform message.
2. Connector enforces platform allowlist.
3. Connector resolves sender to `Person` when possible.
4. Connector passes sanitized identity headers to the Director.
5. Director derives memory principal and person context from headers.
6. Router and tools act on canonical context.

## Decisions

- Known people should not be stored in memory as raw phone numbers or emails.
- Identity is a shared service, not a separate Director.
- Calendar providers keep provider account IDs, but scheduling works in
  canonical person IDs where practical.

## Next Work

Implement persistent contact import/sync from Google Contacts, Apple Contacts,
or an encrypted local contact file.
```

### Copyable `docs/CONTACTS_SYNC_PLAN.md`

```markdown
# Contacts Sync Plan

## Goal

Replace seeded in-code identity data with a durable contact source while
keeping private contact data out of git.

## First Decision

Choose the first canonical source:

- Google Contacts
- Apple Contacts
- Encrypted local YAML or SQLite contact file

## Proposed Interface

Create a contact provider interface that returns canonical people, identities,
aliases, and relationships without exposing provider-specific details to the
Director.

## Acceptance Criteria

- Tests use fake contact providers.
- Raw contact exports are ignored by git.
- Identity resolution remains stable across Signal, iMessage, calendar, and
  memory.
- Existing legacy allowlist syntax still works.
- Duplicate contacts can be detected and reported.
```

### Copyable `docs/SIGNAL_RUNBOOK.md`

~~~markdown
# Signal Runbook

Signal is the primary secure remote connector. In Rev 1, Atlas runs the Signal
REST wrapper and Freyja Signal connector. Mars runs the Director.

## Configure Atlas

```bash
cd ~/freyja-os
cp deploy/compose/signal/.env.example deploy/compose/signal/.env
chmod 600 deploy/compose/signal/.env
```

Set:

- `FREYJA_DIRECTOR_URL=http://<mars-tailscale-host>:8000`
- `FREYJA_CONNECTOR_TOKEN=<same-token-as-mars>`
- `SIGNAL_ENABLED=false` until account linking and allowlist review are done
- `SIGNAL_ACCOUNT_NUMBER=<reviewed-e164-number>`
- `SIGNAL_ALLOWED_SENDERS=<reviewed-e164-or-alias-map>`

## Validate

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml config
curl --fail http://<mars-tailscale-host>:8000/health
```

## Start

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml up -d --build
```

Do not commit Signal account state, phone numbers, or populated `.env` files.
~~~

### Copyable `docs/IMESSAGE_RUNBOOK.md`

~~~markdown
# iMessage Runbook

iMessage is the Apple-native secondary connector. It requires a macOS host with
an interactive Aqua session and appropriate Messages permissions.

## Setup

```bash
cd ~/freyja-os
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
chmod 600 .env
```

Set:

- `FREYJA_CONNECTOR_TOKEN`
- `IMESSAGE_ALLOWED_SENDERS`
- Director URL expected by the connector runner

## LaunchAgent

Use `scripts/com.freyja-os.imessage-connector.plist` as a template. Update all
paths if the runtime path is not `/Users/freyja/freyja-os-imessage-runtime`.

Do not assume iMessage automation works headlessly. Test from the logged-in Mac
session before relying on it.
~~~

### Copyable `docs/AGENT_SMITH_RUNBOOK.md`

~~~markdown
# Agent Smith Runbook

Agent Smith is the maintenance orchestrator. It can inspect, plan, execute,
validate, retry, escalate, and summarize work through policy-controlled tools.

## Modes

- Dry-run: planning and simulated execution.
- Read-only: inspect and report without writes.
- Write-pilot: limited write actions with policy and approval gating.

## Safety Defaults

All Agent Smith modes are disabled by default. Write-pilot tools are enabled
only when both `AGENT_SMITH_ENABLED=true` and
`AGENT_SMITH_WRITE_PILOT_ENABLED=true`.

## State

Approval state defaults to:

```text
~/.local/state/freyja/smith-approvals.sqlite3
```

Audit log defaults to:

```text
logs/agent-smith-audit.jsonl
```

## Rule

Do not enable write-pilot in production until the policy file, approval flow,
audit log, and rollback expectations have been reviewed.
~~~

### Copyable `docs/DECISIONS/0001-host-roles.md`

```markdown
# Decision 0001: Rev 1 Host Roles

## Status

Accepted.

## Decision

- Mars is the Director and control plane.
- Atlas is always-on infrastructure and Signal connector host.
- Hera is complex local reasoning over Tailscale, not always-on control-plane
  infrastructure.
- Iris is the fast local inference tier.

## Consequences

Connectors and workers forward to Mars. Mars must tolerate Hera being
unavailable and use fallback or explicit provider failure. Signal runs on Atlas
but does not own routing.
```

### Copyable `docs/DECISIONS/0002-canonical-identity.md`

```markdown
# Decision 0002: Canonical Identity

## Status

Accepted.

## Decision

Freyja uses canonical `Person` records for known people. Platform addresses are
attached identities, not memory subjects.

## Consequences

Signal, iMessage, calendar, memory, and future voice/avatar integrations should
resolve known users to `Person` where possible. Legacy raw-address allowlists
remain supported for compatibility, but long-term preferences and memory should
attach to stable person-backed principals.
```
