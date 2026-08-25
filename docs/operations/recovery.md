# Recovery

Recovery is boundary-oriented.

1. Check Atlas Director health.
2. Check Atlas persistent dependencies and connector service state.
3. Check Atlas can reach Vulcan.
4. Check required Vulcan model profiles are available.
5. Check Iris MacAgent health for Apple-native capabilities.
6. Check connector-specific transports, especially Signal and iMessage.
7. Use trace ids to identify the last confirmed-good boundary.

Do not diagnose routing from response wording. Use trace evidence.

## Signal Account Recovery

Use the operator CLI before debugging connector behavior:

```bash
scripts/signal-operator.py --env-file deploy/compose/signal/.env readiness --check-registered
scripts/signal-operator.py --env-file deploy/compose/signal/.env allowlist
```

If the account is missing from the REST wrapper, either complete
`register`/`verify` for the configured dedicated Signal number or run
`link-device` and scan the generated device link from the existing Signal
mobile account. When Signal reports a captcha requirement, generate the token at
`https://signalcaptchas.org/registration/generate.html` and pass the returned
`signalcaptcha://...` value only to the approved `register --yes` command. Do
not work around a missing Signal account by adding a connector-local responder.
