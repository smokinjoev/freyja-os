# Freyja Homebridge on Atlas

This Compose project runs Homebridge as an always-on Atlas container.

Homebridge uses `network_mode: host` so HomeKit and mDNS discovery work on the
LAN. Its web UI listens on port `8581` by default. The container stores pairing
state, plugins, and Homebridge configuration in the `homebridge-data` Docker
volume; that data does not belong in Git.

## Start

From the Freyja OS checkout on Atlas:

```bash
cp deploy/compose/homebridge/.env.example deploy/compose/homebridge/.env
chmod 600 deploy/compose/homebridge/.env
docker compose --env-file deploy/compose/homebridge/.env \
  -f deploy/compose/homebridge/compose.yaml config
docker compose --env-file deploy/compose/homebridge/.env \
  -f deploy/compose/homebridge/compose.yaml up -d
```

Verify:

```bash
docker compose --env-file deploy/compose/homebridge/.env \
  -f deploy/compose/homebridge/compose.yaml ps
curl --fail http://127.0.0.1:8581
```

Then open the UI from the LAN:

```text
http://10.1.10.78:8581
```

Keep Homebridge plugin installation deliberate. Plugins can bridge real devices
into Apple Home, so review plugin scope and credentials before adding them.
