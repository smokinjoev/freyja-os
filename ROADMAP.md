# Freyja-OS GitHub Roadmap

**Roadmap version:** 0.1  
**Project stage:** Foundation  
**Primary objective:** Secure local-first AI access through Signal with controlled cloud escalation

## Roadmap Conventions

### Priority

- **P0:** Required for the first usable release
- **P1:** Important after the core path is stable
- **P2:** Useful expansion
- **P3:** Experimental or long-term

### Status

- `Backlog`
- `Ready`
- `In Progress`
- `Blocked`
- `Done`

### Suggested GitHub Labels

```text
priority:P0
priority:P1
priority:P2
priority:P3
area:director
area:gateway
area:signal
area:telegram
area:imessage
area:ollama
area:openrouter
area:memory
area:security
area:infrastructure
area:worker
area:voice
area:vision
area:home-assistant
type:feature
type:bug
type:security
type:documentation
type:maintenance
status:blocked
good-first-issue
```

---

# Milestone 0 — Repository Foundation

**Goal:** Establish a clean repository, development standards, and documented architecture.

**Target release:** `v0.0.1`

## Issues

### P0 — Create base repository structure

**Acceptance criteria:**

- Directory structure matches `ARCHITECTURE.md`
- Python package exists under `src/freyja`
- Tests directory exists
- Connector and worker directories exist

### P0 — Add project documentation

Files:

- `README.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `CONTRIBUTING.md`
- `SECURITY.md`

### P0 — Add Python project configuration

Recommended files:

- `pyproject.toml`
- `.python-version`
- `ruff.toml` or Ruff configuration in `pyproject.toml`
- Type checking configuration

### P0 — Add secret protection

**Acceptance criteria:**

- `.env` is ignored
- `.env.example` exists
- API keys are loaded only from environment variables
- Secret scanning is enabled in GitHub where available

### P1 — Add automated checks

GitHub Actions workflow for:

- Linting
- Type checking
- Unit tests
- Secret detection

### P1 — Add issue and pull request templates

Templates:

- Bug report
- Feature request
- Security concern
- Pull request checklist

---

# Milestone 1 — Director Skeleton

**Goal:** Run a local Freyja Director API with provider-independent request and response models.

**Target release:** `v0.1.0-alpha.1`

## Issues

### P0 — Implement FastAPI service

Endpoints:

- `GET /health`
- `POST /v1/chat`
- `GET /v1/providers`
- `GET /v1/status`

### P0 — Define normalized request and response schemas

Include:

- Request ID
- User ID
- Source
- Conversation ID
- Message
- Attachments
- Permissions
- Provider and model metadata
- Latency and estimated cost

### P0 — Add structured logging

Required fields:

- Request ID
- Timestamp
- Provider
- Model
- Latency
- Outcome
- Error category

### P0 — Add configuration system

Configuration should support:

- Local Ollama URL
- OpenRouter API key
- Provider enable or disable flags
- Default models
- Timeout values
- Monthly budget
- Logging level

### P1 — Add service health registry

Track:

- Director health
- Ollama health
- OpenRouter reachability
- Database health

### P1 — Add local administrative CLI

Initial commands:

- Show configuration
- Test provider
- Show current budget usage
- Enable or disable cloud routing

---

# Milestone 2 — Ollama Integration

**Goal:** Complete local inference through one or more Ollama models.

**Target release:** `v0.1.0-alpha.2`

## Issues

### P0 — Implement Ollama provider adapter

Functions:

- List models
- Check model availability
- Send chat request
- Stream response
- Return timing and token metadata

### P0 — Define initial local model profiles

Each profile should include:

- Model name
- Context limit
- Tool support
- Expected memory use
- Task strengths
- Node location

### P0 — Add model timeout and fallback behavior

Fallback example:

```text
primary local model -> alternate local model -> error response
```

### P0 — Validate Mac mini resource limits

Document:

- Models that run reliably on 24 GB unified memory
- Expected response speed
- Maximum practical context
- Concurrency limit

### P1 — Add remote Ollama node support

Support Ollama running on another private-network node.

### P1 — Add local model benchmark script

Measure:

- Tokens per second
- Time to first token
- Total latency
- Peak memory
- Tool-call formatting accuracy

---

# Milestone 3 — OpenRouter Integration

**Goal:** Add controlled cloud escalation and cost accounting.

**Target release:** `v0.1.0-alpha.3`

## Issues

### P0 — Implement OpenRouter provider adapter

Functions:

- Send chat request
- Select model
- Parse provider response
- Record usage
- Estimate request cost
- Handle provider errors

### P0 — Add model allowlist

The Director must use only explicitly approved OpenRouter models.

### P0 — Add monthly budget configuration

Initial controls:

- Monthly soft limit
- Monthly hard limit
- Per-request cost limit
- Cloud-disable switch

### P0 — Add budget alerts

Thresholds:

- 50%
- 75%
- 90%
- 100%

### P1 — Add cloud fallback chain

Example:

```text
preferred low-cost model
  -> alternate low-cost model
  -> stronger approved model
  -> local fallback
```

### P1 — Add provider usage report

Report fields:

- Requests by model
- Tokens by model
- Cost by model
- Average latency
- Failed requests

---

# Milestone 4 — Routing Policy

**Goal:** Automatically choose local or cloud inference based on policy.

**Target release:** `v0.1.0-beta.1`

## Issues

### P0 — Implement manual routing override

Supported modes:

- `local`
- `cloud`
- `auto`

### P0 — Implement rule-based automatic router

Initial signals:

- Message length
- Requested task type
- Need for tools
- Context size
- Privacy classification
- Local model health
- Budget availability

### P0 — Add privacy routing rules

Sensitive household or personal data should default to local processing when the local model can complete the task.

### P0 — Add routing audit record

Record:

- Chosen provider
- Chosen model
- Routing reason
- Estimated cost
- Fallbacks attempted

### P1 — Add quality-based retry

The Director may retry using a stronger model when:

- Output is malformed
- Required tool call is missing
- Confidence checks fail
- User explicitly requests escalation

### P2 — Add learned routing policy

Use historical success, latency, and cost data to improve routing. This is deferred until sufficient real usage data exists.

---

# Milestone 5 — Signal Gateway

**Goal:** Provide secure, authorized phone access through Signal.

**Target release:** `v0.1.0-beta.2`

## Issues

### P0 — Select Signal bridge implementation

Evaluate:

- `signal-cli`
- REST wrapper around `signal-cli`
- Containerized deployment options

Decision criteria:

- Maintained status
- Linux compatibility
- Attachment support
- Operational reliability
- Security model

### P0 — Provision dedicated Signal identity

Document:

- Phone number or account strategy
- Device registration
- Backup and recovery procedure

### P0 — Implement sender allowlist

Default behavior:

- Accept only Joe's approved Signal identity
- Reject unknown senders
- Ignore groups
- Log authorization failures without storing message contents

### P0 — Implement Signal inbound adapter

Convert Signal messages into normalized Freyja requests.

### P0 — Implement Signal outbound adapter

Return:

- Text responses
- Error responses
- Long-message splitting
- Attachment references where supported

### P0 — Add gateway rate limiting

Rate limits should apply per sender and per source.

### P1 — Add attachment handling

Initial supported types:

- Images
- Plain text
- PDF metadata and storage handoff

### P1 — Add gateway health monitoring

Detect:

- Signal bridge offline
- Registration failure
- Message queue backlog
- Director unreachable

---

# Milestone 6 — First Usable Release

**Goal:** Complete and validate the end-to-end Freyja v0.1 pipeline.

**Target release:** `v0.1.0`

## Required End-to-End Path

```text
Signal
  -> Gateway
  -> Director
  -> Ollama or OpenRouter
  -> Director
  -> Signal
```

## Release Acceptance Criteria

- Authorized Signal message receives a response
- Unknown Signal sender is rejected
- Local Ollama routing works
- OpenRouter routing works
- Automatic routing works
- Cloud routing can be disabled
- Request logs show provider, model, latency, and estimated cost
- Services recover after restart
- Installation procedure is documented
- Backup procedure for configuration and secrets is documented
- No internal model or database service is publicly exposed

## Validation Issues

### P0 — Add end-to-end integration test

### P0 — Add restart recovery test

### P0 — Add unauthorized sender test

### P0 — Add cloud budget limit test

### P0 — Add local provider failure test

### P0 — Write installation and recovery runbook

---

# Milestone 7 — Persistent Memory

**Goal:** Add controlled short-term and long-term memory.

**Target release:** `v0.2.0`

## Issues

### P0 — Deploy PostgreSQL on Atlas

### P0 — Define memory data model

Categories:

- User preference
- Device
- Project decision
- Contact
- Task state
- Document reference

### P0 — Implement explicit memory write tool

Memory writes should require:

- Defined category
- Source
- Confidence
- Timestamp
- Retention policy

### P0 — Implement memory search tool

### P1 — Deploy vector search

Select:

- pgvector
- Qdrant

### P1 — Add document ingestion pipeline

### P1 — Add memory review and deletion interface

### P1 — Add memory privacy classification

---

# Milestone 8 — Capability Registry and Tools

**Goal:** Add controlled tool invocation.

**Target release:** `v0.3.0`

## Issues

### P0 — Implement capability registry

### P0 — Define tool permission model

### P0 — Add tool-call audit log

### P0 — Add tool timeout and retry policies

### P1 — Add file read capability

### P1 — Add restricted file write capability

### P1 — Add web search capability

### P1 — Add notification capability

### P2 — Add code execution sandbox

Code execution must not run directly on the Director host without isolation.

### P2 — Add MCP service adapter

---

# Milestone 9 — Worker Node Framework

**Goal:** Use older computers as managed capability workers.

**Target release:** `v0.4.0`

## Issues

### P0 — Define worker registration protocol

Worker metadata:

- Node ID
- Hostname
- Capabilities
- CPU
- RAM
- GPU
- Operating system
- Health
- Current load

### P0 — Implement worker heartbeat

### P0 — Implement authenticated task dispatch

### P0 — Implement result return and timeout handling

### P1 — Add NUCBox utility worker

### P1 — Add document conversion worker

### P1 — Add speech transcription worker

### P1 — Add vision worker

### P2 — Add automatic worker selection

---

# Milestone 10 — Voice and Avatar

**Goal:** Connect the avatar computer as a controlled Freyja interface.

**Target release:** `v0.5.0`

## Issues

### P0 — Implement avatar client protocol

### P0 — Add microphone input pipeline

### P0 — Add speech-to-text service

### P0 — Add text-to-speech service

### P1 — Add wake-word detection

### P1 — Add interruption handling

### P1 — Add avatar state and animation events

### P2 — Add camera-based presence detection

### P2 — Add local vision requests

---

# Milestone 11 — Home Assistant Integration

**Goal:** Add safe home automation through explicit capabilities.

**Target release:** `v0.6.0`

## Issues

### P0 — Add Home Assistant API adapter

### P0 — Define allowed entity list

### P0 — Define low-risk and high-risk actions

### P0 — Require confirmation for high-risk actions

Examples:

- Door locks
- Alarm systems
- Garage doors
- Security modes

### P1 — Add natural-language status queries

### P1 — Add routine execution

### P1 — Add event notifications

### P2 — Add Cloyd edge-node integration

---

# Milestone 12 — iMessage Interface

**Goal:** Add Apple-native messaging after the Signal path is stable.

**Target release:** `v0.7.0`

## Issues

### P0 — Select iMessage bridge

Evaluate:

- BlueBubbles
- AppleScript or Shortcuts
- Controlled Messages database watcher

### P0 — Implement sender allowlist

### P0 — Implement inbound and outbound adapters

### P1 — Add attachment support

### P1 — Add bridge recovery monitoring

---

# Milestone 13 — Operations and Hardening

**Goal:** Make Freyja-OS maintainable and resilient.

**Target release:** `v1.0.0-rc.1`

## Issues

### P0 — Add automated backups

Back up:

- PostgreSQL
- Vector database
- Configuration
- Documentation
- Non-secret service state

### P0 — Add restore test

### P0 — Add centralized monitoring dashboard

### P0 — Add service alerting

### P0 — Add dependency update process

### P0 — Add security review checklist

### P1 — Add container image scanning

### P1 — Add audit-log retention policy

### P1 — Add disaster recovery runbook

### P1 — Add node replacement procedure

---

# Milestone 14 — Freyja-OS 1.0

**Goal:** Stable personal AI orchestration platform with secure messaging, local and cloud routing, memory, tools, and managed workers.

**Target release:** `v1.0.0`

## Release Criteria

- Signal is stable as the primary remote interface
- Local Ollama and OpenRouter routing are reliable
- Monthly cloud budget controls are enforced
- Memory is reviewable and deletable
- Tool permissions are enforced
- Worker nodes are authenticated
- Backups and restores are tested
- Critical services are monitored
- Installation and operations are documented
- High-risk actions require confirmation
- No core service requires public internet exposure

---

# Initial GitHub Project Board

Recommended columns:

```text
Backlog
Ready
In Progress
Review
Blocked
Done
```

Recommended initial cards, in order:

1. Create repository structure
2. Add architecture and roadmap documents
3. Add Python project configuration
4. Add `.env.example` and secret protections
5. Implement FastAPI health endpoint
6. Define request and response schemas
7. Implement Ollama provider adapter
8. Implement OpenRouter provider adapter
9. Add manual local/cloud routing
10. Add structured request logging
11. Add monthly cloud budget controls
12. Select Signal bridge
13. Implement Signal sender allowlist
14. Implement Signal inbound adapter
15. Implement Signal outbound adapter
16. Run end-to-end Signal test
17. Tag `v0.1.0`

---

# Immediate Sprint — Sprint 1

**Sprint objective:** Establish the repository and prove local inference through the Director.

## Sprint 1 Tasks

### Task 1 — Repository setup

- Create base directories
- Add documentation
- Add `.gitignore`
- Add `.env.example`
- Add `pyproject.toml`

### Task 2 — Director API

- Create FastAPI application
- Add `/health`
- Add `/v1/chat`
- Add Pydantic schemas

### Task 3 — Ollama adapter

- Configure Ollama base URL
- Send one chat request
- Return normalized response
- Record latency

### Task 4 — Tests

- Health endpoint test
- Request schema test
- Ollama adapter test with mocked response

## Sprint 1 Definition of Done

From a local terminal, the following must work:

```text
POST /v1/chat
  -> Freyja Director
  -> Ollama
  -> normalized JSON response
```

---

# Immediate Sprint — Sprint 2

**Sprint objective:** Add OpenRouter and routing controls.

## Sprint 2 Tasks

- OpenRouter adapter
- Model allowlist
- Manual `local`, `cloud`, and `auto` modes
- Estimated cost logging
- Monthly budget configuration
- Local fallback when cloud is disabled

## Sprint 2 Definition of Done

The same `/v1/chat` endpoint can route to either Ollama or OpenRouter and records the routing decision.

---

# Immediate Sprint — Sprint 3

**Sprint objective:** Connect Signal and complete Freyja-OS v0.1.

## Sprint 3 Tasks

- Deploy Signal bridge on an always-on node
- Configure dedicated Signal identity
- Implement authorized sender allowlist
- Connect inbound messages to the Director
- Return responses through Signal
- Add restart recovery
- Write operations runbook

## Sprint 3 Definition of Done

Joe sends a Signal message from his phone and receives a Freyja response produced by local Ollama or OpenRouter.
