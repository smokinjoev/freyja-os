#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(REPO_ROOT / "src"))

from fastapi import FastAPI
from freyja.home_memory import home_memory_router


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-memory-openapi.json"
MEMORY_PATHS = {
    "/freyja-home-memory/operations",
    "/freyja-home-memory/search",
    "/freyja-home-memory/recent-events",
    "/freyja-home-memory/remember",
    "/freyja-home-memory/update",
    "/freyja-home-memory/record-decision",
    "/freyja-home-memory/forget/{scope}/{record_id}",
}
SCHEMA_NAMES = {
    "HomeMemoryRecord",
    "HomeMemorySearchResponse",
    "HomeMemoryWriteRequest",
    "HTTPValidationError",
    "ValidationError",
}


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Freyja Home Memory OpenAPI schema for Open WebUI.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_schema() -> dict[str, Any]:
    app = FastAPI(title="Freyja Home Memory", version="0.1.0")
    app.include_router(home_memory_router)
    full = app.openapi()
    paths = {
        path: value
        for path, value in (full.get("paths") or {}).items()
        if path in MEMORY_PATHS
    }
    schemas = full.get("components", {}).get("schemas", {})
    return {
        "openapi": full.get("openapi"),
        "info": {
            "title": "Freyja Home Memory",
            "version": full.get("info", {}).get("version", "0.1.0"),
            "description": (
                "Scoped local memory/context service for Open WebUI family agents. "
                "Use native Open WebUI Memory for private per-user preferences and this service for "
                "explicit shared household, project, and restricted Benedict memory."
            ),
        },
        "paths": paths,
        "components": {
            "schemas": {name: schema for name, schema in schemas.items() if name in SCHEMA_NAMES},
            "securitySchemes": {
                "FreyjaConnectorToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "x-api-key",
                    "description": "FREYJA_CONNECTOR_TOKEN value configured outside source control.",
                },
                "FreyjaMemoryPrincipal": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "x-freyja-client-subject",
                    "description": "Scoped principal such as person:joe, agent:cloyd, or agent:benedict.",
                },
            },
        },
        "security": [{"FreyjaConnectorToken": [], "FreyjaMemoryPrincipal": []}],
        "x-freyja": {
            "secrets_included": False,
            "private_content_included": False,
            "boundary": "openapi",
            "service": "freyja-home-memory",
            "required_headers": ["x-api-key", "x-freyja-client-type", "x-freyja-client-subject"],
            "scopes": ["personal:joe", "personal:beth", "personal:liam", "personal:jenna", "household", "project:freyja-os", "restricted:benedict"],
            "operations": ["search", "remember", "update", "forget", "record-decision", "recent-events"],
        },
    }


def validate_schema(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(schema.get("paths") or {}) != MEMORY_PATHS:
        errors.append("schema must include exactly the Freyja Home Memory paths")
    if schema.get("x-freyja", {}).get("secrets_included") is not False:
        errors.append("schema must be marked secret-free")
    serialized = json.dumps(schema, sort_keys=True)
    for forbidden in ("FREYJA_CONNECTOR_TOKEN=", "Bearer ", "password", "TELEGRAM_BOT_TOKEN", "SIGNAL_ACCOUNT_NUMBER"):
        if forbidden in serialized:
            errors.append(f"schema includes forbidden marker: {forbidden}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schema = build_schema()
    errors = validate_schema(schema)
    report = {
        "report_type": "open-webui-home-memory-openapi-export",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
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
