# Agent Smith Watchdog Runbook

Agent Smith is a bounded Freyja hardware watchdog. It is not a general-purpose
chat assistant and is disabled by default in the policy configuration.

## Current boundary

- Read-only diagnostics and status work are permitted.
- Source configuration: `config/agent-smith-policy.yaml`.
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

1. Choose one initial recipient: Cloyd is recommended for technical alerts.
2. Choose one delivery path: the existing Cloyd Discord DM connector is the
   least-expansive option because it is already live.
3. Define alert severity:
   - informational: record only;
   - warning: one Cloyd notification with a monitor link;
   - critical: one Cloyd notification plus a clear statement that no automatic
     repair was attempted.
4. Run a synthetic read-only health check and verify the alert arrives once.
5. Record the timestamp and outcome in
   `docs/operations/freyja-live-acceptance.md`.

Do not enable automatic restart, home-control, shell, or write authority as
part of this initial watchdog activation.
