#!/bin/bash
set -euo pipefail

MAX=$(cat /sys/class/backlight/amdgpu_bl1/max_brightness)

# Restart the kiosk while the panel is still dark, then give Firefox a moment
# to repaint the adult portrait before the backlight comes up.
systemctl --user restart freyja-kiosk.service >/dev/null 2>&1 || true
sleep 2

echo "$MAX" | sudo tee /sys/class/backlight/amdgpu_bl1/brightness >/dev/null
curl -fsS -X POST http://127.0.0.1:9200/api/vision \
  -H "Content-Type: application/json" \
  -d '{"event":"screen_wake","details":{"source":"screen_on"}}' >/dev/null 2>&1 || true

echo "screen on"
