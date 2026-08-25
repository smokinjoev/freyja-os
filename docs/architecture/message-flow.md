# Message Flow

Every channel should follow one canonical path:

```text
connector -> normalized request -> Atlas Director -> Vulcan profile
          -> tools/memory as authorized -> canonical response -> connector
```

Connectors receive, authenticate, normalize, attach identity/channel metadata,
submit to Atlas, and deliver responses. They do not independently reason about
or answer user requests.

## Canonical Contract

The channel-neutral models live in `src/freyja/contracts.py`.

`CanonicalRequest` carries `trace_id`, `message_id`, `timestamp`, `channel`,
`conversation_id`, `sender`, resolved user and agent ids, text, attachments,
reply context, channel metadata, and permissions.

`CanonicalResponse` carries the same trace and routing identity back to the
egress adapter, plus response text, optional attachments, sanitized
`tool_results`, channel metadata, status, and degraded-state information.

Director exposes `POST /canonical/route` for the canonical envelope. It returns
`CanonicalResponse` and preserves `trace_id` through router runtime evidence.

Existing connector dataclasses in `connectors/messaging.py` remain the adapter
compatibility layer and can now convert to `CanonicalRequest`. `POST /route`
remains for compatibility with existing scripts and deployed connectors while
callers migrate.

Current connector state:

- Gmail submits `CanonicalRequest` to `POST /canonical/route`.
- Signal submits `CanonicalRequest` to `POST /canonical/route`.
- iMessage submits `CanonicalRequest` to `POST /canonical/route`.
- Telegram submits `CanonicalRequest` to `POST /canonical/route`.
- Shortcuts/HomePod voice ingress builds a voice-channel `CanonicalRequest`
  before routing.
- `POST /route` remains for compatibility scripts, local smoke tools, and
  older callers during rollout.
