# Agent Smith Watchdog

Agent Smith is the native, observation-only Freyja watchdog. It runs outside
Docker so it can report service health without sharing the failure domain.

Current Iris service:

- LaunchAgent: `com.freyja-os.smith-service-shepherd`
- Script: `scripts/smith-service-shepherd.py`
- Config: `config/agent-smith-watchdog.yaml`
- Status: `~/.local/state/freyja/smith-service-shepherd-status.json`
- Logs: `logs/smith-service-shepherd.log` and `logs/smith-service-shepherd.jsonl`

Smith watches the active Director, Discord, MacAgent, Core, and loop services.
It records status only: it never restarts a service, opens Docker, runs Compose,
reads credentials, or performs automatic repair.

Model routing:

- Primary: Vulcan Ollama `http://100.94.80.21:11434`, model `qwen3.8:27b`
Smith has no automatic escalation destination. An operator must explicitly
approve a recipient and a test alert before any health notification is sent.

Install on Iris:

```sh
scripts/install-smith-service-shepherd-launchagent.sh
```

Status:

```sh
scripts/status-smith-service-shepherd.sh
```

Do not enable an additional Smith service on Atlas; Iris is the current
watchdog host.
