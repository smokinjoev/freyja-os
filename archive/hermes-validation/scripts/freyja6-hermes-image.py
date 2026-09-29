#!/usr/bin/env python3
"""Prepare the pinned Hermes Agent image for the Freyja 6 Atlas stack."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-hermes-image.json")
PLACEHOLDER_PREFIX = "replace-with-"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or build the pinned Freyja 6 Hermes Agent image.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--source", type=Path, default=Path(os.environ.get("HERMES_AGENT_SOURCE", "")) if os.environ.get("HERMES_AGENT_SOURCE") else None)
    parser.add_argument("--dockerfile", default="Dockerfile")
    parser.add_argument("--build", action="store_true", help="Build and tag the Hermes image from --source.")
    parser.add_argument("--build-timeout", type=float, default=600.0, help="Seconds to wait for docker build before failing with a JSON report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(
    *,
    env_file: Path,
    source: Path | None = None,
    dockerfile: str = "Dockerfile",
    build: bool = False,
    build_timeout: float = 600.0,
) -> dict[str, Any]:
    env = _load_env(_resolve(env_file))
    image = env.get("HERMES_AGENT_IMAGE", "")
    version = env.get("HERMES_AGENT_VERSION", "")
    source_path = source or _source_from_env(env)
    checks = [
        _check_env_value("HERMES_AGENT_IMAGE", image),
        _check_env_value("HERMES_AGENT_VERSION", version),
        _check_image_pin(image, version),
        _check_local_image(image, version),
        _check_source(source_path, dockerfile),
    ]
    build_result = _skipped("image_build", "Run with --build after selecting a Hermes Agent source checkout.")
    if build:
        build_result = _build_image(source_path, dockerfile=dockerfile, image=image, version=version, timeout=build_timeout)
        checks.append(build_result)
        if build_result["status"] == "pass":
            checks = [
                check if check["id"] != "local_image" else _check_local_image(image, version)
                for check in checks
            ]
    else:
        checks.append(build_result)

    blockers = [check for check in checks if check["status"] == "fail" and check["id"] != "local_image"]
    warnings = [check for check in checks if check["status"] == "warn" or (check["id"] == "local_image" and check["status"] == "fail")]
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-hermes-image",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": not blockers and _any_check_passed(checks, "local_image"),
        "image": image,
        "version": version,
        "source": str(source_path) if source_path else "",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "next_actions": _next_actions(blockers, warnings),
    }


def _check_env_value(key: str, value: str) -> dict[str, Any]:
    if not value or value.startswith(PLACEHOLDER_PREFIX):
        return _failed(key.lower(), f"{key} is missing or still a placeholder.")
    return _passed(key.lower(), f"{key} is populated.")


def _check_image_pin(image: str, version: str) -> dict[str, Any]:
    if not image or not version:
        return _failed("image_pin", "Hermes image and version are required.")
    if image.endswith(":latest") or image.endswith(":main") or ":" not in image:
        return _failed("image_pin", "HERMES_AGENT_IMAGE must use an immutable validation tag.")
    if _image_tag(image) != version:
        return _failed("image_pin", "HERMES_AGENT_IMAGE tag must exactly match HERMES_AGENT_VERSION.")
    return _passed("image_pin", "Hermes image tag is pinned to the configured validation version.")


def _image_tag(image: str) -> str:
    return image.rsplit(":", 1)[-1] if ":" in image else ""


def _check_local_image(image: str, version: str) -> dict[str, Any]:
    if not image:
        return _failed("local_image", "Hermes image value is missing.")
    if not shutil.which("docker"):
        return _warning("local_image", "Docker CLI is not available; cannot inspect the local Hermes image.")
    result = subprocess.run(["docker", "image", "inspect", image], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return _failed("local_image", "Pinned Hermes image is not present locally.")
    label_version = _local_image_version_label(result.stdout)
    if label_version != version:
        return _failed("local_image", "Pinned Hermes image label org.opencontainers.image.version must match HERMES_AGENT_VERSION.")
    return _passed("local_image", "Pinned Hermes image is present locally with the expected validation version label.")


def _local_image_version_label(inspect_stdout: str) -> str:
    try:
        payload = json.loads(inspect_stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return ""
    labels = payload[0].get("Config", {}).get("Labels", {})
    if not isinstance(labels, dict):
        return ""
    return str(labels.get("org.opencontainers.image.version") or "")


def _check_source(source: Path | None, dockerfile: str) -> dict[str, Any]:
    if source is None:
        return _failed("hermes_source", "Set HERMES_AGENT_SOURCE or pass --source to the Hermes Agent checkout.")
    source = source.expanduser()
    dockerfile_path = source / dockerfile
    if not source.exists():
        return _failed("hermes_source", f"Hermes Agent source does not exist: {source}.")
    if not dockerfile_path.exists():
        return _failed("hermes_source", f"Hermes Agent Dockerfile does not exist: {dockerfile_path}.")
    return _passed("hermes_source", "Hermes Agent source checkout and Dockerfile are present.")


def _build_image(source: Path | None, *, dockerfile: str, image: str, version: str, timeout: float = 600.0) -> dict[str, Any]:
    source_check = _check_source(source, dockerfile)
    if source_check["status"] != "pass":
        return {"id": "image_build", **{key: value for key, value in source_check.items() if key != "id"}}
    if not image or not version:
        return _failed("image_build", "Hermes image and version are required before building.")
    if not shutil.which("docker"):
        return _failed("image_build", "Docker CLI is not available.")
    source_path = source.expanduser() if source else Path()
    cmd = [
        "docker",
        "build",
        "-t",
        image,
        "--label",
        f"org.opencontainers.image.version={version}",
        "--label",
        "freyja.platform=6.0",
        "--label",
        "freyja.agent=freyja-test",
        "-f",
        dockerfile,
        ".",
    ]
    try:
        result = subprocess.run(cmd, cwd=source_path, text=True, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "id": "image_build",
            "status": "fail",
            "message": f"Docker build timed out after {timeout:g} seconds.",
            "stdout_tail": (exc.stdout or "")[-1000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
        }
    if result.returncode != 0:
        return {
            "id": "image_build",
            "status": "fail",
            "message": "Docker could not build the pinned Hermes Agent image.",
            "stderr_tail": result.stderr[-1000:],
        }
    return _passed("image_build", "Built the pinned Hermes Agent image.")


def _source_from_env(env: dict[str, str]) -> Path | None:
    raw = env.get("HERMES_AGENT_SOURCE", "")
    return Path(raw).expanduser() if raw else None


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


def _any_check_passed(checks: list[dict[str, Any]], check_id: str) -> bool:
    return any(check["id"] == check_id and check["status"] == "pass" for check in checks)


def _next_actions(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    if blockers:
        return [str(blocker["message"]) for blocker in blockers]
    if warnings:
        return ["Build or inspect the pinned Hermes Agent image before starting compose."]
    return ["Run Freyja 6 Atlas preflight and start the compose stack."]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _warning(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "warn", "message": message}


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _skipped(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "skip", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-hermes-image",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = (
        _error_report(output_failure)
        if output_failure
        else build_report(
            env_file=args.env_file,
            source=args.source,
            dockerfile=args.dockerfile,
            build=args.build,
            build_timeout=args.build_timeout,
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
