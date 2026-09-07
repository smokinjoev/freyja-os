# Agent Smith Remote Terminal

Agent Smith is a small Tailscale-only browser frame for talking to Qwen on Iris.
It is intentionally thin: `ttyd` serves a browser terminal and attaches to a
persistent `tmux` session running Qwen.

## Service

LaunchAgent:

```text
scripts/com.freyja-os.gateway-remote.plist
```

Terminal launcher:

```text
scripts/run-agent-smith-qwen.sh
```

Default local bind:

```text
127.0.0.1:8010
```

Default Qwen binary:

```text
/opt/homebrew/bin/qwen
```

Default Vulcan OpenAI-compatible endpoint passed to Qwen:

```text
http://100.94.80.21:3939/v1
```

The launcher starts Qwen with an isolated `QWEN_HOME` under the gateway state
directory. That Smith-specific Qwen config contains only the Vulcan Nexus
provider and does not inherit the normal `~/.qwen/settings.json` OpenRouter
entries. The Qwen process runs inside the `agent-smith` tmux session, so closing
Safari or locking the iPad does not stop the agent.

## iPad URL

Tailscale Serve publishes the localhost service privately:

```bash
tailscale serve --bg https / http://127.0.0.1:8010
```

Open from the iPad:

```text
https://iris.tail3995b4.ts.net/
```

## Nexus Token

Qwen receives the Nexus bearer token from:

```text
~/.local/state/freyja/gateway-remote/msty-nexus-token
```

## Security Boundary

The service binds to localhost:

```text
127.0.0.1:8010
```

Tailscale Serve publishes that localhost port privately at the iPad URL. There
is no folder picker, no autocomplete popup, and no custom command gateway. The
terminal attaches to the existing `agent-smith` tmux session or creates it with
Qwen as the session command.
