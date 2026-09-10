# Freyja 5.1 Architecture

Status: draft for review.

Freyja 5.1 is the household agent system built around persistent family agents,
local-first inference, scoped memory, and strict tool authority. The original
5.0 plan was directionally correct: keep identity, memory, tools, routing, and
inference as separate boundaries. The final shape is less Msty-only and more
service-oriented because live testing showed OpenWebUI, Freyja5 Gateway, Iris,
and Vulcan each need clear jobs.

## Executive Summary

Freyja 5.1 should use this split:

| Plane | Final role |
| --- | --- |
| Atlas | Always-on policy, identity, memory, audit, OpenWebUI, Freyja5 Gateway, Home Assistant/tool boundary |
| Iris | Apple/Mac body, MacAgent, hot 7B reflex model, read-only fast observations |
| Vulcan | Heavy local compute: 20B/30B/32B/72B/coder/vision/long-context models |
| Hera | Voice/avatar/presence edge, later semantic perception |
| OpenWebUI | Main family chat UI and agent surface |
| Msty Go | Useful specialist/native-agent UI, not the required Freyja 5.1 control plane |
| Nexus | Optional semantic model gateway; useful, but not required for the current OpenWebUI production path |

The final system should keep Atlas authoritative. Iris can be fast and locally
aware, but it must not become policy authority. Vulcan can be powerful, but it
must not own memory, identity, or tool grants.

## What Changed From The 5.0 Plan

The original 5.0 architecture in `docs/architecture/FREYJA-5.0-ARCHITECTURE.md`
said:

- Vulcan/Nexus owns semantic local presets and physical model selection.
- Atlas hosts Freyja Gateway, persistent agents, memory, audit, workers, and
  health APIs.
- Msty Go may replace or wrap the Atlas persistent-agent plane if it proves
  reliable.
- The Gateway must stay deterministic and must not become a Director.
- Agents request semantic routes such as `fast`, `general`, `deep`, `code`,
  `vision`, `embedding`, and `private`.

That plan remains valid as a boundary model, but the live path changed:

| Original expectation | Current finding | Final decision |
| --- | --- | --- |
| Msty Go could become the persistent agent plane | Msty Go works, but full prompts/tool arrays exposed model and grant issues | Keep Msty Go optional; Atlas/Freyja5 remains authority |
| Nexus required for semantic routing | OpenWebUI path works without Nexus through model-proxy and Freyja5 Gateway | Nexus is useful but not required for production OpenWebUI |
| `fast-local` could back persistent agents | 7B corrupts/refuses under large agent payloads | 7B is reflex-only, read-only, tightly scoped |
| `fast_chat` was 32B in one OpenWebUI config | Tests showed 32B is not fast; 20B is much faster but has output caveats | 20B minimum for study/general fast; 7B only reflex |
| Plain `qwen2.5:72b` could be the big default | It is clean for text but only 32k context | Use plain 72B for accurate text, VL 72B for PDFs/images/large context |
| GPT OSS models could be defaults | 20B/120B can return reasoning without visible content | Use only where proxy adapter and validation prove visible output |

## Final Model Policy

| Lane | Model | Host | Purpose | Guardrail |
| --- | --- | --- | --- | --- |
| Reflex | `qwen2.5:7b` | Iris | Simple household status, brief recall, MacAgent summaries | Read-only; no actions, writes, shell, admin, or global memory |
| Fast study/general | `gpt-oss-freyja:20b-analysis-prefill` | Vulcan | Minimum real study model, concise reasoning | Use only through adapter path that prevents blank visible replies |
| Accurate text | `qwen2.5:72b` | Vulcan | Slow, higher-quality text reasoning | 32k context; no vision |
| Vision/docs/large context | `qwen2.5vl:72b` | Vulcan | Photos, PDFs, charts, screenshots, long document sessions | Prefer for Liam pilot-study materials |
| Long-context experiment | `qwen3.8:27b` | Vulcan | 262k text-context testing | Not default until visible-output reliability is proven |
| Coding | `qwen3-coder-next:q4_K_M` | Vulcan | Cloyd/OpenCode/coding work | Separate from household chat |
| Experimental huge | `qwen3.5:122b-a10b`, `gpt-oss:120b` | Vulcan | Opt-in testing only | Not default; memory and output behavior are risky |

The system should prefer slow and accurate when the user asks for real reasoning,
study, aviation, legal, documents, or anything consequential. Speed belongs to
the reflex layer, not the serious-answer layer.

## Family Agents

The family-facing agent set is:

| Agent | Owner | Final role |
| --- | --- | --- |
| Freyja | Household | Primary household assistant, coordinator, memory/tool boundary |
| Cloyd | Joe | Technical/coding/infrastructure agent |
| Benedict | Beth | Beth personal and paralegal assistant, local-only for restricted work |
| Agent 44 | Liam | Study/pilot-training agent with memory and tutoring style |
| Jenna | Jenna | Age-appropriate personal assistant |

Agent 44 should use at least 20B for study. The 7B Iris reflex model can answer
simple status or recall questions, but it should not teach aviation concepts,
explain procedures, or handle college-level reasoning. For Liam's pilot path,
`qwen2.5vl:72b` is the preferred deep model because it can handle PDFs, charts,
diagrams, screenshots, and long study context.

## Iris 7B Leash

Iris now has `qwen2.5:7b` hot and resident. This is good, but it must stay on a
tight leash.

Allowed:

- Read-only MacAgent summaries.
- Calendar/status summaries when authorized.
- Simple home/status answers supplied through Atlas-approved tools.
- Short memory recall from permitted scopes.
- Routing/reflex classification.

Forbidden:

- Sending messages.
- Calendar writes.
- Running Shortcuts.
- Home device actions.
- Shell/admin/config changes.
- Cross-user private memory reads.
- Global memory writes.
- Raw unrestricted message bodies, files, or secrets.

If Iris 7B is uncertain, sees a consequential request, or needs broader
context, it must route upward to Atlas/Freyja and a stronger governed model.

## Tool And Memory Authority

Atlas owns:

- Identity resolution.
- Agent selection.
- Tool authorization.
- Home Assistant boundaries.
- Memory scope enforcement.
- Audit events.
- OpenWebUI/Freyja5 Gateway.
- Confirmation gates for writes/actions.

Iris owns capability access, not authorization. MacAgent can observe and execute
Apple-local operations, but Atlas grants or denies operations.

Vulcan owns compute only. It should not store household authority, decide
permissions, or bypass Atlas policy.

## UI And Runtime

OpenWebUI on Atlas is the main family UI. The current path is:

```text
browser/PWA
  -> Atlas OpenWebUI
  -> model-proxy / Freyja5 Gateway
  -> Vulcan or Iris, depending on model and route
```

The current OpenWebUI path does not require Nexus. Nexus remains valuable for
Msty Go and semantic presets, but Freyja 5.1 should not depend on Nexus for the
household UI to function.

Msty Go remains useful for specialist desktop agent workflows. It should not be
the only control plane unless it proves always-on reliability, recoverability,
and clean tool/memory behavior under full agent prompts.

## What Was Better In The Original Plan

The original plan was better about boundaries:

- Semantic route names are cleaner than exposing physical model IDs everywhere.
- Nexus-owned physical model selection is conceptually right.
- Gateway-not-Director is the right long-term discipline.
- MCP servers by capability host, not per agent, is correct.

Those principles should survive.

## What Is Better In The Current Path

The current path is better operationally:

- OpenWebUI on Atlas gives the family a real shared UI now.
- Freyja5 Gateway can expose agent model IDs directly.
- Atlas model-proxy can guard bad models and adapt reasoning output.
- Iris 7B hot reflex gives the system the fast local feel Joe wanted.
- Home Assistant and memory are now real tools in the Freyja5 path.
- Vulcan is free to be compute rather than authority.

## Final Direction

Adopt the hybrid architecture:

1. Keep Atlas as the household authority and OpenWebUI host.
2. Keep Iris as the hot reflex and Apple/MacAgent body.
3. Keep Vulcan as heavy local inference.
4. Keep Hera as the voice/avatar/perception edge.
5. Keep Nexus as an optional semantic gateway, not a required production
   dependency for OpenWebUI.
6. Keep Msty Go as an optional specialist/native-agent surface.
7. Promote model routing by lane, not by one universal default.
8. Treat 7B as reflex-only and tightly governed.
9. Use 20B minimum for study.
10. Use 72B/VL 72B for accuracy, documents, images, and deep study.

This path is closest to the original goal: Freyja should feel fast and familiar
for normal household questions, grow through scoped memory, and escalate to
slower accurate reasoning when the question matters.
