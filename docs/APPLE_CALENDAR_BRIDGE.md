# Apple Calendar bridge

Freyja uses a narrow native EventKit service on Iris instead of granting a
general-purpose desktop agent access to the host. The service exposes only
health, calendar discovery, and calendar-event CRUD over an authenticated HTTP
interface. Every successful create or update is read back from EventKit and
must include the real Apple event identifier.

## Iris installation

Run as the logged-in `freyja` user from `/Users/freyja/freyja-os`:

```bash
./scripts/install-apple-calendar-bridge.sh
```

The installer creates a random 256-bit bearer token in
`~/.config/freyja/apple-calendar.env` with mode `0600`, binds the service to
Iris's Tailscale IPv4 address on port `8765`, and installs the
`com.freyja-os.apple-calendar` user LaunchAgent. It does not print the token.

Request Full Calendar Access once from the logged-in Aqua session:

```bash
source ~/.config/freyja/apple-calendar.env
curl --fail -X POST \
  -H "Authorization: Bearer ${FREYJA_APPLE_CALENDAR_TOKEN}" \
  "http://${FREYJA_APPLE_CALENDAR_BIND_IP}:8765/permissions/request"
```

Approve the macOS Full Calendar Access dialog. Check the service with:

```bash
./scripts/status-apple-calendar-bridge.sh
```

## Director configuration

Copy the bridge URL and token to the Director's external secret configuration:

```dotenv
APPLE_CALENDAR_BRIDGE_URL=http://<iris-tailscale-ip>:8765
APPLE_CALENDAR_BRIDGE_TOKEN=<value-from-iris-config>
```

Never commit either the generated token file or a production `.env` file.

## Safety properties

- The bridge requires bearer authentication for every route.
- The LaunchAgent runs as the non-root `freyja` user.
- Update fields are allowlisted; callers cannot pass arbitrary EventKit data.
- The model-facing tool remains a controlled write.
- Freyja cannot report success unless EventKit returns a persistent event ID.
- Tests use synthetic payloads and never inspect a real calendar.
