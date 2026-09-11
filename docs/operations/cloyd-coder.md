# Cloyd Coder

`cloyd-coder` is a small Atlas-local HTTP bridge between OpenWebUI/Cloyd and
the existing Atlas OpenCode/Qwen setup. OpenWebUI stays the chat front end; code
work runs through OpenCode in allowlisted project directories.

## Allowlisted Projects

| Project | Directory |
| --- | --- |
| `family-dashboard` | `/home/joe/cloyd-services` |
| `freyja-atlas` | `/home/joe/freyja-os` |
| `nextcloud` | `/home/joe/nextcloud` |
| `paperless` | `/home/joe/paperless-ngx` |

## Start

Run on Atlas bound to loopback by default:

```bash
cloyd-coder --host 127.0.0.1 --port 8766
```

For Tailnet-only exposure, bind to the Atlas Tailscale IP instead of a public
interface:

```bash
CLOYD_CODER_HOST=100.119.235.114 CLOYD_CODER_PORT=8766 cloyd-coder
```

Persisted jobs are stored under:

```bash
~/.local/state/freyja/cloyd-coder/jobs
```

Override that for testing with `CLOYD_CODER_STATE_DIR`.

## Stop

If running in a foreground shell, press `Ctrl-C`.

If running under systemd, stop the unit that launches `cloyd-coder`:

```bash
systemctl --user stop cloyd-coder
```

## API

Only these endpoints are exposed:

```text
POST /jobs
GET /jobs/{id}
GET /jobs/{id}/log
POST /jobs/{id}/cancel
```

Example:

```bash
curl -fsS http://127.0.0.1:8766/jobs \
  -H 'content-type: application/json' \
  -d '{"project":"family-dashboard","prompt":"Read-only: inspect git status and summarize the app structure. Do not change files."}'
```

Then poll the returned id:

```bash
curl -fsS http://127.0.0.1:8766/jobs/JOB_ID
curl -fsS http://127.0.0.1:8766/jobs/JOB_ID/log
```

## OpenWebUI Tool

Run the existing OpenWebUI tool upsert script after the service is reachable:

```bash
python ops/openwebui/create_iris_tools.py
python ops/openwebui/bind_opencode_runtime_tool.py
```

This preserves `opencode_runtime` and adds the `cloyd_coder` tool with:

```text
coder_start(project, prompt)
coder_status(job_id)
coder_log(job_id)
coder_cancel(job_id)
```

Cloyd's model prompt is updated to prefer `coder_*` tools for Atlas code writes
instead of `atlas_code` or direct `opencode_shell` use.

## Smoke Test

Start with a read-only `family-dashboard` job:

```bash
python3 scripts/cloyd-coder-smoke.py
```

Only if that completes, run a tiny safe write test:

```bash
python3 scripts/cloyd-coder-smoke.py --write
```

The equivalent manual calls are:

```bash
READ_JOB=$(curl -fsS http://127.0.0.1:8766/jobs \
  -H 'content-type: application/json' \
  -d '{"project":"family-dashboard","prompt":"Read-only smoke test: run pwd, git status --short, and identify the project type. Do not modify files."}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -fsS "http://127.0.0.1:8766/jobs/$READ_JOB"
WRITE_JOB=$(curl -fsS http://127.0.0.1:8766/jobs \
  -H 'content-type: application/json' \
  -d '{"project":"family-dashboard","prompt":"Tiny safe write smoke test: create or update tmp/cloyd-coder-smoke.txt with a timestamp, then run git status --short. Do not touch any other file."}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -fsS "http://127.0.0.1:8766/jobs/$WRITE_JOB"
curl -fsS "http://127.0.0.1:8766/jobs/$WRITE_JOB/log"
```

The API reports only persisted job state and actual OpenCode results. If
OpenCode cannot be reached, the job is marked failed with the captured error.
