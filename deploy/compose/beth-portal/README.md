# Beth Portal

Small web chat for Beth's two Benedict modes. It does not expose a model picker:

- Benedict: `agent/benedict`, `user: beth`, PDF route `vulcan-nexus-vision-docs`
- Benedict Paralegal: `agent/benedict-paralegal`, `user: paralegal`, PDF/local legal route `benedict-paralegal-nexus`

The browser talks only to this portal. The portal server proxies `/v1/*` to the
Freyja 5 OpenAI-compatible endpoint and injects the server-side token.

## Start

```bash
cp deploy/compose/beth-portal/.env.example deploy/compose/beth-portal/.env
docker compose --env-file deploy/compose/beth-portal/.env \
  -f deploy/compose/beth-portal/compose.yaml up -d
```

Then open:

```text
http://<iris-or-atlas-host>:8091
```

For the current Iris-local Freyja 5 service, set:

```text
FREYJA_OPENAI_BASE_URL=http://host.docker.internal:8500/v1
FREYJA_API_KEY=<FREYJA_CONNECTOR_TOKEN>
```

## API Shape

The portal sends:

```json
{
  "model": "agent/benedict",
  "user": "beth",
  "stream": false,
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Paralegal mode sends:

```json
{
  "model": "agent/benedict-paralegal",
  "user": "paralegal",
  "stream": false,
  "messages": [{"role": "user", "content": "Review this note."}]
}
```

Uploads are encoded as OpenAI-compatible content parts. Images use `image_url`
data URLs; other files use `file.file_data` data URLs.
