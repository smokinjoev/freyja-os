# Freyja HomeKit Visibility

Freyja's family-assistant goal requires one canonical home graph that she can
inventory, reason over, and eventually control through policy. The practical
source of truth is Home Assistant on Atlas, not Apple Home membership.

Apple Home family membership lets a person use Apple Home apps and Siri. It
does not give a Linux service account or container a general API to read the
family's Apple Home graph. Freyja therefore needs HomeKit-visible devices
represented in Home Assistant.

## Target Shape

- Atlas Home Assistant is the canonical device graph for Freyja.
- HomeKit-native devices are paired into Home Assistant with the HomeKit Device
  integration when the device allows it.
- Home Assistant exposes selected entities back to Apple Home with HomeKit
  Bridge so the family can keep using the Home app.
- Homebridge remains available for plugins that expose non-HomeKit services to
  Apple Home, but it is not the primary path for Freyja to see Apple Home.

## Current Verified State

- Atlas Home Assistant API is reachable at `http://10.1.10.78:8123`.
- Freyja can inventory Atlas Home Assistant entities.
- Current inventory contains no obvious HomeKit/Homebridge-origin entities.
- Atlas Homebridge is available at `http://10.1.10.78:8581` for plugin-based
  bridging into Apple Home.
- A Home Assistant HomeKit Bridge named `Freyja Test Bridge` is configured on
  Atlas port `21065` and exposes a curated low-risk family-home set. It started
  with `light.kitchen_floor_lamp` and now includes 92 entities covering
  available lights, door/motion/leak-style sensors, environmental and energy
  readings, weather, HomePods/remotes, and non-dangerous switches.
- The local Freyja `.env` allowlists `light.kitchen_floor_lamp` as the first
  policy-controlled Home Assistant entity for this bridge test.
- `Freyja Test Bridge` has been paired from Apple Home. Its HomeKit bridge state
  has paired clients and remains bound to Atlas port `21065`.
- Freyja's control policy remains narrower than Apple Home exposure: only
  `light.kitchen_floor_lamp` is allowlisted for Freyja control. The rest are
  visible through Home Assistant and/or Apple Home without granting Freyja broad
  control.
- The tracked operational source for the Atlas bridge snippet is
  `deploy/homeassistant/atlas-homekit-bridge.yaml`; validation and rollback are
  documented in `deploy/homeassistant/README.md`.

## Pairing Rules

HomeKit accessories are normally paired to one controller at a time. To make a
HomeKit accessory visible to Freyja through Home Assistant:

1. Confirm the device's pairing code is available.
2. If the accessory is already paired only to Apple Home, remove it from Apple
   Home without factory-resetting it unless the manufacturer requires a reset.
3. Add it in Home Assistant with the HomeKit Device integration.
4. Verify the new entities appear in Freyja's Home Assistant inventory.
5. Expose the approved entities back to Apple Home using HomeKit Bridge.

Matter devices should use multi-admin commissioning when available instead of
forcing a single-controller move.

## Safety Policy

- Sensors, weather, sun, and other observation-only domains can be read by
  default.
- Locks, covers, alarm systems, cameras, and garage doors remain high-risk.
- Lights, switches, media players, scenes, and remotes stay quarantined until
  explicitly allowlisted for Freyja control.
- Pairing windows and control permissions require explicit operator approval.

## Next Work Items

1. Pick one low-risk HomeKit accessory and migrate it into Home Assistant with
   the HomeKit Device integration.
2. Run Freyja inventory validation and confirm the migrated entity appears.
3. Build a Freyja home summary view over Home Assistant inventory: rooms,
   domains, online/offline status, and access classification.
