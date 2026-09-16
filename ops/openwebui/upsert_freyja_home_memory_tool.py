from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from open_webui.models.tools import ToolForm, ToolMeta, Tools
from open_webui.utils.plugin import load_tool_module_by_id
from open_webui.utils.tools import get_tool_specs


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
DB_PATH = Path("/app/backend/data/webui.db")
TOOL_ID = "freyja_home_memory"
MODEL_IDS = (
    "agent/freyja",
    "agent/cloyd-gibbler",
    "agent/freyja-coder",
    "agent/benedict",
    "agent/agent-47",
    "agent/jennacide",
)


CONTENT = r'''
"""LIVE Freyja Home Memory adapter for OpenWebUI home agents.

Use this tool whenever Joe asks about memory, old Raspberry Pi Cloyd archives,
Freyja architecture continuity, or a scoped memory search. This adapter is live:
do not say it is unwired and do not suggest restarting a freyja-home-memory
service.
"""

import json
import urllib.parse
import urllib.request


class Tools:
    _BASE_URL = "http://host.docker.internal:8500/freyja-home-memory"
    _TOKEN_FILE = "/app/backend/data/secrets/freyja-director-token"
    _AGENT_ALIASES = {
        "agent/freyja": "freyja",
        "freyja": "freyja",
        "agent/cloyd-gibbler": "cloyd",
        "cloyd-gibbler": "cloyd",
        "cloyd": "cloyd",
        "agent/freyja-coder": "smith",
        "freyja-coder": "smith",
        "smith": "smith",
        "agent/benedict": "benedict",
        "benedict": "benedict",
        "agent/agent-47": "agent-44",
        "agent-47": "agent-44",
        "agent-44": "agent-44",
        "agent/jennacide": "jenna",
        "jennacide": "jenna",
        "jenna": "jenna",
    }
    _SCOPES = {
        "personal:joe",
        "personal:beth",
        "personal:liam",
        "personal:jenna",
        "household",
        "project:freyja-os",
        "restricted:benedict",
    }

    def _normalize_scope(self, scope: str) -> str:
        normalized = (scope or "project:freyja-os").strip()
        aliases = {
            "joe": "personal:joe",
            "memory": "personal:joe",
            "project": "project:freyja-os",
            "freyja": "project:freyja-os",
            "freyja-os": "project:freyja-os",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in self._SCOPES:
            raise ValueError(
                "invalid Freyja Home Memory scope; use one of: "
                + ", ".join(sorted(self._SCOPES))
            )
        return normalized

    def _token(self) -> str:
        with open(self._TOKEN_FILE, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    def _headers(self, agent_id: str) -> dict[str, str]:
        agent = self._AGENT_ALIASES.get(agent_id, agent_id)
        return {
            "content-type": "application/json",
            "x-api-key": self._token(),
            "x-freyja-client-type": "open-webui",
            "x-freyja-client-subject": f"agent:{agent}",
            "x-freyja-account-owner": "joe",
        }

    def _get(self, path: str, params: dict, agent_id: str) -> str:
        url = f"{self._BASE_URL}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=self._headers(agent_id))
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True)
        if len(body) > 16000:
            body = body[:16000] + "\n[truncated]"
        return body

    def search(self, query: str = "", scope: str = "project:freyja-os", limit: int = 8, agent_id: str = "cloyd") -> str:
        """LIVE search of Freyja permanent memory. Use scope personal:joe for Joe's private memories and project:freyja-os for Freyja/Cloyd archive facts."""
        bounded = max(1, min(int(limit), 20))
        try:
            normalized_scope = self._normalize_scope(scope)
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True)
        return self._get("/search", {"scope": normalized_scope, "q": query, "limit": bounded}, agent_id)

    def recent_events(self, scope: str = "project:freyja-os", limit: int = 8, agent_id: str = "cloyd") -> str:
        """LIVE recent Freyja permanent memory records for a permitted scope."""
        bounded = max(1, min(int(limit), 20))
        try:
            normalized_scope = self._normalize_scope(scope)
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True)
        return self._get("/recent-events", {"scope": normalized_scope, "limit": bounded}, agent_id)
'''


def _load_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def upsert_tool() -> list[str]:
    module, frontmatter = await load_tool_module_by_id(TOOL_ID, content=CONTENT)
    specs = get_tool_specs(module)
    form = ToolForm(
        id=TOOL_ID,
        name="Freyja Home Memory",
        content=CONTENT,
        meta=ToolMeta(
            description="Search Freyja permanent scoped memory through the Freyja gateway.",
            manifest=frontmatter,
            has_user_valves=False,
        ),
        access_grants=[],
    )
    existing = await Tools.get_tool_by_id(TOOL_ID)
    if existing:
        updated = await Tools.update_tool_by_id(
            TOOL_ID,
            {
                "user_id": JOE_USER_ID,
                "name": form.name,
                "content": form.content,
                "specs": specs,
                "meta": form.meta.model_dump(),
                "valves": {},
            },
        )
        if updated is None:
            raise RuntimeError(f"failed to update {TOOL_ID}")
    else:
        await Tools.insert_new_tool(JOE_USER_ID, form, specs)
    return [spec["name"] for spec in specs]


def bind_models() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = int(time.time())
    rows = []
    try:
        conn.execute("update tool set user_id = ?, updated_at = ? where id = ?", (JOE_USER_ID, now, TOOL_ID))
        for model_id in MODEL_IDS:
            row = conn.execute("select id, meta from model where id = ?", (model_id,)).fetchone()
            if row is None:
                continue
            meta = _load_json(row["meta"])
            tool_ids = list(meta.get("toolIds") or [])
            if TOOL_ID not in tool_ids:
                tool_ids.append(TOOL_ID)
            meta["toolIds"] = tool_ids
            capabilities = meta.setdefault("capabilities", {})
            capabilities["builtin_tools"] = False
            capabilities["function_calling"] = True
            capabilities["tools"] = True
            conn.execute(
                "update model set meta = ?, updated_at = ? where id = ?",
                (json.dumps(meta), now, model_id),
            )
            rows.append({"model": model_id, "toolIds": tool_ids})
        conn.commit()
    finally:
        conn.close()
    return rows


async def main() -> None:
    specs = await upsert_tool()
    models = bind_models()
    print(json.dumps({"ok": True, "tool": TOOL_ID, "specs": specs, "models": models}, indent=2))


asyncio.run(main())
