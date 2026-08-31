#!/bin/bash
set -euo pipefail

echo 0 | sudo tee /sys/class/backlight/amdgpu_bl1/brightness >/dev/null
curl -fsS -X POST http://127.0.0.1:9200/api/vision \
  -H "Content-Type: application/json" \
  -d '{"event":"person_left","details":{"source":"screen_off"}}' >/dev/null 2>&1 || true
echo "screen off"
