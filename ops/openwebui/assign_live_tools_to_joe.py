import sqlite3
import time


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
TOOL_IDS = (
    "iris_diagnostics",
    "iris_terminal_diagnostics",
    "atlas_status",
    "vulcan_status",
    "vulcan_free_ram",
    "vulcan_diagnostics",
    "vulcan_agent",
    "openwebui_terminal_bridge",
)


con = sqlite3.connect("/app/backend/data/webui.db")
con.execute(
    "update tool set user_id = ?, updated_at = ? where id in (?, ?, ?, ?, ?, ?, ?, ?)",
    (JOE_USER_ID, int(time.time()), *TOOL_IDS),
)
con.commit()

for row in con.execute("select id, user_id, name from tool where id in (?, ?, ?, ?, ?, ?, ?, ?) order by id", TOOL_IDS):
    print(row)
