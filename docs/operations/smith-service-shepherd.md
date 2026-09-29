# Agent Smith Service Shepherd

Agent Smith is the Freyja 6 native service shepherd. He runs outside Docker so a
Docker outage does not take down the monitor responsible for restoring the stack.

Current Iris service:

- LaunchAgent: `com.freyja-os.smith-service-shepherd`
- Script: `scripts/smith-service-shepherd.py`
- Config: `config/freyja6/smith-shepherd.yaml`
- Status: `~/.local/state/freyja/smith-service-shepherd-status.json`
- Logs: `logs/smith-service-shepherd.log` and `logs/smith-service-shepherd.jsonl`

Smith watches the active Director/Discord/MacAgent launch agents, Docker, and the
Freyja 6 base compose stack. Road mode is explicitly listed as disabled and is not
restarted by Smith.

Model routing:

- Primary: Vulcan Ollama `http://100.94.80.21:11434`, model `qwen3.8:27b`
- OpenClaw back door: the same Ollama API, model from `SMITH_OPENCLAW_MODEL`
  with default `openclaw`

The OpenClaw route is a direct availability probe/back-door route. It reports
unavailable until Vulcan exposes a matching Ollama model tag.

The dormant Docker family overlay now also keeps `hermes-smith` on
`vulcan-general` and carries the OpenClaw route environment, so enabling that
overlay later does not silently drop Smith back to the 7B `vulcan-fast` lane.

Install on Iris:

```sh
scripts/install-smith-service-shepherd-launchagent.sh
```

Status:

```sh
scripts/status-smith-service-shepherd.sh
```

Atlas native deployment uses the systemd unit template:

```sh
sudo cp deploy/systemd/freyja6-smith-service-shepherd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now freyja6-smith-service-shepherd.service
```
