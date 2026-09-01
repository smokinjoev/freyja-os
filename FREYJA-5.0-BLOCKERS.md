# Freyja 5.0 Blockers

## Joe Required

- `msty_go_always_on_linux_validation`: Validate whether Msty Go can operate reliably as the always-on Atlas agent
  plane on Linux. Required evidence: install path, service definition, restart
  behavior, local config/export story, health endpoint or equivalent, and
  whether Freyja's canonical agent definitions can remain in source control.
- `vulcan_nexus_presets`: Provide or confirm local-only Nexus preset names on Vulcan for `fast`,
  `general`, `deep`, `code`, `vision`, `embedding`, and `private`. Do not paste
  tokens into chat; place secrets in the existing host secret stores.
- `iris_apple_session`: Run live Iris Apple Calendar MCP/MacAgent certification on the actual Mac
  session because it requires local Apple account/session state.
- `hera_voice_avatar_hardware`: Run live Hera voice/avatar certification where microphone/speaker/avatar
  hardware is physically present.
- `live_tool_sessions`: Validate live MCP-backed tool sessions for delegated Freyja 5 tasks. Required
  evidence: live MCP tool sessions reachable from Atlas, a Cloyd delegation
  smoke that actually selects/uses a tool, and trace evidence for the tool
  call.
- `vulcan_nexus_private_preset`: Validate Benedict Paralegal's private Nexus route on Vulcan. Required
  evidence: local-only private preset, Benedict enclave smoke with no cloud
  egress, and trace evidence showing the private route.

## Non-Blocking Implementation Notes

- Msty Go is not assumed. The source boundary remains `AgentRuntimeV3` on Atlas
  until Msty Go is proven suitable or an adapter is implemented.
- Freyja 4.1 fallback is preserved at git tag
  `freyja-4.1-baseline-before-5.0-20260831-161448`.
- Freyja 5.0 certification now has a `freyja5` provider/adapter that sends cases
  through `AgentGateway` and `AgentRuntimeV3`. Live certification with real
  Nexus inference, Iris Apple sessions, and Hera hardware still requires Joe's
  local service/session validation above.
