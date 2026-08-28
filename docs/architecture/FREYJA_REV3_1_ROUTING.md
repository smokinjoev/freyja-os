# Freyja Rev 3.1 Routing

Freyja Rev 3.1 aligns model routing with the actual hardware roles. The handler
remains a policy and endpoint selector; it does not become a second reasoning
brain.

## Hardware Roles

- Iris handles immediate local presence, simple answers, acknowledgement, and
  graceful fallback when Vulcan is unreachable.
- Hera handles observation, media, and document intake before deeper reasoning.
- Vulcan handles primary serious inference for general reasoning, coding,
  vision, and embeddings.
- Cloud is an explicit policy-gated escape hatch when local inference is
  unavailable or insufficient.
- Atlas/Freyja owns policy, memory, routing, audit, and tool grants.

## Model Role Aliases

LiteLLM exposes role aliases so clients do not need to know physical model names
or provider formats:

- `iris-fast`: Iris 7B-class local response and fallback model.
- `vulcan-general`: Vulcan primary big multimodal general/reasoning model
  (`qwen2.5vl:72b`).
- `vulcan-coder`: Vulcan coding specialist.
- `vulcan-vision`: Vulcan big multimodal visual/document extraction model
  (`qwen2.5vl:72b`).
- `vulcan-embeddings`: Vulcan retrieval/memory embedding model.
- `cloud-frontier`: approved cloud fallback, only after policy allows egress.
- `vulcan`: compatibility alias for `vulcan-general`.

## Routing Rules

The handler uses lightweight capability routing:

- Simple acknowledgement or low-risk local work routes to `iris-fast`.
- Serious general chat, planning, document synthesis, and ordinary assistant
  work routes to `vulcan-general` on the 72B vision-language model.
- Coding, repository, terminal, and code-review work routes to `vulcan-coder`.
- Images, screenshots, scanned documents, and visual grounding route through
  `vulcan-vision`, using the same 72B vision-language model for heavyweight
  document/image reasoning.
- Retrieval and durable memory indexing use `vulcan-embeddings`.
- If Vulcan is unreachable, Iris returns an honest local limitation and offers
  cloud only when the request policy allows it.
- `cloud-frontier` is never a silent default; it is an explicit fallback.

## Completion Evidence

Rev 3.1 is complete when tests and live smoke checks prove:

- role aliases are present in LiteLLM;
- `vulcan-general` routes to Vulcan's large model;
- `vulcan-coder` routes coding work to the coding model;
- `iris-fast` is available as the local response/fallback role;
- `vulcan-vision` and `vulcan-embeddings` are named as separate capabilities;
- cloud fallback remains policy-gated and auditable.
