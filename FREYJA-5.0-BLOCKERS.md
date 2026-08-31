# Freyja 5.0 Blockers

## Joe Required

- Validate whether Msty Go can operate reliably as the always-on Atlas agent
  plane on Linux. Required evidence: install path, service definition, restart
  behavior, local config/export story, health endpoint or equivalent, and
  whether Freyja's canonical agent definitions can remain in source control.
- Provide or confirm local-only Nexus preset names on Vulcan for `fast`,
  `general`, `deep`, `code`, `vision`, `embedding`, and `private`. Do not paste
  tokens into chat; place secrets in the existing host secret stores.
- Run live Iris Apple Calendar MCP/MacAgent certification on the actual Mac
  session because it requires local Apple account/session state.
- Run live Hera voice/avatar certification where microphone/speaker/avatar
  hardware is physically present.

## Non-Blocking Implementation Notes

- Msty Go is not assumed. The source boundary remains `AgentRuntimeV3` on Atlas
  until Msty Go is proven suitable or an adapter is implemented.
- Freyja 4.1 fallback is preserved at git tag
  `freyja-4.1-baseline-before-5.0-20260831-161448`.
- Freyja 5.0 certification now has a `freyja5` provider/adapter that sends cases
  through `AgentGateway` and `AgentRuntimeV3`. Live certification with real
  Nexus inference, Iris Apple sessions, and Hera hardware still requires Joe's
  local service/session validation above.
