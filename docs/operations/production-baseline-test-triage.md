# Production Baseline Test Triage

This is an evidence record for the full suite run on Vulcan on 2026-09-29.
Result: **1859 passed, 32 failed, 6 skipped**. On 2026-09-29, the operator
approved a narrow production-baseline exception for the exact failure groups
below. This exception does not claim that Telegram or Signal are operational,
does not apply to new failures, and does not waive post-merge verification.

## Groups requiring a matching host or a deliberate operational choice

| Failure group | Count | Why it fails on Vulcan | Required disposition |
| --- | ---: | --- | --- |
| `test_gmail_launchagent.py`, `test_macagent_launchagent.py`, and the macOS `osascript` test | 7 | These tests assert Iris macOS paths and `/usr/bin/osascript`; Vulcan is Linux. | Run them on Iris, or refactor the tests to use source-controlled Iris deployment fixtures while retaining one Iris smoke. |
| `test_openwebui_terminal_bridge.py` | 1 | The bridge is configured for the macOS Homebrew `tmux` path, unavailable on Vulcan. | Validate on Iris or make the executable path host-configurable and add an equivalent Linux fixture. |
| `test_freyja_channels_atlas_deployment.py` | 2 | The verifier expects an Atlas readiness artifact produced from private channel configuration. Telegram and Signal are intentionally not enabled or certified. | Keep channels out of the release claim; either add a non-secret, clearly pending fixture or run an approved Atlas readiness check without activating either channel. |
| `test_freyja5_architecture.py::test_freyja5_certification_provider_exercises_gateway_runtime` | 1 | Its local provider is intentionally configured with inference disabled, so it cannot produce a written answer. | Replace with a deterministic non-inference architecture assertion, or run a bounded live Nexus smoke and preserve its trace. |

## Approved production-baseline exception

The 32 failures above are accepted only for this baseline because they are
either wrong-host checks, intentionally unapproved messaging prerequisites, or
obsolete Open WebUI artifact-chain assertions. They are bounded by the
following current evidence:

- 107 focused platform tests passing on Vulcan;
- 21 matching-host macOS tests passing on Iris;
- all five named LibreChat agents accepted with scoped Core tools;
- the ten-check live readiness baseline passing.

This is a release exception, not test deletion or a permanent exclusion.
Future changes must rerun the full suite and triage any failure outside these
exact groups. The obsolete Open WebUI evidence chain remains a cleanup item.

### Matching-host evidence

On 2026-09-29, Iris ran the host-specific selection successfully:
`21 passed` covering `test_gmail_launchagent.py`,
`test_macagent_launchagent.py`,
`test_macagent.py::test_macagent_osascript_timeout_reports_concrete_error`,
and `test_openwebui_terminal_bridge.py`. This confirms the eight Vulcan
failures in those files are host-mismatch results, not a failure of the
deployed macOS runtime. They remain excluded from neither the full-suite
count nor the production gate; the final release evidence must retain this
matching-host result.

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

After this baseline, choose one path deliberately for a later cleanup:

1. Rebuild and validate that evidence chain against the current compatibility
   role of Open WebUI; or
2. Retire/archive the obsolete chain with replacement coverage for the
   canonical LibreChat, Nexus, Iris Core, and family-portal path.

Do not manufacture private readiness artifacts, enable Telegram/Signal, or
weaken secret-safety checks merely to turn these tests green.
