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

Check required profile readiness with:

```bash
scripts/vulcan-operator.py readiness
scripts/vulcan-operator.py readiness --output logs/vulcan-readiness.json
```

Install a missing profile model deliberately:

```bash
scripts/vulcan-operator.py pull-profile vision
scripts/vulcan-operator.py pull-profile vision --yes
```

`pull-profile` defaults to dry-run. The JSON report records the logical
profile, provider id, base URL, and configured physical model so certification
can prove Freyja is using the named profile layer instead of scattered model
names.

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
scripts/signal-operator.py --env-file deploy/compose/signal/.env readiness --check-registered
scripts/signal-operator.py --env-file deploy/compose/signal/.env register
scripts/signal-operator.py --env-file deploy/compose/signal/.env register --yes
scripts/signal-operator.py --env-file deploy/compose/signal/.env verify --code 123-456
scripts/signal-operator.py --env-file deploy/compose/signal/.env verify --code 123-456 --yes
```

Use `--voice` on `register` when SMS is unavailable, and `--captcha` when
Signal requires a captcha token. Generate registration captcha tokens at
`https://signalcaptchas.org/registration/generate.html` and pass the returned
`signalcaptcha://...` value only to the approved registration command. For an
existing mobile Signal account, link the REST wrapper as a secondary device
instead:

```bash
scripts/signal-operator.py --env-file deploy/compose/signal/.env link-device --device-name freyja-atlas
scripts/signal-operator.py --env-file deploy/compose/signal/.env link-device --device-name freyja-atlas --link-output /tmp/freyja-signal-link.txt --yes
```

The JSON reports hash phone numbers and do not include verification codes,
captcha tokens, PINs, or link URIs. Treat the optional link-output file as
sensitive and remove it after scanning or using the link.

After registration or linking, confirm `SIGNAL_ACCOUNT_NUMBER` is configured,
review `SIGNAL_ALLOWED_SENDERS`, set `SIGNAL_ENABLED=true`, then run:

```bash
scripts/signal-operator.py --env-file deploy/compose/signal/.env readiness --check-registered
scripts/signal-operator.py --env-file deploy/compose/signal/.env live-smoke --check-registered
scripts/signal-operator.py --env-file deploy/compose/signal/.env live-smoke --check-registered --yes
```

## Current External Actions

Signal live certification remains blocked until the dedicated Signal account is
registered or linked, enabled, and configured with reviewed allowed senders. The
Atlas Compose Signal REST API is running healthy in the current local evidence;
the remaining account setup requires a fresh Signal captcha-backed registration
request or device-link approval.
iMessage live certification remains blocked on local Apple permissions and
Messages account state where those prompts are not already approved.
