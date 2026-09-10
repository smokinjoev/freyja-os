import json
import sqlite3
import time


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
MODEL_ID = "qwen3.8-tools:27b"
BASE_MODEL_ID = "qwen3.8:27b"
STATUS_TOOL_IDS = ["atlas_status", "vulcan_status", "vulcan_free_ram"]


con = sqlite3.connect("/app/backend/data/webui.db")
con.row_factory = sqlite3.Row

meta = {
    "profile_image_url": "/static/favicon.png",
    "description": "Qwen 3.8 27B with safe Atlas and Vulcan status tools enabled by default.",
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
    "tags": ["qwen", "tools", "safe-status"],
    "toolIds": STATUS_TOOL_IDS,
}

params = {"temperature": 0.2, "top_p": 0.9}
now = int(time.time())

existing = con.execute("select id from model where id = ?", (MODEL_ID,)).fetchone()
if existing:
    con.execute(
        "update model set user_id = ?, base_model_id = ?, name = ?, params = ?, meta = ?, updated_at = ?, is_active = 1 where id = ?",
        (JOE_USER_ID, BASE_MODEL_ID, "Qwen 3.8 Tools", json.dumps(params), json.dumps(meta), now, MODEL_ID),
    )
    action = "updated"
else:
    con.execute(
        "insert into model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) values (?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (MODEL_ID, JOE_USER_ID, BASE_MODEL_ID, "Qwen 3.8 Tools", json.dumps(params), json.dumps(meta), now, now),
    )
    action = "created"
con.commit()

row = con.execute("select id, base_model_id, name, meta from model where id = ?", (MODEL_ID,)).fetchone()
saved_meta = json.loads(row["meta"])
print(json.dumps({"action": action, "id": row["id"], "base_model_id": row["base_model_id"], "name": row["name"], "toolIds": saved_meta.get("toolIds")}, indent=2))
