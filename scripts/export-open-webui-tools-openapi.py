#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.main import app


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-tools-openapi.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the Open WebUI tool gateway OpenAPI schema without secrets.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_schema() -> dict[str, Any]:
    full = app.openapi()
    paths = {
        path: value
        for path, value in (full.get("paths") or {}).items()
        if path.startswith("/open-webui-tools")
    }
    schemas = full.get("components", {}).get("schemas", {})
    selected_schema_names = {
        "ToolCatalogResponse",
        "ToolInvocationRequest",
        "ToolInvocationResponse",
        "ToolOperation",
        "HTTPValidationError",
        "ValidationError",
    }
    selected_schemas = {
        name: schema
        for name, schema in schemas.items()
        if name in selected_schema_names
    }
    return {
        "openapi": full.get("openapi"),
        "info": {
            "title": "Freyja Open WebUI Tool Gateway",
            "version": full.get("info", {}).get("version", "0.1.0"),
            "description": "Narrow deny-by-default tool boundary for Open WebUI family agents.",
        },
        "paths": paths,
        "components": {"schemas": selected_schemas},
        "x-freyja": {
            "secrets_included": False,
            "private_content_included": False,
            "boundary": "openapi",
            "live_side_effects_default": "suppressed_or_denied",
            "auth": "FREYJA_CONNECTOR_TOKEN bearer or x-api-key when configured",
        },
    }


def validate_schema(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paths = schema.get("paths") or {}
    if set(paths) != {"/open-webui-tools", "/open-webui-tools/invoke"}:
        errors.append("schema must include only the Open WebUI tool gateway paths")
    if schema.get("x-freyja", {}).get("secrets_included") is not False:
        errors.append("schema must be marked secret-free")
    serialized = json.dumps(schema, sort_keys=True)
    for forbidden in ("FREYJA_CONNECTOR_TOKEN=", "Bearer ", "api_token", "password"):
        if forbidden in serialized:
            errors.append(f"schema includes forbidden token marker: {forbidden}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schema = build_schema()
    errors = validate_schema(schema)
    report = {
        "report_type": "open-webui-tools-openapi-export",
        "secrets_included": False,
        "private_content_included": False,
        "ok": not errors,
        "validation_errors": errors,
        "schema": schema,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
