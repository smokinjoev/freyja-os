#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-evidence-refresh.json"
DEFAULT_CONTAINER = "freyja-open-webui-atlas-open-webui-1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh credential-free Freyja Open WebUI home-agent evidence in dependency order.")
    parser.add_argument("--open-webui-container", default=DEFAULT_CONTAINER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _run(args: list[str], *, allowed_returncodes: set[int] | None = None, stdout_path: Path | None = None) -> dict[str, Any]:
    allowed = allowed_returncodes or {0}
    started = time.monotonic()
    stdout_target = stdout_path.open("w", encoding="utf-8") if stdout_path else subprocess.PIPE
    try:
        proc = subprocess.run(
            args,
            cwd=REPO_ROOT,
            text=True,
            stdout=stdout_target,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        if stdout_path and hasattr(stdout_target, "close"):
            stdout_target.close()
    return {
        "command": " ".join(args),
        "returncode": proc.returncode,
        "ok": proc.returncode in allowed,
        "allowed_returncodes": sorted(allowed),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_path": str(stdout_path.relative_to(REPO_ROOT)) if stdout_path and stdout_path.is_relative_to(REPO_ROOT) else str(stdout_path) if stdout_path else None,
        "stderr_present": bool(proc.stderr),
    }


def _run_with_retry(
    args: list[str],
    *,
    attempts: int,
    allowed_returncodes: set[int] | None = None,
    stdout_path: Path | None = None,
) -> dict[str, Any]:
    runs = []
    for _ in range(max(1, attempts)):
        run = _run(args, allowed_returncodes=allowed_returncodes, stdout_path=stdout_path)
        runs.append(run)
        if run["ok"]:
            break
    result = dict(runs[-1])
    result["attempt_count"] = len(runs)
    result["attempt_returncodes"] = [run["returncode"] for run in runs]
    return result


def _snapshot_open_webui_database(container: str, target_dir: Path) -> Path | None:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied_main = False
    for filename in ("webui.db", "webui.db-wal", "webui.db-shm"):
        proc = subprocess.run(
            ["docker", "cp", f"{container}:/app/backend/data/{filename}", str(target_dir / filename)],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if filename == "webui.db":
            copied_main = proc.returncode == 0
    return target_dir / "webui.db" if copied_main else None


def refresh(container: str) -> dict[str, Any]:
    py = sys.executable
    reports = REPO_ROOT / "certification" / "reports"
    steps: list[dict[str, Any]] = []
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(
        json.dumps(
            {
                "report_type": "open-webui-home-agent-evidence-refresh",
                "generated_at_unix": int(time.time()),
                "git_head": _git_head(),
                "secrets_included": False,
                "private_content_included": False,
                "ok": False,
                "status": "in_progress",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix="open-webui-home-agent-refresh-") as tmp:
        snapshot = _snapshot_open_webui_database(container, Path(tmp))
        snapshot_step = {
            "step": "snapshot_open_webui_database",
            "ok": snapshot is not None,
            "container": container,
            "wal_and_shm_attempted": True,
        }
        steps.append(snapshot_step)
        steps.extend(
            [
                _run([py, "scripts/open-webui-home-agent-verify.py"]),
                _run([py, "scripts/inventory-open-webui-home-agent-platform.py"]),
                _run([py, "scripts/check-open-webui-model-proxy-catalog.py"]),
                _run([py, "scripts/export-open-webui-home-agents.py"]),
            ]
        )
        if snapshot is not None:
            steps.append(
                _run(
                    [
                        py,
                        "scripts/apply-open-webui-home-agents-offline.py",
                        "--import-json",
                        "certification/reports/open-webui-home-agents-import.json",
                        "--db",
                        str(snapshot),
                    ],
                    stdout_path=reports / "open-webui-home-agents-offline-apply.json",
                )
            )
            steps.append(
                _run(
                    [
                        py,
                        "scripts/audit-open-webui-home-agent-access.py",
                        "--db",
                        str(snapshot),
                        "--output",
                        "certification/reports/open-webui-home-agent-access-audit.json",
                    ]
                )
            )
        steps.extend(
            [
                _run([py, "scripts/bind-open-webui-home-agent-access.py"]),
                _run([py, "scripts/export-open-webui-home-resources.py"]),
                _run([py, "scripts/count-open-webui-home-resources-live.py"]),
                _run([py, "scripts/apply-open-webui-home-resources-offline.py"]),
                _run([py, "scripts/check-open-webui-tools-gateway.py"]),
                _run([py, "scripts/export-open-webui-tools-openapi.py"]),
                _run([py, "scripts/audit-open-webui-inference-policy.py"]),
                _run([py, "scripts/activate-open-webui-home-agent-post-auth.py"]),
                _run([py, "scripts/smoke-open-webui-home-agent-chats.py"]),
                _run([py, "scripts/check-freyja-channels-readiness.py"]),
                _run([py, "scripts/run-freyja-channels-telegram-pilot.py", "--dry-run"]),
                _run([py, "scripts/run-freyja-channels-signal-pilot.py", "--dry-run"]),
                _run([py, "scripts/check-freyja-proactive-readiness.py"]),
                _run([py, "scripts/dry-run-freyja-proactive.py"]),
                _run_with_retry([py, "scripts/audit-freyja41-preservation.py"], attempts=2),
                _run([py, "scripts/audit-open-webui-backup-rollback.py"]),
                _run([py, "scripts/audit-open-webui-home-agent-secret-safety.py"]),
                _run([py, "scripts/summarize-open-webui-home-agent-readiness.py"], allowed_returncodes={0, 1}),
                _run([py, "scripts/audit-open-webui-home-agent-completion.py"]),
            ]
        )
    return {
        "report_type": "open-webui-home-agent-evidence-refresh",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "step_count": len(steps),
        "failed_steps": [step for step in steps if not step.get("ok")],
        "ok": all(step.get("ok") for step in steps),
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = refresh(args.open_webui_container)
    report["post_refresh_bundle"] = None
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    bundle_step = _run([sys.executable, "scripts/build-open-webui-home-agent-bundle.py"])
    report["post_refresh_bundle"] = bundle_step
    report["ok"] = bool(report["ok"] and bundle_step["ok"])
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
