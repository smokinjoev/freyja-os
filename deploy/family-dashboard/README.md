# Family Dashboard Deployment

`index.html` is the source-controlled Freyja Family Portal served at:

```text
http://100.119.235.114:9091/
```

Atlas's `cloyd-dashboard-web` container bind-mounts the page from:

```text
/home/joe/cloyd-services/dashboard/index.html
```

## Safe update procedure

1. Edit and review this repository copy first.
2. From a machine with approved Atlas SSH access, preserve the deployed file:

   ```sh
   cp /home/joe/cloyd-services/dashboard/index.html \
      /home/joe/cloyd-services/dashboard/index.html.bak-before-portal-update
   ```

3. Copy the reviewed `index.html` to that bind-mount path.
4. Verify the live page loads at `:9091` and every new link is reachable from
   the Tailscale network.
5. Commit the repository source and record material endpoint changes in
   `OPS_MANUAL.txt`.

The portal should contain only verified browser-accessible services. Do not add
password-copy buttons, control actions, stale Telegram links, file-share paths,
or unverified endpoints.
