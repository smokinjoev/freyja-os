#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


MIDDLEWARE_PATH = Path("/app/backend/open_webui/utils/middleware.py")


OLD = "    tool_ids = form_data.pop('tool_ids', None)\n"
NEW = (
    "    tool_ids = form_data.pop('tool_ids', None)\n"
    "    if tool_ids is None:\n"
    "        model_meta = (model.get('info', {}).get('meta', {}) or {})\n"
    "        tool_ids = model_meta.get('tool_ids') or model_meta.get('toolIds')\n"
)


def patch(path: Path = MIDDLEWARE_PATH) -> bool:
    text = path.read_text(encoding="utf-8")
    if NEW in text:
        return False
    if OLD not in text:
        raise RuntimeError("OpenWebUI middleware tool_ids target line not found")
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    return True


def main() -> int:
    changed = patch()
    print({"ok": True, "changed": changed, "path": str(MIDDLEWARE_PATH)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
