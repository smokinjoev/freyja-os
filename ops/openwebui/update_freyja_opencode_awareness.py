import json
import shutil
import sqlite3
import time
from pathlib import Path


DB = Path("/app/backend/data/webui.db")
BACKUP_DIR = Path("/app/backend/data/backups/freyja-opencode-awareness")
MODEL_ID = "agent/freyja"
OPENCODE_TEXT = (
    "Freyja can control the approved OpenCode coding-agent runtime when Joe asks for repository work. "
    "Use OpenCode for real coding tasks: start isolated coder sessions, send prompts, run shell commands, "
    "inspect session status/output, and stop active work. The OpenCode server is reachable on the private "
    "Tailscale address 100.115.228.56:4097 and routes model inference through Msty Nexus to Vulcan Qwen. "
    "Do not say you cannot code or interact with development environments when this tool lane is available; "
    "use the approved coding tools or report the specific runtime/approval problem."
)
TOOL_IDS = [
    "atlas_status",
    "vulcan_agent",
    "openwebui_terminal_bridge",
]


def load_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


BACKUP_DIR.mkdir(parents=True, exist_ok=True)
backup = BACKUP_DIR / f"webui.db.{int(time.time())}.bak"
shutil.copy2(DB, backup)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
row = con.execute("select id, params, meta from model where id = ?", (MODEL_ID,)).fetchone()
if row is None:
    raise RuntimeError(f"missing model row: {MODEL_ID}")

params = load_json(row["params"], {})
system = str(params.get("system") or "").strip()
if OPENCODE_TEXT not in system:
    params["system"] = f"{system}\n\n{OPENCODE_TEXT}".strip()

meta = load_json(row["meta"], {})
meta["description"] = (
    "Freyja household agent with approved OpenCode runtime control for Joe's repository coding tasks."
)
capabilities = meta.setdefault("capabilities", {})
capabilities["function_calling"] = True
capabilities["tools"] = True
capabilities["status_updates"] = True
tool_ids = list(meta.get("toolIds") or [])
for tool_id in TOOL_IDS:
    if tool_id not in tool_ids:
        tool_ids.append(tool_id)
meta["toolIds"] = tool_ids
tags = list(meta.get("tags") or [])
for tag in ("opencode", "coding-runtime"):
    if tag not in tags:
        tags.append(tag)
meta["tags"] = tags

now = int(time.time())
con.execute(
    "update model set params = ?, meta = ?, updated_at = ? where id = ?",
    (json.dumps(params), json.dumps(meta), now, MODEL_ID),
)
con.commit()

print(json.dumps({"ok": True, "model": MODEL_ID, "backup": str(backup), "toolIds": tool_ids}, indent=2))
