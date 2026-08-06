# Apple Reminders bridge

Freyja uses a narrow native EventKit service on Iris for Reminders. The service
exposes only health, reminder-list discovery, reminder listing, creation,
completion, and deletion over an authenticated HTTP interface.

## Iris installation

Run as the logged-in `freyja` user from `/Users/freyja/freyja-os`:

```bash
./scripts/install-apple-reminders-bridge.sh
```

The installer creates a random 256-bit bearer token in
`~/.config/freyja/apple-reminders.env` with mode `0600`, binds the service to
Iris's Tailscale IPv4 address on port `8766`, and installs the
`com.freyja-os.apple-reminders` user LaunchAgent. It does not print the token.

Request Reminders access once from the logged-in Aqua session:

```bash
source ~/.config/freyja/apple-reminders.env
curl --fail -X POST \
  -H "Authorization: Bearer ${FREYJA_APPLE_REMINDERS_TOKEN}" \
  "http://${FREYJA_APPLE_REMINDERS_BIND_IP}:8766/permissions/request"
```

Approve the macOS Reminders access dialog. Check the service with:

```bash
./scripts/status-apple-reminders-bridge.sh
```

## Director configuration

Copy the bridge URL and token to the Director's external secret configuration:

```dotenv
APPLE_REMINDERS_BRIDGE_URL=http://<iris-tailscale-ip>:8766
APPLE_REMINDERS_BRIDGE_TOKEN=<value-from-iris-config>
```

Never commit either the generated token file or a production `.env` file.

## Safety properties

- The bridge requires bearer authentication for every route.
- The LaunchAgent runs as the non-root `freyja` user.
- Freyja can list, create, complete, and delete reminders only through explicit
  controlled tools.
- Tests use synthetic payloads and never inspect real reminders.
