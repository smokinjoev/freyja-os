# Rev 2 Implementation Plan

**Date:** 2026-08-16  
**Status:** prepared; implementation not yet started  
**Architecture:** `ARCHITECTURE.md` v0.2 Rev 2

## Goal

Move Freyja from the Rev 1 single-local-provider / Mars-control-plane assumptions to the Rev 2 architecture:

- Atlas = authoritative Director/control plane
- Iris = MacAgent + always-hot approximately 7B route/reflex model
- new inference machine = heavy local reasoning provider
- Hera = presence/avatar/development/experimental node
- Mars = utility/fallback node
- Director = final routing and authorization authority

The migration must preserve working messaging, memory, identity, certification, and tool behavior while provider routing is refactored underneath them.

---

## Current Code Observations

### Configuration is still single-Ollama-host oriented

`src/freyja/config.py` currently exposes one `ollama_base_url` and model-name fields for chat, classification, and reasoning. Rev 2 needs named inference hosts/provider profiles rather than assuming all Ollama roles share one endpoint.

### Router already has useful separation to build on

`src/freyja/router.py` already has:

- `RouteRequest`
- `RoutingDecision`
- privacy classification
- routine/cloud/local-reasoning scoring
- runtime evidence
- provider/client registration
- explicit tool registry integration

Rev 2 should evolve these boundaries instead of replacing the router wholesale.

### Existing route policy is task-type and heuristic based

The current router contains deterministic scoring for routine, cloud, and local reasoning work. Keep this as a safe fallback even after Iris-based route classification is introduced.

---

## Workstream A — Host and Deployment Alignment

### A1. Atlas Director target

Audit and update deployment/documentation references that still identify Mars as Director.

Targets likely include:

- `README.md`
- `ROADMAP.md`
- `docs/REV1_STATUS.md` (retain as historical; do not rewrite history)
- `deploy/compose/**`
- connector `.env.example` files
- operations/handoff docs

Desired invariant:

- all active connectors target the Atlas Director URL
- no current deployment example tells an operator to deploy Director on Mars

### A2. Preserve Rev 1 history

Do not rewrite `docs/REV1_STATUS.md` as if Rev 1 never existed. Add Rev 2 status documents and mark Rev 1 superseded where necessary.

---

## Workstream B — Provider Registry

### B1. Introduce provider profile model

Add a model similar to:

```python
class InferenceProviderProfile(BaseModel):
    provider_id: str
    kind: str
    base_url: str
    model: str
    capabilities: set[str]
    locality: str
    priority: int = 100
    enabled: bool = True
```

Possible initial registrations:

- `iris_router`
- `iris_chat`
- `heavy_local`
- `openrouter_frontier`

Do not encode hostnames into business logic.

### B2. Add health/readiness model

Track separately:

- host reachable
- provider endpoint healthy
- model present
- model warm/resident when detectable
- last successful inference
- observed latency

A host being reachable must not imply that its model is ready.

### B3. Maintain backward compatibility

During migration, continue accepting the existing `OLLAMA_BASE_URL` and model environment variables and translate them into a default legacy provider profile.

This keeps current tests and deployments working while Rev 2 provider configuration is introduced.

---

## Workstream C — Iris 7B Route Classifier

### C1. Structured classifier contract

Introduce a strict response model:

```python
class RouteClassification(BaseModel):
    task_type: str
    complexity: int
    sensitivity: str
    needs_tools: bool
    preferred_tier: int
    confidence: float
```

Use `extra="forbid"` and validate bounds.

### C2. Advisory-only rule

Classifier output may influence routing but must not contain or grant permissions.

The Director must ignore any classifier attempt to provide fields such as:

- allowed tools
- permissions
- principal identity
- approval state
- memory scope

### C3. Confidence threshold

If classifier output is invalid, unavailable, times out, or falls below the configured confidence threshold, fall back to the deterministic routing logic already present in `router.py`.

### C4. Model residency

Iris should keep the chosen approximately 7B classifier/reflex model resident.

Add configuration for:

- classifier provider ID
- classifier timeout
- classifier confidence threshold
- warmup enabled
- keep-alive/residency preference

Do not make Director startup depend on successful Iris warmup.

---

## Workstream D — Tiered Routing

Add an explicit tier to routing decisions.

Suggested enum:

```text
0 deterministic/direct
1 Iris hot 7B
2 stronger routine local
3 heavy local reasoning
4 cloud/frontier
```

### Routing order

1. deterministic/direct capability when exact handling is available
2. Iris classifier when model classification is useful
3. Director applies privacy, identity, tool, health, cost, and policy constraints
4. select the lowest tier likely to complete the task reliably
5. escalate only on explicit need or failed/low-confidence result

### Important rule

Do not send every request through Iris just because Iris is available. Exact deterministic tool paths should remain faster than model classification.

---

## Workstream E — Runtime Evidence and Latency

Extend `RuntimeEvidence` and/or routing metadata with:

- selected tier
- classifier provider/model
- classifier confidence
- classifier latency
- provider readiness state
- model warm/cold state when known
- time to first token
- total provider latency
- escalation reason

This data is required to prove that Rev 2 actually improves first-question latency.

---

## Workstream F — MacAgent Boundary

MacAgent runs on Iris and exposes Apple-native capabilities behind an authenticated internal API.

Initial capability families:

- `apple.messages.*`
- `apple.calendar.*`
- `apple.contacts.*`
- `apple.shortcuts.*`

MacAgent responsibilities:

- native macOS interaction
- provider-specific normalization
- health reporting
- safe error handling

Atlas responsibilities:

- principal identity
- authorization
- approval policy
- memory policy
- final tool dispatch decision

MacAgent must not treat local network origin as authorization.

---

## Workstream G — Capability Broker

The existing tool registry remains useful but Rev 2 should make authorization explicit before execution.

Add a policy step that evaluates at minimum:

- acting principal
- requested capability
- target resource/person scope
- read/write/consequential classification
- required approval
- connector/source trust

The LLM/tool-call loop may propose a capability invocation but cannot approve it.

---

## Workstream H — Trust-Aware External Workers

Create a boundary for untrusted-content processing.

Candidate worker classes:

- web research
- arbitrary email content
- arbitrary document ingestion
- scraping

Default capability set for such workers should exclude:

- memory authoritative write
- message send
- home control
- administrative configuration
- privileged shell/code execution

Return structured observations to Director for interpretation.

---

## Workstream I — Memory Provenance

Extend shared/long-term memory with provenance and trust metadata without breaking existing memory APIs.

Minimum target fields:

- source type
- source ID
- trust level
- confidence
- observed timestamp
- sensitivity
- derivation links where practical

Add a distinction between:

- observation
- user-confirmed fact
- trusted-system fact
- derived fact

External-content observations should not automatically become authoritative facts.

---

## Workstream J — Certification

Add a Rev 2 certification suite before changing production routing defaults.

Minimum cases:

1. deterministic Home Assistant-style request bypasses heavy inference
2. routine chat selects Iris Tier 1 when healthy
3. hard coding request selects Tier 3 heavy local
4. Iris unavailable falls back to deterministic router logic
5. classifier malformed JSON fails safely
6. low classifier confidence fails safely
7. classifier-proposed permission field is rejected/ignored
8. heavy local unavailable falls back according to policy
9. cloud disabled prevents Tier 4
10. sensitive memory is not included in cloud context by default
11. MacAgent consequential request requires Director authorization
12. unknown principal cannot use private Apple capability
13. untrusted web content cannot invoke privileged tools
14. untrusted web content cannot directly create authoritative memory
15. model cold-start and warm-start latency are measured separately

---

## Suggested Code Order

1. Add provider profile/readiness models with no routing behavior change.
2. Add configuration compatibility layer for legacy Ollama settings.
3. Add provider registry and health checks.
4. Add routing tier field to `RoutingDecision` and runtime evidence.
5. Add Iris classifier client and strict response model.
6. Add classifier fallback to existing deterministic heuristics.
7. Add Tier 0-4 selection policy.
8. Add latency/readiness telemetry.
9. Add MacAgent capability boundary.
10. Harden capability authorization.
11. Add memory provenance/trust metadata.
12. Add isolated external-content workers.
13. Run full certification before changing production defaults.

---

## Deployment Strategy

Do not cut over everything at once.

### Stage 1 — shadow classification

Director sends eligible requests to Iris classifier but does not use its answer for routing. Record what Iris would have chosen and compare with current routing/certification expectations.

### Stage 2 — advisory routing

Use Iris classification only when confidence is high and deterministic policy agrees that the proposed tier is allowed.

### Stage 3 — Rev 2 default

Enable tiered routing as the default after certification and latency measurements show improvement.

### Stage 4 — heavy-local cutover

Make the new inference machine the preferred Tier 3 provider once its endpoint/model/health checks are stable.

---

## Success Metrics

Rev 2 routing should improve:

- first-request latency
- time to first token
- percentage of requests handled without heavy-model activation
- local inference utilization
- cloud spend
- failover behavior
- route explainability

It must not regress:

- sender authorization
- memory isolation
- messaging delivery
- tool safety
- Director availability
- certification pass rate

---

## Immediate Next Coding Slice

The safest first implementation slice is deliberately small:

1. add `InferenceProviderProfile`, provider capability tags, and readiness state
2. add a provider registry that can represent Iris, heavy-local, and OpenRouter
3. preserve current single-Ollama behavior through a compatibility registration
4. add tests only; do not change production routing yet

After that passes the full suite, add Iris shadow classification.
