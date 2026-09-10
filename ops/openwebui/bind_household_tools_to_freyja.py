import json
import sqlite3
import time


MODEL_IDS = ["agent/freyja"]
REQUIRED_TOOL_IDS = [
    "atlas_status",
    "vulcan_agent",
    "weather",
    "home_assistant",
    "iris_apple",
]


def load_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


con = sqlite3.connect("/app/backend/data/webui.db")
con.row_factory = sqlite3.Row

placeholders = ", ".join("?" for _ in REQUIRED_TOOL_IDS)
existing_tools = {row["id"] for row in con.execute(f"select id from tool where id in ({placeholders})", REQUIRED_TOOL_IDS)}
missing = [tool_id for tool_id in REQUIRED_TOOL_IDS if tool_id not in existing_tools]
if missing:
    raise RuntimeError(f"missing tools: {missing}")

changed = []
for model_id in MODEL_IDS:
    row = con.execute("select id, meta from model where id = ?", (model_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"missing model: {model_id}")
    meta = load_json(row["meta"], {})
    tool_ids = list(meta.get("toolIds") or [])
    for tool_id in REQUIRED_TOOL_IDS:
        if tool_id not in tool_ids:
            tool_ids.append(tool_id)
    meta["toolIds"] = tool_ids
    capabilities = meta.setdefault("capabilities", {})
    capabilities["function_calling"] = True
    capabilities["tools"] = True
    con.execute(
        "update model set meta = ?, updated_at = ? where id = ?",
        (json.dumps(meta), int(time.time()), model_id),
    )
    changed.append((model_id, tool_ids))

con.commit()
print(json.dumps({"changed": changed}, indent=2))
