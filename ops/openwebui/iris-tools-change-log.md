# Iris OpenWebUI Tools Change Log

Date: 2026-09-09

## Installation/runtime

- OpenWebUI is running on Iris in Docker Compose project `freyja-open-webui-atlas`.
- Container: `freyja-open-webui-atlas-open-webui-1` (`93034aed33a2` during investigation).
- Image: `ghcr.io/open-webui/open-webui:main`.
- OpenWebUI version: `0.11.3`.
- Compose file: `/Users/freyja/freyja-os/deploy/compose/open-webui/compose.yaml`.
- Compose env file: `/Users/freyja/freyja-os/deploy/compose/open-webui/.env`.
- Published port: host `3001` to container `8080`.
- Data path in container: `/app/backend/data`.
- Data storage: Docker volume `freyja-open-webui-atlas_open-webui`, mounted read-write at `/app/backend/data`.
- Tool execution runtime: inside the OpenWebUI Linux container, not directly on the macOS host.

## Root cause found

- The OpenWebUI loader raises `No Tools class found in the module` only after executing the submitted module and failing to find a top-level `class Tools:`.
- The persisted `tool` and `function` tables were empty before creating the test tool, so the failing pasted/imported tool was not saved in `webui.db`.
- Most likely causes for the rejected module: missing top-level `class Tools:`, wrong class name, markdown code fences included in the pasted source, or indentation that nested `Tools` inside another block.
- Follow-up correction: the iPad UI was using the live Atlas OpenWebUI at `http://100.119.235.114:3001`, not the duplicate Iris-local container at `http://127.0.0.1:3001`.
- Live Atlas root cause: six existing placeholder tool rows had specs but their `content` was only a comment beginning `# Freyja managed tool boundary...`, with no `class Tools:`.

## Changes made

- Added helper script: `/Users/freyja/freyja-os/ops/openwebui/create_iris_tools.py`.
- Created OpenWebUI tool row `iris_diagnostics` in `/app/backend/data/webui.db`.
  - `iris_hostname()`
  - `iris_time()`
- Created OpenWebUI tool row `iris_terminal_diagnostics` in `/app/backend/data/webui.db`.
  - `local_diagnostic(command)`
  - Allowed command enum only: `hostname`, `whoami`, `pwd`, `uptime`, `ls`.
  - Uses fixed subprocess argv arrays with a 5 second timeout.
  - Does not accept arbitrary shell strings.

## Validation

- `iris_diagnostics` loaded through OpenWebUI's tool loader and generated two specs.
- `iris_hostname()` returned the container hostname `93034aed33a2`, proving Docker container execution.
- `iris_time()` returned current container/server time.
- `iris_terminal_diagnostics` loaded through OpenWebUI's tool loader and generated one spec with the fixed command enum.
- `local_diagnostic("hostname")`, `local_diagnostic("whoami")`, `local_diagnostic("pwd")`, and `local_diagnostic("ls")` succeeded.
- `local_diagnostic("uptime")` returned `unavailable` because `uptime` is not installed in this container.
- `local_diagnostic("uname")` returned `denied`, proving non-allowlisted commands are rejected.
- HTTP `GET /api/v1/tools/` returned `401 Not authenticated`, so UI/API listing requires an OpenWebUI login/API token.

## SSH findings

- The OpenWebUI container resolves `vulcan` and `atlas` but does not currently have an `ssh` binary.
- From the macOS host, `vulcan` resolves but batch SSH failed with public key/password authentication denied.
- From the macOS host, `atlas` resolves but batch SSH failed with public key/password authentication denied.
- `cloyd`, `cloyd.local`, `cloyd.lan`, `pi`, `pi.local`, `pi.lan`, `raspberrypi`, `raspberrypi.local`, and `raspberrypi.lan` did not resolve during the check.
- No per-machine OpenWebUI SSH tools were created because SSH did not work from the OpenWebUI runtime.

## SSH setup update

Date: 2026-09-09

- Created dedicated Iris SSH keypair for status-agent access:
  - Private key: `/Users/freyja/.ssh/openwebui_status_ed25519`
  - Public key: `/Users/freyja/.ssh/openwebui_status_ed25519.pub`
- Installed the public key for `joe` on Atlas using Atlas Tailscale IPv4 `100.119.235.114`.
- Verified Atlas key login with fixed read-only command:
  - `ssh -i ~/.ssh/openwebui_status_ed25519 joe@100.119.235.114 'hostname; whoami; uptime'`
  - Result returned hostname `Atlas`, user `joe`, and uptime.
- Attempted to install the same public key on Vulcan via `100.87.242.99` and `vulcan`.
  - `100.87.242.99` timed out on port 22 during `ssh-copy-id`.
  - `vulcan` hung during `ssh-copy-id` pre-check and was interrupted.
- Added SSH client config draft at `/Users/freyja/freyja-os/ops/openwebui/ssh-config-snippet`.
  - It defines `atlas-openwebui-status` and `vulcan-openwebui-status` using the dedicated key.
  - It has not been merged into `/Users/freyja/.ssh/config`.
- No password was written to the ops files.

## OpenWebUI chat test

Enable the `Iris Diagnostics` and `Iris Terminal Diagnostics` tools in OpenWebUI, then ask:

- `Use the Iris Diagnostics tool to show iris_hostname and iris_time.`
- `Use Iris Terminal Diagnostics to run hostname.`
- `Use Iris Terminal Diagnostics to run whoami.`
- `Use Iris Terminal Diagnostics to run uptime.`

Expected behavior:

- Hostname should show the Docker container ID, not `iris.lan`.
- `uptime` should report unavailable until the container image includes that binary.
- Any command outside the enum should be unavailable to the model.

## Safe next step

For Qwen coding/terminal agents, keep OpenWebUI tools narrow and route coding work through a separate local agent gateway with:

- Per-host allowlisted methods such as `vulcan_status()`, `atlas_status()`, and `cloyd_status()`.
- Fixed SSH argv arrays only.
- Dedicated read-only SSH keys or forced-command keys.
- No mounted broad host filesystem access.
- No arbitrary command parameter.

## OpenWebUI-runtime SSH fix

Date: 2026-09-09

- Installed `openssh-client` into the running OpenWebUI container.
  - This enables SSH from OpenWebUI tools now.
  - This package install is in the container filesystem and must be baked into the image or startup process before the container is recreated.
- Created `/app/backend/data/ssh` in the OpenWebUI data volume.
- Copied the dedicated status key into the OpenWebUI data volume:
  - `/app/backend/data/ssh/openwebui_status_ed25519`
  - `/app/backend/data/ssh/openwebui_status_ed25519.pub`
- Added Atlas host keys to `/app/backend/data/ssh/known_hosts`.
- Created OpenWebUI tool row `atlas_status` in `/app/backend/data/webui.db`.
  - `atlas_status()`
  - No arguments.
  - Uses fixed SSH argv only.
  - Target: `joe@100.119.235.114`
  - Remote command: `hostname; whoami; uptime`
  - Key: `/app/backend/data/ssh/openwebui_status_ed25519`
  - Known hosts file: `/app/backend/data/ssh/known_hosts`
  - `BatchMode=yes`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes`, `ConnectTimeout=10`
- Verified `atlas_status()` by loading the tool through OpenWebUI's loader inside the container.
  - Result: `exit=0`, hostname `Atlas`, user `joe`, and uptime.
- Vulcan is still not configured for OpenWebUI-runtime SSH.
  - The key install attempt to `100.87.242.99` timed out.
  - The key install attempt to `vulcan` hung and was interrupted.

## Vulcan-1 OpenWebUI-runtime SSH fix

Date: 2026-09-09

- Correct Vulcan Tailscale hostname: `Vulcan-1`.
- `Vulcan-1` resolves to `100.94.80.21` from the OpenWebUI container.
- Installed the existing dedicated status public key for `joe@Vulcan-1`.
- Added `Vulcan-1` host keys to `/app/backend/data/ssh/known_hosts`.
- Created OpenWebUI tool row `vulcan_status` in `/app/backend/data/webui.db`.
  - `vulcan_status()`
  - No arguments.
  - Uses fixed SSH argv only.
  - Target: `joe@Vulcan-1`
  - Remote command: `hostname; whoami; uptime`
  - Key: `/app/backend/data/ssh/openwebui_status_ed25519`
  - Known hosts file: `/app/backend/data/ssh/known_hosts`
  - `BatchMode=yes`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes`, `ConnectTimeout=10`
- Verified through OpenWebUI's loader inside the OpenWebUI container:
  - `atlas_status()` returned `exit=0`, hostname `Atlas`, user `joe`, and uptime.
  - `vulcan_status()` returned `exit=0`, hostname `Vulcan`, user `joe`, and uptime.

## Live Atlas OpenWebUI tool repair

Date: 2026-09-09

- Targeted the actual live OpenWebUI instance on Atlas:
  - URL: `http://100.119.235.114:3001`
  - Container: `freyja-open-webui-atlas-open-webui-1`
  - Container ID during repair: `21f0b3e6f9e8`
  - Data: Docker volume `freyja-open-webui-atlas_open-webui`
- Installed `openssh-client` into the running live Atlas OpenWebUI container.
- Copied the dedicated status key into the live Atlas OpenWebUI data volume:
  - `/app/backend/data/ssh/openwebui_status_ed25519`
  - `/app/backend/data/ssh/openwebui_status_ed25519.pub`
- Added Atlas and `Vulcan-1` host keys to `/app/backend/data/ssh/known_hosts`.
- Verified SSH from inside the live Atlas OpenWebUI container:
  - `joe@100.119.235.114` returned hostname `Atlas`, user `joe`, and uptime.
  - `joe@Vulcan-1` returned hostname `Vulcan`, user `joe`, and uptime.
- Created live OpenWebUI tools:
  - `iris_diagnostics`
  - `iris_terminal_diagnostics`
  - `atlas_status`
  - `vulcan_status`
- Repaired placeholder tool rows so they have top-level `class Tools:` stubs instead of comment-only source:
  - `freyja_home_memory`
  - `iris_apple`
  - `home_assistant`
  - `household_analysis`
  - `infrastructure_health`
  - `weather`
- Added helper scripts:
  - `/Users/freyja/freyja-os/ops/openwebui/repair_placeholder_tools.py`
  - `/Users/freyja/freyja-os/ops/openwebui/validate_openwebui_tools.py`
- Verified all 13 live tool rows load successfully through OpenWebUI's tool loader inside the live Atlas container.

## All-tools repair and cache clear

Date: 2026-09-09

- Audited all live Atlas OpenWebUI tool rows.
- Confirmed all 13 tools are owned by Joe's admin user or were reassigned to Joe where needed.
- Restarted only the live OpenWebUI container `21f0b3e6f9e8` to clear stale in-memory tool/module cache.
  - No OpenWebUI data was deleted, reset, reinstalled, or wiped.
  - Container ID remained `21f0b3e6f9e8`.
- Post-restart validation:
  - All 13 live tool rows load successfully through OpenWebUI's loader.
  - No new `No Tools class found` or `Error loading module` entries appeared in the post-restart log window.
  - `atlas_status()` executed from the OpenWebUI container and returned `exit=0`, hostname `Atlas`, user `joe`, and uptime.
  - `vulcan_status()` executed from the OpenWebUI container and returned `exit=0`, hostname `Vulcan`, user `joe`, and uptime.

## Vulcan RAM tool and model defaults

Date: 2026-09-09

- Created live OpenWebUI tool row `vulcan_free_ram`.
  - Tool name: `Vulcan Free RAM`
  - Method: `vulcan_free_ram()`
  - No arguments.
  - Uses fixed SSH argv only.
  - Target: `joe@Vulcan-1`
  - Remote command: `free -h`
- Verified `vulcan_free_ram()` through OpenWebUI's loader inside the live Atlas OpenWebUI container.
  - Result: `30Gi` total, `9Gi` free, `20Gi` available, `8.0Gi` swap free.
- Bound status tools to model defaults where model DB rows existed:
  - `agent/cloyd-gibbler`: `atlas_status`, `vulcan_status`, `vulcan_free_ram`
  - `agent/freyja`: `atlas_status`, `vulcan_status`, `vulcan_free_ram`
- Created wrapper model `qwen3.8-tools:27b`.
  - Display name: `Qwen 3.8 Tools`
  - Base model: `qwen3.8:27b`
  - Default tools: `atlas_status`, `vulcan_status`, `vulcan_free_ram`
- Restarted only the live OpenWebUI container to refresh model metadata and tool cache.
- Post-restart validation:
  - OpenWebUI `http://100.119.235.114:3001/api/config` is healthy.
  - All 14 live tool rows load successfully.

## Consolidated Vulcan agent tool

Date: 2026-09-09

- Created live OpenWebUI tool row `vulcan_agent`.
  - Tool name: `Vulcan Agent`
  - Method: `vulcan_agent(action)`
  - Uses one enum parameter instead of one tool per command.
  - Does not accept arbitrary shell commands.
  - Current allowlisted actions:
    - `status`
    - `system_memory`
    - `gpu_memory`
    - `gpu_inventory`
    - `disk`
    - `load`
    - `freyja_os_git_status`
    - `freyja_os_recent_commits`
    - `freyja_os_test_inventory`
- Updated model defaults to use the consolidated tool surface:
  - `qwen3.8-tools:27b`: `atlas_status`, `vulcan_agent`
  - `agent/cloyd-gibbler`: `atlas_status`, `vulcan_agent`
  - `agent/freyja`: `atlas_status`, `vulcan_agent`
- Verified through OpenWebUI's loader inside the live Atlas OpenWebUI container:
  - `vulcan_agent("gpu_inventory")` identified AMD Strix Halo / Radeon 8050S or 8060S graphics.
  - `vulcan_agent("gpu_memory")` returned that `nvidia-smi` and `rocm-smi` were not available.
  - `vulcan_agent("freyja_os_git_status")` found the Vulcan `freyja-os` checkout on branch `feature/cloyd-upstream-features`.

## OpenWebUI terminal bridge

Date: 2026-09-09

- Added `scripts/openwebui-terminal-bridge.py`.
  - Owns named tmux sessions.
  - Supports `start`, `status`, `send`, `read`, and `stop`.
  - Rejects unsafe session names.
  - Stores per-session metadata under `~/.local/state/freyja/openwebui-terminal-bridge`.
  - Launches Qwen with the existing Vulcan Nexus defaults:
    - Base URL: `http://100.94.80.21:3939/v1`
    - Model: `@preset/freyja-coder`
    - Token file: `~/.local/state/freyja/gateway-remote/msty-nexus-token`
- Added live OpenWebUI tool row `openwebui_terminal_bridge`.
  - Tool name: `OpenWebUI Terminal Bridge`
  - Methods:
    - `terminal_start(session, workdir, agent)`
    - `terminal_status(session)`
    - `terminal_send(text, session, enter)`
    - `terminal_ctrl_c(session)`
    - `terminal_read(session, lines)`
    - `terminal_stop(session)`
  - Uses fixed SSH argv from the OpenWebUI container to `freyja@iris`.
  - Sends arbitrary user text over stdin to the bridge, not as part of the SSH command string.
  - Does not expose an unauthenticated network shell.
- Backups made before live modifications:
  - Repo files: `backups/openwebui-terminal-bridge-20260909/`
  - Live OpenWebUI DB: `/app/backend/data/backups/openwebui-terminal-bridge-20260909/webui.db.bak`
  - Container SSH known_hosts: `/app/backend/data/ssh/known_hosts.bak.openwebui-terminal-bridge-20260909`
- Live verification from inside the OpenWebUI container:
  - OpenWebUI loader accepted the tool and generated specs for all six terminal methods.
  - `terminal_start("owui-live-full", "~/freyja-os")` created a Qwen tmux session on Iris.
  - `terminal_send("BRIDGE_INPUT_MARKER", enter=False)` wrote literal text into Qwen.
  - `terminal_read("owui-live-full")` showed the Qwen Code banner, `Vulcan Nexus`, `~/freyja-os`, and the marker text.
  - `terminal_status("owui-live-full")` reported `running: true`.
  - `terminal_ctrl_c("owui-live-full")` succeeded.
  - `terminal_stop("owui-live-full")` removed the tmux session.
  - Restarted only the live OpenWebUI container to clear tool/module cache.
  - Post-restart loader check still exposed all six `terminal_*` methods.
  - `terminal_status("openwebui-qwen")` returned `running: false` with STOP available for the default session name.
- Local regression checks:
  - `.venv/bin/pytest -q tests/test_openwebui_terminal_bridge.py`
  - `python3 -m py_compile scripts/openwebui-terminal-bridge.py ops/openwebui/create_iris_tools.py`
