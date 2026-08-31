# Hera Camera Bring-Up

Use this runbook when Hera camera hardware is installed or changes state. The
goal is to verify camera-backed semantic status and then restore real local
perception without making raw video streaming to Vulcan the default path.

As of 2026-08-31, Hera sees the installed ROCWARE RC08
camera/microphone/speaker as `/dev/video0` and `/dev/video1` with stable
`/dev/v4l/by-id/` and `/dev/v4l/by-path/` links.
The Freyja 3 semantic publisher has emitted authenticated `camera_available`
events to Atlas. `freyja-vision.service` is enabled on camera index `0` and
wakes the built-in screen on motion or face detection.

## Current Safe State

- `freyja3-hera-semantic-publisher.timer` should stay enabled and active.
- `freyja-vision.service` should stay enabled and use `VISION_CAM=0` for the
  readable ROCWARE RC08 video stream.
- Hera should publish `camera_available` events with visible camera devices,
  audio source and sink evidence, and NPU evidence.
- Motion or face detection should run `/home/joe/agent/bin/screen_on.sh`; idle
  timeout should run `/home/joe/agent/bin/screen_off.sh`.
- Revision 4.1 avatar inclusion keeps the adult avatar visible during wake by
  restarting the kiosk while the panel is still dark, waiting briefly for the
  portrait to repaint, then raising the backlight and posting `screen_wake`.
  The tracked deploy copies live under `deploy/systemd/user/hera/`.

## Check Hardware Visibility

Run on Hera:

```bash
ls -l /dev/video* /dev/media* /dev/v4l/by-id/* /dev/v4l/by-path/* 2>/dev/null || true
lsusb
lspci | grep -Ei 'camera|video|multimedia|neural|npu|accelerator'
pw-cli list-objects Node | grep -Ei 'media.class|node.name|node.description|Audio/Source|Audio/Sink|Video' -A2 -B1
```

Expected current Hera evidence includes `/dev/video0`, `/dev/video1`, and
ROCWARE RC08 symlinks under `/dev/v4l/by-id/`. If no `/dev/video*` appears,
check physical USB/camera connection, BIOS/UEFI camera enablement, kernel driver
availability, and user permissions.

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

After confirming the camera device appears:

1. Restart Hera's semantic publisher once. It should publish `camera_available`
   with `camera_device_count` greater than zero.
2. Keep `freyja-vision.service` pointed at camera index `0`, the readable
   ROCWARE RC08 video stream.
3. Confirm motion or face detection wakes the built-in screen through
   `/home/joe/agent/bin/screen_on.sh`.
4. Confirm the service emits avatar events such as `motion_detected`,
   `person_entered`, `screen_wake`, and `person_left`.
5. Add Atlas semantic perception events such as `person_present`,
   `occupancy_changed`, or `object_seen` when the local pipeline is promoted
   beyond display wake behavior.
6. Keep raw video local to Hera unless a specific approved diagnostic requires
   otherwise.

## Service Commands

```bash
systemctl --user restart freyja3-hera-semantic-publisher.service
systemctl --user enable --now freyja3-hera-semantic-publisher.timer

systemctl --user enable --now freyja-vision.service
```

## Completion Evidence

Hera display wake bring-up is complete when motion or face detection turns on
the built-in screen and posts avatar events. Full semantic perception completion
still requires Atlas to return a real sensor-derived semantic event, not just
`camera_available` status.
Acceptable event types include:

- `person_present`
- `occupancy_changed`
- `object_seen`
- another typed, documented semantic perception event derived from a local Hera
  sensor
