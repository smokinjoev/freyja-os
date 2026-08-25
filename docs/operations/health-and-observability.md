# Health And Observability

Every request must carry a trace id through connector receipt, identity
resolution, Director routing, Vulcan profile selection, tool execution,
response creation, and connector delivery.

Signal and iMessage gateways generate a canonical trace id at the adapter
boundary, send it as Director `request_id`, and include it in
`X-Freyja-Trace-Id`. The canonical endpoint uses `CanonicalRequest.trace_id`
directly.

`/providers/health` reports provider compatibility ids plus logical model
profiles. The logical profile is the architecture-level signal; the provider id
is the current implementation compatibility key.

Health states should distinguish healthy, degraded, unavailable, and
misconfigured. If Vulcan is unavailable, connectors must not silently fall back
to local conversational intelligence.

Required evidence for certification:

- connector received message
- identity resolved
- Director accepted request
- model profile selected
- actual endpoint/model used
- tool calls and results
- response produced
- connector delivered response

`/canonical/route` returns sanitized `tool_results` when tools are required.
These records expose tool name, success/failure, safe scalar metadata, error
category, and duration without raw stdout, stderr, prompts, secrets, or
exception internals.
