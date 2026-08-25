# Deployment

Freyja deployment should keep inference, messaging, and control endpoints on
the private network unless a document explicitly says otherwise.

## Atlas

Atlas runs the Director/control plane and Linux-native connector services such
as Signal where configured. Use systemd or the existing container manifests on
Linux, and verify services return after reboot.

## Vulcan

Configure Vulcan with:

```text
VULCAN_BASE_URL=http://vulcan:11434
MODEL_FAST=<configured-fast-model>
MODEL_REASON=<configured-reason-model>
MODEL_CODE=<configured-code-model>
MODEL_VISION=<configured-vision-model>
```

The physical model names are deployment choices, not architecture.

## Iris

Iris runs MacAgent and Apple-native connectors with LaunchAgents/LaunchDaemons
as appropriate. iMessage live sending still requires local Apple permissions,
Messages account state, and operator approval gates.

## Signal

Freyja uses `signal-cli-rest-api` as the local Signal transport wrapper. That
is not a private Signal network: new Signal accounts still require Signal SMS,
voice, registration-lock, or device-link approval.

Registration and linking are operator actions:

```bash
scripts/signal-operator.py readiness --check-registered
scripts/signal-operator.py register --number +15555550100
scripts/signal-operator.py register --number +15555550100 --yes
scripts/signal-operator.py verify --number +15555550100 --code 123-456
scripts/signal-operator.py verify --number +15555550100 --code 123-456 --yes
```

Use `--voice` on `register` when SMS is unavailable, and `--captcha` when
Signal requires a captcha token. For an existing mobile Signal account, link
the REST wrapper as a secondary device instead:

```bash
scripts/signal-operator.py link-device --device-name freyja-atlas
scripts/signal-operator.py link-device --device-name freyja-atlas --link-output /tmp/freyja-signal-link.txt --yes
```

The JSON reports hash phone numbers and do not include verification codes,
captcha tokens, PINs, or link URIs. Treat the optional link-output file as
sensitive and remove it after scanning or using the link.

After registration or linking, set `SIGNAL_ACCOUNT_NUMBER`, review
`SIGNAL_ALLOWED_SENDERS`, then run:

```bash
scripts/signal-operator.py readiness --check-registered
scripts/signal-operator.py live-smoke --check-registered
scripts/signal-operator.py live-smoke --check-registered --yes
```

## Current External Actions

Signal live certification remains blocked until the Signal account/service is
registered or linked, enabled, and reachable with configured allowed senders.
iMessage live certification remains blocked on local Apple permissions and
Messages account state where those prompts are not already approved.
