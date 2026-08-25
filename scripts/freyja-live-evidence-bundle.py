#!/usr/bin/env python3
"""Run the live Freyja 2.0 messaging and inference evidence bundle."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and Path(sys.executable) != _VENV_PYTHON:
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])
_DEFAULT_PYTHON = str(_VENV_PYTHON if _VENV_PYTHON.exists() else Path(sys.executable))
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Freyja 2.0 evidence bundle: iMessage/terminal route "
            "equivalence plus Vulcan QA and iterative coding suites."
        )
    )
    parser.add_argument("--python", default=_DEFAULT_PYTHON)
    parser.add_argument("--output-dir", type=Path, default=Path("certification/reports"))
    parser.add_argument("--director-url", default="http://127.0.0.1:8000")
    parser.add_argument("--vulcan-url", default=os.environ.get("OLLAMA_REASONING_BASE_URL", "http://100.115.228.56:11434"))
    parser.add_argument("--vulcan-model", default=os.environ.get("OLLAMA_REASONING_MODEL", "gpt-oss-freyja:20b-analysis-prefill"))
    parser.add_argument("--suite", default="inference/freyja_qa_100")
    parser.add_argument("--coding-suite", default="inference/freyja_iterative_coding")
    parser.add_argument("--connector-report", type=Path)
    parser.add_argument("--summary-report", type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--route-smoke-person-id", default="joe")
    parser.add_argument("--route-smoke-person-display-name", default="Joe")
    parser.add_argument("--route-smoke-person-preferred-name", default="Joe")
    parser.add_argument("--route-smoke-agent-id", default="cloyd-gibbler")
    parser.add_argument("--route-smoke-agent-display-name", default="Cloyd Gibbler")
    parser.add_argument("--route-smoke-expected-provider", default="local_reasoning")
    parser.add_argument(
        "--sync-imessage-runtime",
        action="store_true",
        help="Sync the LaunchAgent runtime checkout from this checkout and restart iMessage before evidence checks.",
    )
    parser.add_argument(
        "--run-inference-with-failed-preflight",
        action="store_true",
        help="Run the 100-question inference suite even when Vulcan preflight fails.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the commands and write no reports.",
    )
    return parser


def build_sync_command(args: argparse.Namespace) -> list[str]:
    return ["scripts/sync-imessage-runtime.sh"] if args.sync_imessage_runtime else []


def build_messaging_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "scripts/messaging-production-check.py",
        "--connector",
        "imessage",
        "--check-director",
        "--check-rev2-director",
        "--check-imessage-route-smoke",
        "--check-inprocess-route-smoke",
        "--route-smoke-person-id",
        args.route_smoke_person_id,
        "--route-smoke-person-display-name",
        args.route_smoke_person_display_name,
        "--route-smoke-person-preferred-name",
        args.route_smoke_person_preferred_name,
        "--route-smoke-agent-id",
        args.route_smoke_agent_id,
        "--route-smoke-agent-display-name",
        args.route_smoke_agent_display_name,
        "--route-smoke-expected-provider",
        args.route_smoke_expected_provider,
        "--output",
        str(_connector_report(args)),
    ]


def build_inference_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "-m",
        "certification.cli",
        args.suite,
        "--provider",
        "local_reasoning",
        "--model",
        args.vulcan_model,
        "--output-dir",
        str(args.output_dir),
    ]


def build_coding_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "-m",
        "certification.cli",
        args.coding_suite,
        "--provider",
        "local_reasoning",
        "--model",
        args.vulcan_model,
        "--output-dir",
        str(args.output_dir),
    ]


def inference_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env["OLLAMA_REASONING_BASE_URL"] = args.vulcan_url
    env["OLLAMA_REASONING_MODEL"] = args.vulcan_model
    return env


async def vulcan_preflight(args: argparse.Namespace) -> dict[str, Any]:
    from freyja.ollama_client import OllamaClient

    client = OllamaClient(args.vulcan_url, args.vulcan_model)
    result: dict[str, Any] = {
        "base_url": args.vulcan_url,
        "model": args.vulcan_model,
        "host_reachable": False,
        "model_available": False,
        "ok": False,
    }
    tags = await client.tags()
    if "error" in tags:
        result["error"] = _clip(str(tags["error"]))
        return result
    result["host_reachable"] = True
    models = [
        str(model.get("name") or "")
        for model in tags.get("models", [])
        if isinstance(model, dict)
    ]
    result["model_count"] = len([name for name in models if name])
    result["model_available"] = args.vulcan_model in models or any(
        name.startswith(f"{args.vulcan_model}:") for name in models
    )
    result["ok"] = result["host_reachable"] is True and result["model_available"] is True
    if not result["model_available"]:
        result["error"] = "model_not_listed"
    return result


def _connector_report(args: argparse.Namespace) -> Path:
    return args.connector_report or args.output_dir / "freyja-live-imessage-route-evidence.json"


def _summary_report(args: argparse.Namespace) -> Path:
    return args.summary_report or args.output_dir / "freyja-live-evidence-summary.json"


def _print_command(command: list[str], *, env_prefix: dict[str, str] | None = None) -> None:
    prefix = ""
    if env_prefix:
        prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env_prefix.items()) + " "
    print(prefix + shlex.join(command), flush=True)


def _extract_report(output: str, prefix: str) -> str | None:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clip(value: str, limit: int = 160) -> str:
    return " ".join(value.split())[:limit]


def _clip_tail(value: str, limit: int = 160) -> str:
    return " ".join(value.split())[-limit:]


def _summarize_connector(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    imessage = payload.get("imessage") if isinstance(payload.get("imessage"), dict) else {}
    live = imessage.get("synthetic_route_smoke") if isinstance(imessage.get("synthetic_route_smoke"), dict) else {}
    inprocess = imessage.get("inprocess_route_smoke") if isinstance(imessage.get("inprocess_route_smoke"), dict) else {}
    drift = imessage.get("runtime_source_drift") if isinstance(imessage.get("runtime_source_drift"), dict) else {}
    import_check = imessage.get("runtime_import_check") if isinstance(imessage.get("runtime_import_check"), dict) else {}
    return {
        "path": str(path),
        "ready_for_live_smoke": imessage.get("ready_for_live_smoke"),
        "runtime_source_drift_ok": drift.get("ok"),
        "runtime_source_drift_count": drift.get("drift_count"),
        "runtime_import_ok": import_check.get("ok"),
        "runtime_import_error": import_check.get("stderr") or import_check.get("error"),
        "live_route_smoke_ok": live.get("ok"),
        "inprocess_route_smoke_ok": inprocess.get("ok"),
        "terminal_equivalent": live.get("terminal_equivalent") or inprocess.get("terminal_equivalent"),
        "prompt_context_equivalent": inprocess.get("prompt_context_equivalent"),
        "director_health_ok": (imessage.get("director_health") or {}).get("ok") if isinstance(imessage.get("director_health"), dict) else None,
    }


def _summarize_inference(path: Path | None) -> dict[str, Any]:
    payload = _read_json(path)
    speed = payload.get("speed_metrics") if isinstance(payload.get("speed_metrics"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    overall_score = payload.get("overall_score")
    if overall_score is None:
        overall_score = metadata.get("overall_score")
    failure_summary = _inference_failure_summary(cases)
    return {
        "path": str(path) if path else None,
        "passed": payload.get("passed"),
        "overall_score": overall_score,
        "passing_score": payload.get("passing_score"),
        "mean_generation_tokens_per_second": speed.get("mean_generation_tokens_per_second"),
        "speed_samples": speed.get("measured_cases"),
        "total_cases": len(cases),
        "failed_cases": failure_summary["failed_cases"],
        "failure_summary": failure_summary,
    }


def _inference_failure_summary(cases: list[Any]) -> dict[str, Any]:
    errors: dict[str, int] = {}
    categories: dict[str, int] = {}
    missing_keywords: dict[str, int] = {}
    forbidden_matches: dict[str, int] = {}
    failed_cases = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        if case.get("passed") is True:
            continue
        failed_cases += 1
        category = _case_failure_category(case)
        categories[category] = categories.get(category, 0) + 1
        error = str(case.get("error") or "").strip()
        if not error:
            error = "verification_failed"
        errors[error] = errors.get(error, 0) + 1
        for keyword in case.get("missing_keywords") or ():
            if isinstance(keyword, str) and keyword:
                missing_keywords[keyword] = missing_keywords.get(keyword, 0) + 1
        for keyword in case.get("forbidden_matches") or ():
            if isinstance(keyword, str) and keyword:
                forbidden_matches[keyword] = forbidden_matches.get(keyword, 0) + 1
    top_errors = [
        {"error": error, "count": count}
        for error, count in sorted(errors.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    top_categories = [
        {"category": category, "count": count}
        for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    first_error = top_errors[0]["error"] if top_errors else None
    connection_failed = (
        failed_cases > 0
        and len(errors) == 1
        and first_error is not None
        and "connection" in first_error.lower()
    )
    return {
        "failed_cases": failed_cases,
        "unique_error_count": len(errors),
        "top_errors": top_errors,
        "top_categories": top_categories,
        "top_missing_keywords": _top_counts(missing_keywords, key_name="keyword"),
        "top_forbidden_matches": _top_counts(forbidden_matches, key_name="keyword"),
        "first_error": first_error,
        "all_failures_are_connection_errors": connection_failed,
    }


def _case_failure_category(case: dict[str, Any]) -> str:
    name = str(case.get("name") or "").strip()
    if "-" in name:
        return name.rsplit("-", 1)[0]
    category = str(case.get("category") or "").strip()
    return category or "unknown"


def _top_counts(values: dict[str, int], *, key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: value, "count": count}
        for value, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]


def _completion_gates(summary: dict[str, Any]) -> dict[str, bool]:
    messaging = summary.get("messaging") if isinstance(summary.get("messaging"), dict) else {}
    inference = summary.get("inference") if isinstance(summary.get("inference"), dict) else {}
    coding = summary.get("coding") if isinstance(summary.get("coding"), dict) else {}
    preflight = summary.get("vulcan_preflight") if isinstance(summary.get("vulcan_preflight"), dict) else {}
    failure_summary = (
        inference.get("failure_summary")
        if isinstance(inference.get("failure_summary"), dict)
        else {}
    )
    passing_score = _as_float(inference.get("passing_score"))
    overall_score = _as_float(inference.get("overall_score"))
    speed_samples = _as_int(inference.get("speed_samples"))
    speed = _as_float(inference.get("mean_generation_tokens_per_second"))
    coding_speed_samples = _as_int(coding.get("speed_samples"))
    coding_speed = _as_float(coding.get("mean_generation_tokens_per_second"))
    return {
        "imessage_runtime_synced": (
            messaging.get("runtime_source_drift_ok") is True
            and messaging.get("runtime_import_ok") is True
        ),
        "imessage_terminal_equivalent": (
            messaging.get("inprocess_route_smoke_ok") is True
            and messaging.get("terminal_equivalent") is True
            and messaging.get("prompt_context_equivalent") is True
        ),
        "live_imessage_route_smoke": (
            messaging.get("ready_for_live_smoke") is True
            and messaging.get("live_route_smoke_ok") is True
        ),
        "vulcan_preflight": preflight.get("ok") is True,
        "vulcan_inference_accuracy": (
            inference.get("passed") is True
            and overall_score is not None
            and passing_score is not None
            and passing_score >= 0.95
            and overall_score >= passing_score
        ),
        "vulcan_speed_measured": speed_samples is not None and speed_samples > 0 and speed is not None and speed > 0,
        "vulcan_iterative_coding": (
            coding.get("passed") is True
            and coding_speed_samples is not None
            and coding_speed_samples > 0
            and coding_speed is not None
            and coding_speed > 0
        ),
    }


def _action_items(summary: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    runtime_sync = summary.get("runtime_sync") if isinstance(summary.get("runtime_sync"), dict) else {}
    messaging = summary.get("messaging") if isinstance(summary.get("messaging"), dict) else {}
    inference = summary.get("inference") if isinstance(summary.get("inference"), dict) else {}
    coding = summary.get("coding") if isinstance(summary.get("coding"), dict) else {}
    preflight = summary.get("vulcan_preflight") if isinstance(summary.get("vulcan_preflight"), dict) else {}
    failure_summary = (
        inference.get("failure_summary")
        if isinstance(inference.get("failure_summary"), dict)
        else {}
    )

    if runtime_sync.get("returncode") not in {None, 0}:
        actions.append("Fix scripts/sync-imessage-runtime.sh failure, then rerun the evidence bundle.")
    elif messaging.get("runtime_source_drift_ok") is False:
        actions.append("Run scripts/freyja-live-evidence-bundle.py --sync-imessage-runtime from a normal terminal.")
    if messaging.get("runtime_import_ok") is False:
        detail = _clip_tail(str(messaging.get("runtime_import_error") or "runtime import check failed"), limit=120)
        actions.append(f"Fix iMessage runtime import failure before restarting live messaging: {detail}")

    if messaging.get("director_health_ok") is False or messaging.get("live_route_smoke_ok") is False:
        actions.append("Run the live route smoke from an environment that can reach Director localhost and the iMessage LaunchAgent.")

    speed_samples = _as_int(inference.get("speed_samples"))
    if preflight.get("host_reachable") is False:
        actions.append("Fix connectivity to Vulcan before running the 100-question inference and iterative coding gates.")
    elif preflight.get("model_available") is False:
        actions.append("Install or expose the configured Vulcan model before running the 100-question inference and iterative coding gates.")
    elif inference.get("passed") is not True and failure_summary.get("all_failures_are_connection_errors") is True:
        actions.append("Fix connectivity to Vulcan before judging model quality; all 100-question failures are connection errors.")
    elif inference.get("passed") is not True and speed_samples == 0:
        actions.append("Run the 100-question suite from a host that can reach Vulcan at the configured OLLAMA_REASONING_BASE_URL.")
    elif inference.get("passed") is not True:
        actions.append("Inspect the 100-question inference report and make systemic routing/model fixes before accepting Freyja 2.0.")

    if preflight.get("ok") is True and coding.get("passed") is not True:
        actions.append("Inspect the iterative coding report and fix the Vulcan to Smith/Qwen coding lane systemically.")

    return actions


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_summary(
    args: argparse.Namespace,
    *,
    sync_command: list[str],
    sync_returncode: int | None,
    messaging_command: list[str],
    messaging_returncode: int,
    inference_command: list[str],
    inference_returncode: int,
    inference_report: Path | None,
    coding_command: list[str] | None = None,
    coding_returncode: int = 1,
    coding_report: Path | None = None,
    vulcan_preflight: dict[str, Any] | None = None,
    inference_skipped: bool = False,
    inference_skip_reason: str | None = None,
    coding_skipped: bool = False,
    coding_skip_reason: str | None = None,
) -> Path:
    connector_report = _connector_report(args)
    sync_ok = sync_returncode in {None, 0}
    summary = {
        "ok": False,
        "director_url": args.director_url,
        "vulcan_url": args.vulcan_url,
        "vulcan_model": args.vulcan_model,
        "vulcan_preflight": vulcan_preflight or {},
        "runtime_sync": {
            "requested": bool(args.sync_imessage_runtime),
            "returncode": sync_returncode,
            "command": sync_command,
        },
        "messaging": {
            "returncode": messaging_returncode,
            "command": messaging_command,
            **_summarize_connector(connector_report),
        },
        "inference": {
            "returncode": inference_returncode,
            "command": inference_command,
            "skipped": inference_skipped,
            "skip_reason": inference_skip_reason,
            **_summarize_inference(inference_report),
        },
        "coding": {
            "returncode": coding_returncode,
            "command": coding_command or [],
            "skipped": coding_skipped,
            "skip_reason": coding_skip_reason,
            **_summarize_inference(coding_report),
        },
    }
    gates = _completion_gates(summary)
    summary["completion_gates"] = {
        **gates,
        "all_gates_passed": all(gates.values()),
    }
    summary["action_items"] = _action_items(summary)
    summary["ok"] = (
        sync_ok
        and messaging_returncode == 0
        and inference_returncode == 0
        and coding_returncode == 0
        and summary["completion_gates"]["all_gates_passed"] is True
    )
    path = _summary_report(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sync_command = build_sync_command(args)
    messaging_command = build_messaging_command(args)
    inference_command = build_inference_command(args)
    coding_command = build_coding_command(args)
    inference_env_prefix = {
        "OLLAMA_REASONING_BASE_URL": args.vulcan_url,
        "OLLAMA_REASONING_MODEL": args.vulcan_model,
    }

    if sync_command:
        _print_command(sync_command)
    _print_command(messaging_command)
    _print_command(inference_command, env_prefix=inference_env_prefix)
    _print_command(coding_command, env_prefix=inference_env_prefix)
    if args.print_only:
        return 0

    sync_returncode: int | None = None
    if sync_command:
        sync = subprocess.run(sync_command, text=True, capture_output=True)
        sync_returncode = sync.returncode
        print(sync.stdout, end="")
        if sync.stderr:
            print(sync.stderr, end="", file=sys.stderr)
    if sync_returncode not in {None, 0}:
        messaging_returncode = 1
        inference_returncode = 1
        summary = write_summary(
            args,
            sync_command=sync_command,
            sync_returncode=sync_returncode,
            messaging_command=messaging_command,
            messaging_returncode=messaging_returncode,
            inference_command=inference_command,
            inference_returncode=inference_returncode,
            inference_report=None,
            coding_command=coding_command,
            coding_returncode=1,
            coding_report=None,
            vulcan_preflight=None,
            inference_skipped=True,
            inference_skip_reason="runtime_sync_failed",
            coding_skipped=True,
            coding_skip_reason="runtime_sync_failed",
        )
        print(f"Summary report: {summary}")
        return 1

    preflight = asyncio.run(vulcan_preflight(args))
    print("Vulcan preflight: " + json.dumps(preflight, sort_keys=True), flush=True)

    messaging = subprocess.run(messaging_command, text=True, capture_output=True)
    print(messaging.stdout, end="")
    if messaging.stderr:
        print(messaging.stderr, end="", file=sys.stderr)

    inference_returncode = 1
    inference_report = None
    inference_skipped = False
    inference_skip_reason = None
    coding_returncode = 1
    coding_report = None
    coding_skipped = False
    coding_skip_reason = None
    if preflight.get("ok") is not True and not args.run_inference_with_failed_preflight:
        inference_skipped = True
        inference_skip_reason = "vulcan_preflight_failed"
        coding_skipped = True
        coding_skip_reason = "vulcan_preflight_failed"
        print("Inference skipped: Vulcan preflight failed.", flush=True)
    else:
        inference = subprocess.run(inference_command, text=True, capture_output=True, env=inference_env(args))
        inference_returncode = inference.returncode
        print(inference.stdout, end="")
        if inference.stderr:
            print(inference.stderr, end="", file=sys.stderr)
        inference_report_value = _extract_report(inference.stdout, "JSON report:")
        inference_report = Path(inference_report_value) if inference_report_value else None
        coding_result = subprocess.run(coding_command, text=True, capture_output=True, env=inference_env(args))
        coding_returncode = coding_result.returncode
        print(coding_result.stdout, end="")
        if coding_result.stderr:
            print(coding_result.stderr, end="", file=sys.stderr)
        coding_report_value = _extract_report(coding_result.stdout, "JSON report:")
        coding_report = Path(coding_report_value) if coding_report_value else None

    summary = write_summary(
        args,
        sync_command=sync_command,
        sync_returncode=sync_returncode,
        messaging_command=messaging_command,
        messaging_returncode=messaging.returncode,
        inference_command=inference_command,
        inference_returncode=inference_returncode,
        inference_report=inference_report,
        coding_command=coding_command,
        coding_returncode=coding_returncode,
        coding_report=coding_report,
        vulcan_preflight=preflight,
        inference_skipped=inference_skipped,
        inference_skip_reason=inference_skip_reason,
        coding_skipped=coding_skipped,
        coding_skip_reason=coding_skip_reason,
    )
    print(f"Summary report: {summary}")
    return 0 if messaging.returncode == 0 and inference_returncode == 0 and coding_returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
