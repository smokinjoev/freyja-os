# Hera Camera Recovery

Use this runbook when Hera is publishing `camera_unavailable` semantic events.
The goal is to restore real camera-backed semantic perception without making raw
video streaming to Vulcan the default path.

Hera now lives in Atlanta as the household IoT/logging and voice/avatar edge
node. This is future-scope guidance until the Atlanta camera/sensor hardware is
installed or otherwise reachable.

## Current Safe State

- `freyja3-hera-semantic-publisher.timer` should stay enabled and active.
- `freyja-vision.service` may be disabled while no camera device is visible.
- Hera should continue publishing `camera_unavailable` events with
  `camera_device_count=0`, audio source evidence, and NPU evidence.

## Check Hardware Visibility

Run on Hera:

```bash
ls -l /dev/video* /dev/media* /dev/v4l/by-id/* /dev/v4l/by-path/* 2>/dev/null || true
lsusb
lspci | grep -Ei 'camera|video|multimedia|neural|npu|accelerator'
pw-cli list-objects Node | grep -Ei 'media.class|node.name|node.description|Audio/Source|Video' -A2 -B1
```

If no `/dev/video*` appears, check physical USB/camera connection, BIOS/UEFI
camera enablement, kernel driver availability, and user permissions. Joe may
need to confirm the physical device or make host-level permission changes.

## Verify Semantic Status

Run on Hera:

```bash
systemctl --user is-active freyja3-hera-semantic-publisher.timer
systemctl --user restart freyja3-hera-semantic-publisher.service
journalctl --user -u freyja3-hera-semantic-publisher.service -n 5 --no-pager
```

Run on Atlas:

```bash
curl -fsS -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN" \
  "http://100.119.235.114:8300/events/semantic?event_type=camera_unavailable&room=hera&limit=1"
```

The event should be typed semantic metadata, not raw frame data.

## Restore Real Perception

After a camera device appears:

1. Update Hera's semantic publisher by restarting it once. It should publish
   `camera_available` with `camera_device_count` greater than zero.
2. Reconfigure the real perception service to use the visible camera index or
   device path.
3. Start the real perception service and confirm it emits semantic events such
   as `person_present`, `occupancy_changed`, or `object_seen`.
4. Confirm Atlas stores those events through `/events/semantic`.
5. Keep raw video local to Hera unless a specific approved diagnostic requires
   otherwise.

## Service Commands

```bash
systemctl --user restart freyja3-hera-semantic-publisher.service
systemctl --user enable --now freyja3-hera-semantic-publisher.timer

# Only enable this after a real camera device exists and the service is pointed
# at the correct device.
systemctl --user enable --now freyja-vision.service
```

## Completion Evidence

Hera camera recovery is complete only when Atlas returns a real sensor-derived
semantic event, not just `camera_available` or `camera_unavailable` status.
Acceptable event types include:

- `person_present`
- `occupancy_changed`
- `object_seen`
- another typed, documented semantic perception event derived from a local Hera
  sensor
