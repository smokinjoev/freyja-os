#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists() and Path(sys.executable) != venv_python:
        os.execv(str(venv_python), [str(venv_python), *sys.argv])

    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    root_path = str(repo_root)
    if root_path not in sys.path:
        sys.path.insert(1, root_path)

    import uvicorn

    host = os.getenv("MACAGENT_HOST", "127.0.0.1")
    port = int(os.getenv("MACAGENT_PORT", "8765"))
    uvicorn.run("freyja.macagent_app:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
