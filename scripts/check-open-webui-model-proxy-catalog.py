#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-model-proxy-catalog.json"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "open-webui-home-agents.yaml"
DEFAULT_URL = "http://100.119.235.114:3001/api/models"
DEFAULT_CONTAINER = "freyja-open-webui-atlas-open-webui-1"
DEFAULT_CONTAINER_URL = "http://model-proxy:8080/v1/models"
AGENT_MODEL_IDS = {
    "freyja": "agent/freyja",
    "cloyd": "agent/cloyd-gibbler",
    "benedict": "agent/benedict",
    "agent-44": "agent/agent-47",
    "jenna": "agent/jennacide",
}
EXPECTED_AGENT_MODELS = set(AGENT_MODEL_IDS.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the Open WebUI model-proxy catalog without exposing secrets.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--container-url", default=DEFAULT_CONTAINER_URL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--open-webui-api-key", default=os.environ.get("OPEN_WEBUI_API_KEY"))
    parser.add_argument("--no-container-probe", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def fetch_model_ids(url: str, timeout: float, api_key: str | None = None) -> tuple[list[str], int, str | None]:
    try:
        request = urllib.request.Request(url)
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            raw_models = payload if isinstance(payload, list) else payload.get("data") or []
            ids = [str(item.get("id")) for item in raw_models if isinstance(item, dict) and item.get("id")]
            return sorted(ids), response.status, None
    except urllib.error.HTTPError as exc:
        exc.read()
        return [], exc.code, None
    except Exception as exc:
        return [], 0, exc.__class__.__name__


def fetch_model_ids_from_container(container: str, url: str, timeout: float) -> tuple[list[str], int, str | None]:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "python",
            "-c",
            (
                "import json,sys,urllib.request;"
                "u=sys.argv[1];t=float(sys.argv[2]);"
                "r=urllib.request.urlopen(u,timeout=t);"
                "print(json.dumps({'status':r.status,'body':json.loads(r.read().decode())}))"
            ),
            url,
            str(timeout),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return [], 0, "ContainerProbeFailed"
    try:
        payload = json.loads(proc.stdout)
        body = payload.get("body") or {}
        ids = [str(item.get("id")) for item in body.get("data") or [] if isinstance(item, dict) and item.get("id")]
        return sorted(ids), int(payload.get("status") or 0), None
    except Exception as exc:
        return [], 0, exc.__class__.__name__


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("secrets_included") is not False:
        raise ValueError("agent manifest must be a secret-free mapping")
    return data


def manifest_agent_profiles(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = manifest.get("model_profiles") if isinstance(manifest.get("model_profiles"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for agent in manifest.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id") or "")
        model_id = AGENT_MODEL_IDS.get(agent_id)
        profile_id = str(agent.get("model_profile") or "")
        profile = profiles.get(profile_id) if isinstance(profiles.get(profile_id), dict) else {}
        if not model_id:
            continue
        result[model_id] = {
            "agent_id": agent_id,
            "model_profile": profile_id,
            "provider": profile.get("provider"),
            "local_model": profile.get("model"),
            "keep_local": bool(profile.get("keep_local")),
        }
    return result


def build_report(
    model_ids: list[str],
    *,
    status: int = 200,
    error: str | None = None,
    url: str = DEFAULT_URL,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    present = sorted(EXPECTED_AGENT_MODELS & set(model_ids))
    missing = sorted(EXPECTED_AGENT_MODELS - set(model_ids))
    agent_profiles = manifest_agent_profiles(manifest or load_manifest())
    profile_missing = sorted(model_id for model_id in EXPECTED_AGENT_MODELS if model_id not in agent_profiles)
    non_local_profiles = sorted(
        model_id
        for model_id, profile in agent_profiles.items()
        if model_id in EXPECTED_AGENT_MODELS and (profile.get("provider") != "vulcan_ollama" or profile.get("keep_local") is not True)
    )
    generated_at = int(time.time())
    return {
        "report_type": "open-webui-model-proxy-catalog",
        "generated_at_unix": generated_at,
        "timestamp_unix": generated_at,
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "url": url,
        "http_status": status,
        "error_class": error,
        "model_count": len(model_ids),
        "agent_models_present": present,
        "agent_models_missing": missing,
        "agent_profile_map": {model_id: agent_profiles.get(model_id) for model_id in sorted(EXPECTED_AGENT_MODELS)},
        "agent_profiles_missing": profile_missing,
        "agent_profiles_non_local": non_local_profiles,
        "ok": status == 200 and not missing and not profile_missing and not non_local_profiles,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    probe = "http"
    model_ids, status, error = fetch_model_ids(args.url, args.timeout, args.open_webui_api_key)
    url = args.url
    if status == 401 and not args.no_container_probe:
        probe = "container"
        model_ids, status, error = fetch_model_ids_from_container(args.container, args.container_url, args.timeout)
        url = args.container_url
    report = build_report(model_ids, status=status, error=error, url=url, manifest=load_manifest(args.manifest))
    report["probe"] = probe
    if probe == "container":
        report["container"] = args.container
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
