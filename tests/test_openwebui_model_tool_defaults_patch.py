from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "openwebui" / "patch_model_tool_defaults.py"


def _module():
    spec = importlib.util.spec_from_file_location("patch_model_tool_defaults", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patch_adds_model_tool_defaults(tmp_path: Path) -> None:
    module = _module()
    middleware = tmp_path / "middleware.py"
    middleware.write_text(
        "    tool_ids = form_data.pop('tool_ids', None)\n"
        "    terminal_id = form_data.pop('terminal_id', None)\n",
        encoding="utf-8",
    )

    assert module.patch(middleware) is True
    text = middleware.read_text(encoding="utf-8")
    assert "((model.get('info') or {}).get('meta') or {})" in text
    assert "or (model.get('meta') or {})" in text
    assert "model_meta.get('tool_ids') or model_meta.get('toolIds')" in text
    assert module.patch(middleware) is False
