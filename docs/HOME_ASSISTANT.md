# Home Assistant Foundation

Home Assistant is the device registry and automation runtime for Freyja-OS.
Atlas is the intended always-on host. Mars remains the Director and is the only
component that exposes Home Assistant capabilities to personal agents.

## Installation decision

Use Home Assistant OS in a bridged VM on Atlas if Atlas supports KVM or another
reliable hypervisor. Start with at least 2 vCPUs, 2 GB RAM, and a 32 GB virtual
disk. Home Assistant OS keeps the Supervisor and managed apps available for
Mosquitto, Matter Server, and Z-Wave JS.

Home Assistant Container is the fallback only when a VM is impractical. It does
not include managed apps, so MQTT, Matter Server, and Z-Wave JS would become
separate services that Freyja-OS must operate and back up.

## Current Freyja integration

The first integration slice is deliberately read-only from the agent loop:

- `homeassistant_status` checks configuration and reachability.
- `homeassistant_home_summary` summarizes entity counts, access classes, and
  family-home attention counts without returning raw Home Assistant attributes.
- `homeassistant_list_entities` returns sanitized states and access classes.
- `homeassistant_pairing_plan` explains protocol-specific physical and approval
  steps but cannot open pairing.
- `homeassistant_begin_pairing` can open a bounded Zigbee ZHA pairing window
  only when deliberately enabled by the operator and called with explicit
  confirmation. It is registered as `controlled_write` and disabled by default.

The REST client retains only these entity fields in tool output:

- entity ID
- state
- friendly name
- device class
- unit of measurement
- Freyja access classification

All other Home Assistant attributes are discarded at the boundary.

## Entity policy

New or unrecognized controllable entities start `quarantined`.

- `read_only`: sensors, binary sensors, weather, and sun state.
- `controlled`: an ordinary entity explicitly listed in
  `HOME_ASSISTANT_ENTITY_ALLOWLIST`.
- `high_risk`: locks, cameras, covers, and alarm control panels.
- `quarantined`: everything else until reviewed.

High-risk classification overrides the allowlist. The default model-facing tool
loop sees only enabled tools, so the Zigbee pairing write path is hidden until
an operator explicitly enables `homeassistant_begin_pairing`.

## Private configuration

Create a dedicated Home Assistant user for Freyja and generate its API token.
Keep the token in the protected runtime environment, never in Git:

```text
HOME_ASSISTANT_BASE_URL=http://homeassistant.freyja.local:8123
HOME_ASSISTANT_TOKEN=<private token>
HOME_ASSISTANT_TIMEOUT_SECONDS=10
HOME_ASSISTANT_ENTITY_ALLOWLIST=switch.test_lamp,light.test_bulb
```

The Home Assistant endpoint must remain on the LAN or tailnet. Do not publish
port 8123 directly to the internet.

## Pairing behavior

The service layer contains a bounded Zigbee pairing operation using
`zha.permit`, clamped to 15–120 seconds. It refuses unless its caller supplies
an explicit confirmation. The corresponding Director tool is registered but
disabled by default, classified as `controlled_write`, and returns only a safe
session summary:

- protocol
- whether pairing is open
- bounded duration
- Home Assistant service domain/name
- human-safe summary text

Protocol behavior:

- Zigbee: bounded ZHA join window after approval.
- Z-Wave: start inclusion through Z-Wave JS; retain PIN/QR handling.
- Matter: commission through the Home Assistant companion app using Bluetooth
  and the device QR/setup code.
- Bluetooth: review passive discovery from an approved adapter or ESPHome
  proxy; there is no universal network pairing window.
- Vendor integrations: follow the integration's own onboarding flow.

## Atlanta installation checklist

1. Confirm Atlas virtualization support and free storage.
2. Create the bridged Home Assistant OS VM and reserve its LAN address.
3. Complete local onboarding and enable backups before adding devices.
4. Create the dedicated Freyja API user/token and store it outside Git.
5. Inventory device brands and protocols before buying or attaching radios.
6. Attach Zigbee/Thread and Z-Wave radios using stable USB passthrough.
7. Record radio serial paths and securely back up network keys.
8. Verify mDNS and IPv6 behavior required by Matter across the home network.
9. Add one harmless test sensor, bulb, or plug first.
10. Verify inventory and backup/restore before enrolling security devices.

## Validation without a live home

All repository tests use `httpx.MockTransport`, synthetic tokens, synthetic
entities, and synthetic service responses. They never contact a LAN host or
open a real pairing window.
