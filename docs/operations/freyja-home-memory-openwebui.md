# Freyja Home Memory for Open WebUI

Freyja Home Memory is the local shared-context layer for the family agents. It
complements Open WebUI's native per-user Memory and Personalization feature; it
does not replace it.

## Layers

- Open WebUI native Memory: private per-user facts and preferences.
- Open WebUI Knowledge: stable household, project, device, and procedure
  documents.
- Freyja Home Memory: scoped local records shared through a narrow OpenAPI
  boundary.

## Service

The Director mounts the service at:

```text
/freyja-home-memory
```

On Atlas, the Director container listens internally on port `8000` and is
published on the tailnet as:

```text
http://100.119.235.114:8001/freyja-home-memory
```

The OpenAPI export for Open WebUI is generated with:

```bash
python3 scripts/export-open-webui-home-memory-openapi.py \
  --output certification/reports/open-webui-home-memory-openapi.json
```

The generated schema includes only:

- `GET /freyja-home-memory/operations`
- `GET /freyja-home-memory/search`
- `GET /freyja-home-memory/recent-events`
- `POST /freyja-home-memory/remember`
- `POST /freyja-home-memory/update`
- `POST /freyja-home-memory/record-decision`
- `DELETE /freyja-home-memory/forget/{scope}/{record_id}`

## Open WebUI Wiring

In Open WebUI, add this as a Tool Server:

```text
Type: OpenAPI
URL: http://100.119.235.114:8001
Spec path: /openapi.json or the exported schema URL/path you host
```

For production use, configure the tool server with these headers:

```text
x-api-key: <FREYJA_CONNECTOR_TOKEN>
x-freyja-client-type: open-webui
x-freyja-client-subject: agent:<agent-id>
```

Use one tool-server registration per agent principal when the UI cannot set
dynamic per-agent headers. Examples:

- Cloyd: `x-freyja-client-subject: agent:cloyd`
- Freyja: `x-freyja-client-subject: agent:freyja`
- Benedict: `x-freyja-client-subject: agent:benedict`
- Agent 44: `x-freyja-client-subject: agent:agent-44`
- Jenna: `x-freyja-client-subject: agent:jenna`

## Scope Policy

Readable scopes:

- Freyja: `household`, `project:freyja-os`
- Cloyd: `personal:joe`, `household`, `project:freyja-os`
- Benedict: `personal:beth`, `restricted:benedict`
- Agent 44: `personal:liam`, `household`
- Jenna: `personal:jenna`, `household`

Writable scopes:

- Freyja: `household`, `project:freyja-os`
- Cloyd: `personal:joe`, `household`, `project:freyja-os`
- Benedict: `restricted:benedict`
- Children: no direct writes; search and recent-events only

Every record includes scope, owner, provenance, created/updated timestamps, and
sensitivity. Cross-scope reads and writes fail closed with `403`.

## Open WebUI Community Fit

Open WebUI already has native Memory for per-user facts and preferences, and it
supports OpenAPI and MCP tool servers for external context systems. For this
household setup, the safest approach is therefore not a cloud memory plugin:
use Open WebUI native Memory for personal preferences, Knowledge for curated
shared documents, and Freyja Home Memory for scoped household/project/restricted
records.
