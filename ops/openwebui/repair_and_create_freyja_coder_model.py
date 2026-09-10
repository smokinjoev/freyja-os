import json
import sqlite3
import time


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
MODEL_ID = "agent/freyja-coder"
BASE_MODEL_ID = "qwen3-coder-next:q4_K_M"
TOOL_IDS = ["atlas_status", "vulcan_agent", "openwebui_terminal_bridge"]


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

con.execute("update model set user_id = ?, updated_at = ? where user_id is null", (JOE_USER_ID, now))

existing_tools = {
    row["id"]
    for row in con.execute(
        f"select id from tool where id in ({', '.join('?' for _ in TOOL_IDS)})",
        TOOL_IDS,
    )
}
missing_tools = [tool_id for tool_id in TOOL_IDS if tool_id not in existing_tools]
if missing_tools:
    raise RuntimeError(f"missing tools: {missing_tools}")

meta = {
    "profile_image_url": "/static/favicon.png",
    "description": "Freyja coding model backed by the approved Qwen coder route, with the constrained terminal bridge available for persistent tmux/Qwen sessions.",
    "capabilities": {
        "file_context": True,
        "vision": False,
        "file_upload": False,
        "web_search": False,
        "image_generation": False,
        "code_interpreter": False,
        "terminal": False,
        "citations": True,
        "status_updates": True,
        "memory": True,
        "builtin_tools": True,
        "function_calling": True,
        "tools": True,
    },
    "knowledge": None,
    "suggestion_prompts": [],
    "tags": ["freyja", "coder", "qwen", "terminal-bridge"],
    "toolIds": TOOL_IDS,
}
params = {"temperature": 0.2, "top_p": 0.9}

existing = con.execute("select id from model where id = ?", (MODEL_ID,)).fetchone()
if existing:
    con.execute(
        "update model set user_id = ?, base_model_id = ?, name = ?, params = ?, meta = ?, updated_at = ?, is_active = 1 where id = ?",
        (JOE_USER_ID, BASE_MODEL_ID, "Freyja Coder", json.dumps(params), json.dumps(meta), now, MODEL_ID),
    )
    action = "updated"
else:
    con.execute(
        "insert into model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) values (?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (MODEL_ID, JOE_USER_ID, BASE_MODEL_ID, "Freyja Coder", json.dumps(params), json.dumps(meta), now, now),
    )
    action = "created"

for model_id in ("agent/cloyd-gibbler", "agent/freyja", MODEL_ID):
    row = con.execute("select id, meta from model where id = ?", (model_id,)).fetchone()
    if row is None:
        continue
    row_meta = load_json(row["meta"], {})
    existing_tool_ids = list(row_meta.get("toolIds") or [])
    for tool_id in TOOL_IDS:
        if tool_id not in existing_tool_ids:
            existing_tool_ids.append(tool_id)
    row_meta["toolIds"] = existing_tool_ids
    capabilities = row_meta.setdefault("capabilities", {})
    capabilities["function_calling"] = True
    capabilities["tools"] = True
    con.execute(
        "update model set meta = ?, updated_at = ? where id = ?",
        (json.dumps(row_meta), now, model_id),
    )

con.commit()

rows = []
for row in con.execute("select id, user_id, base_model_id, name, is_active, meta from model order by id"):
    row_meta = load_json(row["meta"], {})
    rows.append(
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "base_model_id": row["base_model_id"],
            "name": row["name"],
            "is_active": row["is_active"],
            "toolIds": row_meta.get("toolIds"),
        }
    )

print(json.dumps({"action": action, "created_or_updated": MODEL_ID, "models": rows}, indent=2))
