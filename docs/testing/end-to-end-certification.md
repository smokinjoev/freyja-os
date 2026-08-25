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
