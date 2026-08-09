# Atlas Home Assistant Operations

Atlas runs the live Home Assistant instance for the Freyja family-home graph.
The container mounts its configuration at `/home/admin/ha-config` on Atlas and
`/config` inside the `homeassistant` container.

## HomeKit Bridge

`atlas-homekit-bridge.yaml` records the curated `Freyja Test Bridge` block that
is currently applied to Atlas `configuration.yaml`.

The bridge:

- uses Home Assistant's `homekit` integration,
- binds to Atlas port `21065`,
- remains paired in Apple Home,
- exposes a curated low-risk set of 92 entities to Apple Home,
- does not grant broad Freyja control.

Freyja control is governed separately by `HOME_ASSISTANT_ENTITY_ALLOWLIST`.
At this checkpoint only `light.kitchen_floor_lamp` is allowlisted.

## Apply Or Update

From Iris, copy the snippet to Atlas and replace the Freyja bridge block in
Home Assistant `configuration.yaml`:

```bash
scp deploy/homeassistant/atlas-homekit-bridge.yaml joe@10.1.10.78:/tmp/freyja-homekit.yaml
ssh joe@10.1.10.78
docker cp /tmp/freyja-homekit.yaml homeassistant:/tmp/freyja-homekit.yaml
docker exec -i homeassistant python3 - <<'PY'
from pathlib import Path

config = Path("/config/configuration.yaml")
snippet = Path("/tmp/freyja-homekit.yaml").read_text().strip()
text = config.read_text()
markers = [
    "# Freyja family HomeKit Bridge",
    "# Freyja test HomeKit Bridge",
]
starts = [text.find(marker) for marker in markers if text.find(marker) != -1]
if not starts:
    raise SystemExit("Freyja HomeKit Bridge block not found")
start = min(starts)
config.write_text(text[:start].rstrip() + "\n\n" + snippet + "\n")
PY
docker exec homeassistant python -m homeassistant --script check_config -c /config
docker restart homeassistant
```

## Validate

After restart:

```bash
docker ps --filter name=homeassistant --format '{{.Names}} {{.Status}}'
timeout 5 bash -c '</dev/tcp/127.0.0.1/21065' && echo homekit_bridge_port_open
docker exec -i homeassistant python3 - <<'PY'
import json
from pathlib import Path

entry_id = "01KZKXH9F4PK775GP3YCAQC6TN"
entries = json.loads(Path("/config/.storage/core.config_entries").read_text())["data"]["entries"]
state = json.loads(Path(f"/config/.storage/homekit.{entry_id}.state").read_text())
for entry in entries:
    if entry.get("entry_id") == entry_id:
        included = entry["options"]["filter"]["include_entities"]
        print({
            "title": entry["title"],
            "port": entry["data"]["port"],
            "include_count": len(included),
            "paired_client_count": len(state.get("paired_clients", {})),
        })
PY
```

Expected checkpoint:

```text
homekit_bridge_port_open
include_count: 92
paired_client_count: greater than 0
```

## Rollback

The first expansion created this in-container backup:

```text
/config/configuration.yaml.before-freyja-homekit-expanded
```

Restore it only if the bridge update breaks Home Assistant startup or Apple Home
pairing:

```bash
docker exec homeassistant cp \
  /config/configuration.yaml.before-freyja-homekit-expanded \
  /config/configuration.yaml
docker exec homeassistant python -m homeassistant --script check_config -c /config
docker restart homeassistant
```
