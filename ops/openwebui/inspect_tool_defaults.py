import json
import sqlite3


con = sqlite3.connect("/app/backend/data/webui.db")
con.row_factory = sqlite3.Row

for table in ("model", "user", "config"):
    print("##", table)
    for row in con.execute(f"pragma table_info({table})"):
        print(tuple(row))
    print("rows")
    for row in con.execute(f"select * from {table} limit 50"):
        data = dict(row)
        redacted = {}
        for key, value in data.items():
            if isinstance(value, str) and any(secret_word in key.lower() for secret_word in ("key", "token", "secret", "password")):
                redacted[key] = "[redacted]"
            elif isinstance(value, str):
                redacted[key] = value[:1200]
            else:
                redacted[key] = value
        print(json.dumps(redacted, indent=2))
