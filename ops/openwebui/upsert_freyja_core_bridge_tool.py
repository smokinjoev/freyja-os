from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
TOOL_ID = "freyja_core_bridge"
MODEL_IDS = ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder")
DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_BACKUP_DIR = Path("/app/backend/data/backups")


CONTENT = r'''
"""Thin OpenWebUI bridge to Iris-owned Freyja Core.

This tool intentionally contains no calendar, OpenCode, memory, or policy logic.
It only forwards an explicit Core tool name plus JSON arguments to Freyja Core.
"""

import json
import urllib.error
import urllib.request


class Tools:
    _CORE_URL = "http://100.115.228.56:8510/tools/call"
    _TIMEOUT_SECONDS = 30
    _MAX_RESPONSE_CHARS = 20000

    def freyja_core_call(self, tool: str, arguments_json: str = "{}") -> str:
        """Call an Iris-owned Freyja Core tool by name and return the raw Core JSON."""
        tool_name = (tool or "").strip()
        if not tool_name:
            return json.dumps({"ok": False, "error": "missing required Core tool name"}, indent=2, sort_keys=True)
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return json.dumps(
                {"ok": False, "error": "arguments_json must be valid JSON", "detail": str(exc)},
                indent=2,
                sort_keys=True,
            )
        if not isinstance(arguments, dict):
            return json.dumps(
                {"ok": False, "error": "arguments_json must decode to a JSON object"},
                indent=2,
                sort_keys=True,
            )
        payload = json.dumps({"tool": tool_name, "arguments": arguments}).encode("utf-8")
        request = urllib.request.Request(
            self._CORE_URL,
            data=payload,
            headers={
                "content-type": "application/json",
                "x-freyja-client-type": "open-webui",
                "x-freyja-client-tool": "freyja_core_call",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return json.dumps(
                {"ok": False, "error": "freyja core returned http error", "status": exc.code, "body": body},
                indent=2,
                sort_keys=True,
            )
        except Exception as exc:
            return json.dumps(
                {"ok": False, "error": "freyja core request failed", "detail": str(exc)},
                indent=2,
                sort_keys=True,
            )
        if len(body) > self._MAX_RESPONSE_CHARS:
            body = body[: self._MAX_RESPONSE_CHARS] + "\n[truncated]"
        return body
'''


SYSTEM_NOTE = (
    "Freyja Core is the authority for Freyja actions. When a request involves Freyja tools, dates, "
    "calendar actions, OpenCode session control, status checks, or Freyja memory, prefer the "
    "freyja_core_call tool and pass the exact Core tool name plus JSON arguments. Do not duplicate "
    "calendar, OpenCode, memory, or policy logic in OpenWebUI when Freyja Core can handle it."
)


def load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def backup_db(db: Path, backup_dir: Path, *, now: int | None = None) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now or time.time()))
    destination_dir = backup_dir / f"freyja-core-bridge-{timestamp}"
    destination_dir.mkdir(parents=True, exist_ok=False)
    destination = destination_dir / "webui.db.bak"
    shutil.copy2(db, destination)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db) + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, destination_dir / f"webui.db{suffix}.bak")
    return destination


def bind_models(conn: sqlite3.Connection, *, now: int | None = None) -> list[dict[str, Any]]:
    timestamp = int(now or time.time())
    conn.row_factory = sqlite3.Row
    conn.execute("update tool set user_id = ?, updated_at = ? where id = ?", (JOE_USER_ID, timestamp, TOOL_ID))
    rows: list[dict[str, Any]] = []
    for model_id in MODEL_IDS:
        row = conn.execute("select id, meta, params from model where id = ?", (model_id,)).fetchone()
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
        if SYSTEM_NOTE not in system:
            params["system"] = f"{system.strip()}\n\n{SYSTEM_NOTE}".strip()
        conn.execute(
            "update model set meta = ?, params = ?, updated_at = ? where id = ?",
            (json.dumps(meta), json.dumps(params), timestamp, model_id),
        )
        rows.append({"model": model_id, "toolIds": tool_ids})
    conn.commit()
    return rows


async def upsert_tool() -> list[str]:
    from open_webui.models.tools import ToolForm, ToolMeta, Tools
    from open_webui.utils.plugin import load_tool_module_by_id
    from open_webui.utils.tools import get_tool_specs

    module, frontmatter = await load_tool_module_by_id(TOOL_ID, content=CONTENT)
    specs = get_tool_specs(module)
    form = ToolForm(
        id=TOOL_ID,
        name="Freyja Core Bridge",
        content=CONTENT,
        meta=ToolMeta(
            description="Thin OpenWebUI bridge that forwards explicit tool calls to Iris-owned Freyja Core.",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the thin OpenWebUI bridge to Freyja Core.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--no-backup", action="store_true")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backup = None if args.no_backup else str(backup_db(args.db, args.backup_dir))
    specs = await upsert_tool()
    conn = sqlite3.connect(args.db)
    try:
        models = bind_models(conn)
    finally:
        conn.close()
    print(json.dumps({"ok": True, "tool": TOOL_ID, "specs": specs, "models": models, "backup": backup}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
