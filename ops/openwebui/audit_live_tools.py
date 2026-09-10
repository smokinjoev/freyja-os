import json
import sqlite3


def walk_tool_ids(value, found):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("tool_ids", "toolIds"):
                found.append(child)
            walk_tool_ids(child, found)
    elif isinstance(value, list):
        for child in value:
            walk_tool_ids(child, found)


con = sqlite3.connect("/app/backend/data/webui.db")
con.row_factory = sqlite3.Row

print("TOOLS")
for row in con.execute("select id,user_id,name,specs,meta,valves,updated_at from tool order by name"):
    specs = json.loads(row["specs"] or "[]")
    meta = json.loads(row["meta"] or "{}") if row["meta"] else None
    print(
        json.dumps(
            {
                "id": row["id"],
                "owner": row["user_id"],
                "name": row["name"],
                "spec_names": [spec.get("name") for spec in specs],
                "meta": meta,
                "valves_null": row["valves"] is None,
                "updated_at": row["updated_at"],
            },
            indent=2,
        )
    )

print("RECENT_CHAT_TOOL_IDS")
for row in con.execute("select id,title,chat,updated_at from chat order by updated_at desc limit 30"):
    chat = json.loads(row["chat"] or "{}")
    found = []
    walk_tool_ids(chat, found)
    if found:
        print(json.dumps({"id": row["id"], "title": row["title"], "tool_ids": found, "updated_at": row["updated_at"]}, indent=2))
