# HomePod Shortcuts Voice

Use this runbook to let a HomePod talk to Freyja through an Apple Shortcut.
The HomePod/Siri layer only captures speech and speaks the response. Atlas or
Freyja 3 remains the authority for routing, tools, memory, and approval gates.

## Current Endpoint

Freyja exposes a voice-friendly Shortcut endpoint:

```text
POST /shortcuts/message
```

Use the Iris or Atlas Freyja 3 gateway URL that is reachable from the Apple
device. For a first HomePod test, prefer Iris because it is the Apple gateway
and is already part of the household Apple setup.

Current Iris options:

```text
http://10.1.10.136:8300/shortcuts/message
http://100.115.228.56:8300/shortcuts/message
```

Server-side Atlas option:

```text
http://100.119.235.114:8300/shortcuts/message
```

If `FREYJA_CONNECTOR_TOKEN` is set on the selected server, include:

```text
Authorization: Bearer <FREYJA_CONNECTOR_TOKEN>
```

## Shortcut Shape

Create a Shortcut named `Ask Freyja`.

1. Dictate Text
2. Get Contents of URL
3. Speak Text

Configure `Get Contents of URL`:

- Method: `POST`
- Headers:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer <FREYJA_CONNECTOR_TOKEN>` when the server requires it
- Request Body: JSON
- JSON body:

```json
{
  "prompt": "Dictated Text",
  "conversation_id": "homepod",
  "sender": "homepod",
  "tools_required": true
}
```

Configure `Speak Text` to speak the `spoken` field from the JSON response.

## Siri Phrase

After creating the Shortcut, say:

```text
Hey Siri, Ask Freyja
```

Then dictate the request, for example:

```text
What is on the family calendar today?
```

or:

```text
Ask before adding this, but add family dinner Saturday at 6 PM.
```

Calendar writes must still ask for confirmation before changing anything.

## Smoke Test

From a shell on the same network:

```bash
curl -fsS -X POST "http://100.119.235.114:8300/shortcuts/message" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is on my calendar?","conversation_id":"homepod-smoke","sender":"homepod","tools_required":true}'
```

Expected result:

- HTTP 200
- JSON includes `spoken`
- `conversation_id` starts with `shortcut-conv:`

## Failure Checks

- If Siri says the Shortcut failed, verify the HomePod/iPhone can reach the URL.
- If HTTP returns 401, add the `Authorization` header or verify the token.
- If the response is too long, keep the Shortcut using `spoken`, not `response`.
- If calendar writes happen without confirmation, stop and fix the Freyja tool
  permission gate before using the Shortcut with family.
