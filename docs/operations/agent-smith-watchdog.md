# Agent Smith Watchdog Runbook

Agent Smith is a bounded Freyja hardware watchdog. It is not a general-purpose
chat assistant and is disabled by default in the policy configuration.

## Current boundary

- Read-only diagnostics and status work are permitted.
- Service-watchdog configuration: `config/agent-smith-watchdog.yaml`.
- Repository-agent policy: `config/agent-smith-policy.yaml`. This is a
  separate, disabled-by-default policy for bounded repository work; it does
  not authorize the service watchdog to repair infrastructure.
- The policy denies credential access, arbitrary shell execution, arbitrary
  filesystem writes, package installation, service termination, and destructive
  Git actions.
- Any write, commit, service restart, or dependency change requires explicit
  human approval through the approved path.

## Read-only health check

The current monitor is on Iris:

```sh
curl -fsS http://100.115.228.56:8000/agent-runs/api/runtime/health
curl -fsS http://100.115.228.56:8000/agent-runs/api/status
```

The browser view is `http://100.115.228.56:8000/agent-runs`.

Interpret these as observability evidence only. A healthy monitor does not
authorize Smith to repair a service.

## Required alert contract before enabling Smith

1. Initial recipient: Joe through the existing Cloyd Discord DM bot.
2. Delivery path: direct Discord delivery using the fixed recipient and the
   existing Cloyd Bot credential; it is not a general messaging capability.
3. Define alert severity:
   - informational: record only;
   - warning: one Cloyd notification with a monitor link;
   - critical: one Cloyd notification plus a clear statement that no automatic
     repair was attempted.
4. On 2026-09-29, the controlled delivery test was accepted by Discord. Its
   message stated that no repair was attempted.
5. Record the timestamp and outcome in
   `docs/operations/freyja-live-acceptance.md`.

Do not enable automatic restart, home-control, shell, or write authority as
part of this initial watchdog activation.
