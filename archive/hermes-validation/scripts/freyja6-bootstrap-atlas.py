#!/usr/bin/env python3
"""Bootstrap Freyja 6.0 host directories and seed files on Atlas."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-bootstrap-atlas.json")
IDENTITY_TEMPLATE = Path("config/freyja6/bootstrap/identity.md")
APPROVED_SMOKE_TEMPLATE = Path("config/freyja6/bootstrap/approved-smoke.txt")
REQUIRED_ROOT_KEYS = ("FREYJA6_APPROVED_FILES_ROOT", "FREYJA6_LOG_ROOT", "FREYJA6_HERMES_DATA")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Freyja 6.0 Atlas validation directories.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Overwrite seed files if they already exist.")
    return parser


def bootstrap(*, env_file: Path, force: bool = False) -> dict[str, Any]:
    env_path = _resolve(env_file)
    env = _load_env(env_path)
    checks = [_check_env_file(env_path), _check_required_roots(env)]
    failures = [check for check in checks if check["status"] == "fail"]
    if failures:
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-bootstrap-atlas",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "env_file": str(env_file),
            "force": force,
            "checks": checks,
            "created_dirs": [],
            "writes": [],
            "failures": failures,
            "next_actions": [str(failures[0]["message"])],
        }
    roots = {
        "approved": Path(env.get("FREYJA6_APPROVED_FILES_ROOT", "/srv/freyja6/approved-files")).expanduser(),
        "logs": Path(env.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs")).expanduser(),
        "hermes": Path(env.get("FREYJA6_HERMES_DATA", "/srv/freyja6/hermes")).expanduser(),
    }
    created_dirs = []
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(str(path))

    agent_root = roots["hermes"] / "agents" / "freyja-test"
    session_dir = agent_root / "sessions"
    private_memory_dir = agent_root / "memory" / "private"
    for path in (agent_root, session_dir, private_memory_dir):
        path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(str(path))

    seed_targets = [
        {"label": "identity", "path": agent_root / "identity.md"},
        {"label": "approved_smoke_file", "path": roots["approved"] / "smoke.txt"},
        *[
            {"label": log_name, "path": roots["logs"] / log_name}
            for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl")
        ],
    ]
    target_failures = _seed_target_failures(seed_targets)
    if target_failures:
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-bootstrap-atlas",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "env_file": str(env_file),
            "force": force,
            "checks": checks
            + [
                {
                    "id": "seed_targets",
                    "status": "fail",
                    "message": "Bootstrap seed targets must be regular files and must not be symlinks.",
                    "failures": target_failures,
                }
            ],
            "created_dirs": sorted(set(created_dirs)),
            "writes": [],
            "failures": [
                {
                    "id": "seed_targets",
                    "status": "fail",
                    "message": "Bootstrap seed targets must be regular files and must not be symlinks.",
                    "failures": target_failures,
                }
            ],
            "next_actions": ["Remove or replace unsafe bootstrap seed targets before rerunning bootstrap."],
        }

    writes = []
    writes.append(
        _copy_template(
            _resolve(IDENTITY_TEMPLATE),
            agent_root / "identity.md",
            force=force,
            label="identity",
        )
    )
    writes.append(
        _copy_template(
            _resolve(APPROVED_SMOKE_TEMPLATE),
            roots["approved"] / "smoke.txt",
            force=force,
            label="approved_smoke_file",
        )
    )
    for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"):
        log_path = roots["logs"] / log_name
        if not log_path.exists():
            log_path.touch()
            writes.append({"label": log_name, "path": str(log_path), "action": "created"})
        else:
            writes.append({"label": log_name, "path": str(log_path), "action": "preserved"})

    return {
        "schema_version": "1.0",
        "report_type": "freyja6-bootstrap-atlas",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "status": "pass",
        "env_file": str(env_file),
        "force": force,
        "checks": checks,
        "created_dirs": sorted(set(created_dirs)),
        "writes": writes,
        "identity_file": str(agent_root / "identity.md"),
        "approved_smoke_file": str(roots["approved"] / "smoke.txt"),
        "log_root": str(roots["logs"]),
        "failures": [],
        "next_actions": ["Continue with live stack status and acceptance evidence capture."],
    }


def _check_env_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _failed("env_file", "Bootstrap requires an explicit Freyja 6 env file; .env.example is not used for host writes.")
    if not path.is_file() or path.is_symlink():
        return _failed("env_file", "Bootstrap env file must be a regular file.")
    return _passed("env_file", "Bootstrap env file exists.")


def _check_required_roots(env: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ROOT_KEYS if not env.get(key, "").strip()]
    placeholders = [key for key in REQUIRED_ROOT_KEYS if _looks_placeholder(env.get(key, ""))]
    unsafe = [
        {"key": key, "path": env.get(key, ""), "reason": _unsafe_root_reason(env.get(key, ""))}
        for key in REQUIRED_ROOT_KEYS
        if env.get(key, "").strip() and _unsafe_root_reason(env.get(key, ""))
    ]
    if missing or placeholders or unsafe:
        return {
            "id": "required_roots",
            "status": "fail",
            "message": "Bootstrap root paths must be explicit, non-placeholder, and Freyja 6 scoped.",
            "missing": missing,
            "placeholders": placeholders,
            "unsafe": unsafe,
        }
    return _passed("required_roots", "Bootstrap root paths are explicit and Freyja 6 scoped.")


def _looks_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("replace-with", "example", "placeholder", "<", ">"))


def _unsafe_root_reason(value: str) -> str:
    path = Path(value).expanduser()
    if str(path) in {"/", "/srv", "/var", "/tmp", str(Path.home())}:
        return "must not point at a broad host root"
    if path.is_symlink():
        return "must not be a symlink"
    if "freyja6" not in {part.lower() for part in path.parts}:
        return "must stay under a freyja6-specific host path"
    return ""


def _copy_template(source: Path, target: Path, *, force: bool, label: str) -> dict[str, str]:
    if target.exists() and not force:
        return {"label": label, "path": str(target), "action": "preserved"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return {"label": label, "path": str(target), "action": "overwritten" if force else "created"}


def _seed_target_failures(targets: list[dict[str, Path | str]]) -> list[dict[str, str]]:
    failures = []
    for target in targets:
        label = str(target["label"])
        path = target["path"]
        if not isinstance(path, Path):
            path = Path(path)
        if path.is_symlink():
            failures.append({"label": label, "path": str(path), "reason": "must not be a symlink"})
        elif path.exists() and not path.is_file():
            failures.append({"label": label, "path": str(path), "reason": "must be a regular file"})
    return failures


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _expand_env_value(value.strip(), values)
    return values


def _expand_env_value(value: str, values: dict[str, str]) -> str:
    expanded = value
    for key, replacement in values.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return expanded


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-bootstrap-atlas",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
        "created_dirs": [],
        "writes": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = _error_report(output_failure) if output_failure else bootstrap(env_file=args.env_file, force=args.force)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
