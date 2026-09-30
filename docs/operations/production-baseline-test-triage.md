# Production Baseline Test Triage

This is an evidence record for the full suite run on Vulcan on 2026-09-29.
Result: **1859 passed, 32 failed, 6 skipped**. None of the groups below is an
approved exclusion. The production-baseline gate remains closed until each is
resolved or explicitly accepted with matching-host evidence.

## Groups requiring a matching host or a deliberate operational choice

| Failure group | Count | Why it fails on Vulcan | Required disposition |
| --- | ---: | --- | --- |
| `test_gmail_launchagent.py`, `test_macagent_launchagent.py`, and the macOS `osascript` test | 7 | These tests assert Iris macOS paths and `/usr/bin/osascript`; Vulcan is Linux. | Run them on Iris, or refactor the tests to use source-controlled Iris deployment fixtures while retaining one Iris smoke. |
| `test_openwebui_terminal_bridge.py` | 1 | The bridge is configured for the macOS Homebrew `tmux` path, unavailable on Vulcan. | Validate on Iris or make the executable path host-configurable and add an equivalent Linux fixture. |
| `test_freyja_channels_atlas_deployment.py` | 2 | The verifier expects an Atlas readiness artifact produced from private channel configuration. Telegram and Signal are intentionally not enabled or certified. | Keep channels out of the release claim; either add a non-secret, clearly pending fixture or run an approved Atlas readiness check without activating either channel. |
| `test_freyja5_architecture.py::test_freyja5_certification_provider_exercises_gateway_runtime` | 1 | Its local provider is intentionally configured with inference disabled, so it cannot produce a written answer. | Replace with a deterministic non-inference architecture assertion, or run a bounded live Nexus smoke and preserve its trace. |

## Legacy evidence/report chain

The following 21 failures belong to an older Open WebUI home-agent bundle,
inventory, readiness-summary, secret-safety, inference-policy, and model-proxy
evidence chain. It relies on generated `certification/reports` artifacts that
are not present in this source checkout and whose historical Open WebUI model
proxy assumptions are no longer the canonical LibreChat/Core path.

- `test_open_webui_home_agent_bundle.py` (3)
- `test_open_webui_home_agent_completion_audit.py` (3)
- `test_open_webui_home_agent_platform_inventory.py` (3)
- `test_open_webui_home_agent_readiness_summary.py` (5)
- `test_open_webui_home_agent_secret_safety.py` (2)
- `test_open_webui_inference_policy_audit.py` (3)
- `test_open_webui_model_proxy.py` (1)
- plus the two Atlas readiness-artifact failures above when their generated
  evidence is consumed by this chain

Before a production merge, choose one path deliberately:

1. Rebuild and validate that evidence chain against the current compatibility
   role of Open WebUI; or
2. Retire/archive the obsolete chain with replacement coverage for the
   canonical LibreChat, Nexus, Iris Core, and family-portal path.

Do not manufacture private readiness artifacts, enable Telegram/Signal, or
weaken secret-safety checks merely to turn these tests green.
