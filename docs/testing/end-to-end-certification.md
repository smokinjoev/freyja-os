# End-To-End Certification

Certification begins only after the build-complete architecture exists.

Minimum matrix:

- conversation: single turn, multi-turn, personal-agent identity, household
  isolation
- Vulcan routing: fast, reason, code, vision, unavailable profile behavior
- current information: weather, web/current requests, date-aware requests
- attachments: image, PDF, text document, unsupported, multiple attachments
- tools: success, failure, permission denied, timeout, malformed result,
  bounded multi-step use
- memory: remember, recall, scope correctness, shared scope, isolation
- iMessage: inbound, outbound, direct, group policy, attachment, tool use,
  Vulcan unavailable
- Signal: inbound, outbound, identity, attachment where supported, tool use,
  Vulcan unavailable
- reliability: Atlas, Iris, and Vulcan restart; network loss; timeout;
  duplicate message; reconnection

For every failure, capture the trace id and follow the boundary chain before
making a fix.

## Operator Evidence

Before live certification, capture:

```bash
scripts/vulcan-operator.py readiness --output logs/vulcan-readiness.json
scripts/signal-operator.py readiness --check-registered --output logs/signal-readiness.json
freyja-certify rev2-readiness --vulcan-report logs/vulcan-readiness.json
```

`vulcan-readiness.json` must show `ready_for_certification: true` before
vision/profile certification can pass. `signal-readiness.json` must show
`ready_for_live_smoke: true` before Signal live certification can pass.
