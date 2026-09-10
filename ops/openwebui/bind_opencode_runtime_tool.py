import json
import sqlite3
import time


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
TOOL_ID = "opencode_runtime"
MODEL_IDS = ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder")


def load_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


con = sqlite3.connect("/app/backend/data/webui.db")
con.row_factory = sqlite3.Row
now = int(time.time())

con.execute("update tool set user_id = ?, updated_at = ? where id = ?", (JOE_USER_ID, now, TOOL_ID))

rows = []
for model_id in MODEL_IDS:
    row = con.execute("select id, meta, params from model where id = ?", (model_id,)).fetchone()
    if row is None:
        continue
    meta = load_json(row["meta"], {})
    params = load_json(row["params"], {})
    tool_ids = list(meta.get("toolIds") or [])
    if TOOL_ID not in tool_ids:
        tool_ids.append(TOOL_ID)
    meta["toolIds"] = tool_ids
    capabilities = meta.setdefault("capabilities", {})
    capabilities["function_calling"] = True
    capabilities["tools"] = True
    system = str(params.get("system") or "")
    note = (
        "The OpenCode Runtime tool is available. For coding, webpage/app building, repo changes, "
        "tests, development environment checks, ports, or Tailscale/OpenCode service work, use "
        "opencode_start, opencode_send, opencode_shell, opencode_status, opencode_output, or opencode_stop. "
        "Do not refuse these tasks as outside household scope when this tool is available."
    )
    if note not in system:
        params["system"] = f"{system.strip()}\n\n{note}".strip()
    con.execute(
        "update model set meta = ?, params = ?, updated_at = ? where id = ?",
        (json.dumps(meta), json.dumps(params), now, model_id),
    )
    rows.append({"model": model_id, "toolIds": tool_ids})

con.commit()
print(json.dumps({"ok": True, "tool": TOOL_ID, "models": rows}, indent=2))
