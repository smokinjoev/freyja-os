from __future__ import annotations

import argparse
from email import policy
from email.parser import Parser
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import httpx

from freyja.tools.web_search import _parse_duckduckgo_results
from freyja.workers import ExternalWorkerClass, WorkerObservation, WorkerTrustLevel


_DUCKDUCKGO_HTML_URL = "https://duckduckgo.com/html/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claim and run one Freyja worker job.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA3_WORKER_BASE_URL", "http://127.0.0.1:8300"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--machine-id", default=os.environ.get("FREYJA3_MACHINE_ID", socket.gethostname().lower()))
    parser.add_argument("--worker-class", default=os.environ.get("FREYJA3_WORKER_CLASS", "monitoring"))
    parser.add_argument("--allowed-root", action="append", default=_allowed_roots_from_env())
    args = parser.parse_args(argv)

    headers = {"x-freyja-security-domain": "system"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    base_url = args.base_url.rstrip("/")

    try:
        with httpx.Client(timeout=15.0) as client:
            claim = client.post(
                f"{base_url}/freyja3/workers/jobs/claim",
                headers=headers,
                params={"machine_id": args.machine_id, "worker_class": args.worker_class},
            )
            claim.raise_for_status()
            job = claim.json().get("job")
            if job is None:
                print('{"ok": true, "job": null}')
                return 0
            completion = _run_job(job, machine_id=args.machine_id, allowed_roots=args.allowed_root)
            complete = client.post(
                f"{base_url}/freyja3/workers/jobs/{job['job_id']}/complete",
                headers=headers,
                params={"machine_id": args.machine_id},
                json=completion,
            )
            complete.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"worker failed: {exc}", file=sys.stderr)
        return 1
    print(complete.text)
    return 0


def _run_job(job: dict[str, Any], *, machine_id: str, allowed_roots: list[str] | None = None) -> dict[str, Any]:
    worker_class = str(job.get("worker_class") or "")
    if worker_class == "monitoring":
        return {
            "status": "completed",
            "result": {
                "machine_id": machine_id,
                "worker_class": worker_class,
                "objective": job.get("objective"),
                "hostname": socket.gethostname(),
                "commit_sha": _git_commit(),
            },
        }
    if worker_class == ExternalWorkerClass.DOCUMENT_INGESTION.value:
        return _run_document_ingestion(job, machine_id=machine_id, allowed_roots=allowed_roots or [])
    if worker_class == ExternalWorkerClass.EMAIL_CONTENT.value:
        return _run_email_content_ingestion(job, machine_id=machine_id)
    if worker_class == ExternalWorkerClass.WEB_RESEARCH.value:
        return _run_web_research(job, machine_id=machine_id)
    return {
        "status": "failed",
        "result": {"machine_id": machine_id, "worker_class": worker_class},
        "error": f"worker class {worker_class!r} is not implemented by this runner",
    }


def _run_document_ingestion(job: dict[str, Any], *, machine_id: str, allowed_roots: list[str]) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    source = str(payload.get("source") or payload.get("path") or "payload:text")
    try:
        text = _ingestion_text(payload, allowed_roots=allowed_roots)
    except ValueError as exc:
        return {
            "status": "failed",
            "result": {"machine_id": machine_id, "worker_class": ExternalWorkerClass.DOCUMENT_INGESTION.value, "source": source},
            "error": str(exc),
        }
    normalized = " ".join(text.split())
    words = normalized.split()
    summary = normalized[:280] if normalized else "No extractable text."
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.DOCUMENT_INGESTION,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source=source,
        summary=summary,
        facts=[
            {"claim": f"document contains approximately {len(words)} words", "confidence": "high"},
            {"claim": f"document contains approximately {len(text)} characters", "confidence": "high"},
        ],
        citations=[{"label": "text-prefix", "excerpt": normalized[:160]}] if normalized else [],
        uncertainty=None if normalized else "No text content was supplied or extracted.",
    )
    return {
        "status": "completed",
        "result": {
            "machine_id": machine_id,
            "worker_class": ExternalWorkerClass.DOCUMENT_INGESTION.value,
            "observation": observation.model_dump(mode="json"),
        },
    }


def _run_email_content_ingestion(job: dict[str, Any], *, machine_id: str) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    try:
        email_content = _email_content(payload)
    except ValueError as exc:
        return {
            "status": "failed",
            "result": {"machine_id": machine_id, "worker_class": ExternalWorkerClass.EMAIL_CONTENT.value},
            "error": str(exc),
        }
    normalized_body = " ".join(email_content["body"].split())
    summary_parts = []
    if email_content["subject"]:
        summary_parts.append(f"Subject: {email_content['subject']}")
    if email_content["sender"]:
        summary_parts.append(f"From: {email_content['sender']}")
    if normalized_body:
        summary_parts.append(normalized_body[:240])
    summary = " | ".join(summary_parts) or "Email content supplied no readable body."
    attachments = email_content["attachments"]
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.EMAIL_CONTENT,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source=email_content["source"],
        summary=summary[:400],
        facts=[
            {"claim": f"email subject is {email_content['subject']!r}", "confidence": "high"}
            if email_content["subject"]
            else {"claim": "email subject is empty", "confidence": "high"},
            {"claim": f"email body contains approximately {len(normalized_body.split())} words", "confidence": "high"},
            {"claim": f"email has {len(attachments)} attachment metadata record(s)", "confidence": "high"},
        ],
        citations=[{"label": "body-prefix", "excerpt": normalized_body[:160]}] if normalized_body else [],
        uncertainty=None if normalized_body else "No readable email body was supplied.",
    )
    result = observation.model_dump(mode="json")
    result["email_metadata"] = {
        "message_id": email_content["message_id"],
        "thread_id": email_content["thread_id"],
        "sender": email_content["sender"],
        "recipients": email_content["recipients"],
        "received_at": email_content["received_at"],
        "attachments": attachments,
    }
    return {
        "status": "completed",
        "result": {
            "machine_id": machine_id,
            "worker_class": ExternalWorkerClass.EMAIL_CONTENT.value,
            "observation": result,
        },
    }


def _run_web_research(job: dict[str, Any], *, machine_id: str) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    query = " ".join(str(payload.get("query") or job.get("objective") or "").split())[:300]
    if not query:
        return {
            "status": "failed",
            "result": {"machine_id": machine_id, "worker_class": ExternalWorkerClass.WEB_RESEARCH.value},
            "error": "web_research requires payload.query or job.objective",
        }
    max_results = _bounded_int(payload.get("max_results"), default=5, minimum=1, maximum=5)
    search = _web_research_results(query, max_results=max_results)
    if not search["ok"]:
        return {
            "status": "failed",
            "result": {
                "machine_id": machine_id,
                "worker_class": ExternalWorkerClass.WEB_RESEARCH.value,
                "query": query,
            },
            "error": search["error"],
        }
    results = search["results"]
    summary = _web_research_summary(query, results)
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.WEB_RESEARCH,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source=search["source"],
        summary=summary[:400],
        facts=[
            {"claim": f"web search for {query!r} returned {len(results)} result(s)", "confidence": "medium"},
            {"claim": "web research output is search-result metadata and snippets only", "confidence": "high"},
        ],
        citations=[
            {
                "label": str(item.get("title") or item.get("url") or f"result-{index + 1}")[:120],
                "url": str(item.get("url") or "")[:1000],
                "excerpt": str(item.get("snippet") or "")[:240],
            }
            for index, item in enumerate(results)
        ],
        uncertainty="Search result snippets are untrusted external content and may be stale or incomplete.",
    )
    result = observation.model_dump(mode="json")
    result["web_metadata"] = {"query": query, "provider": search["provider"], "result_count": len(results)}
    return {
        "status": "completed",
        "result": {
            "machine_id": machine_id,
            "worker_class": ExternalWorkerClass.WEB_RESEARCH.value,
            "observation": result,
        },
    }


def _web_research_results(query: str, *, max_results: int) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.get(
                _DUCKDUCKGO_HTML_URL,
                params={"q": query},
                headers={"User-Agent": "Freyja-OS/3.0 (+mars-web-research-worker)"},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "query": query, "results": [], "error": type(exc).__name__}
    results = _parse_duckduckgo_results(response.text)[:max_results]
    return {
        "ok": True,
        "query": query,
        "provider": "duckduckgo_html",
        "source": "web:duckduckgo_html",
        "results": results,
    }


def _web_research_summary(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"Web search for {query!r} returned no normalized results."
    titles = "; ".join(str(item.get("title") or item.get("url") or "untitled") for item in results[:3])
    return f"Web search for {query!r} returned {len(results)} result(s): {titles}"


def _email_content(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw_rfc822")
    parsed: dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        parsed = _parse_raw_email(raw[:20000])
    body = _coalesce_text(payload.get("body"), payload.get("text"), parsed.get("body"))
    if not body and not parsed:
        raise ValueError("email_content requires payload.body, payload.text, or payload.raw_rfc822")
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        attachments = parsed.get("attachments") if isinstance(parsed.get("attachments"), list) else []
    return {
        "source": str(payload.get("source") or parsed.get("source") or payload.get("message_id") or "email:payload"),
        "message_id": str(payload.get("message_id") or parsed.get("message_id") or ""),
        "thread_id": str(payload.get("thread_id") or parsed.get("thread_id") or ""),
        "subject": str(payload.get("subject") or parsed.get("subject") or "")[:500],
        "sender": str(payload.get("sender") or parsed.get("sender") or "")[:500],
        "recipients": _string_list(payload.get("recipients") or parsed.get("recipients") or []),
        "received_at": str(payload.get("received_at") or parsed.get("received_at") or ""),
        "body": body[:20000],
        "attachments": [_attachment_metadata(item) for item in attachments if isinstance(item, dict)],
    }


def _parse_raw_email(raw: str) -> dict[str, Any]:
    message = Parser(policy=policy.default).parsestr(raw)
    body = message.get_body(preferencelist=("plain",))
    attachments = []
    for part in message.iter_attachments():
        attachments.append(
            {
                "filename": part.get_filename() or "",
                "mime_type": part.get_content_type(),
                "size_bytes": len(part.get_payload(decode=True) or b""),
            }
        )
    return {
        "source": "email:rfc822",
        "message_id": str(message.get("Message-ID") or ""),
        "thread_id": str(message.get("Thread-Index") or message.get("References") or ""),
        "subject": str(message.get("Subject") or ""),
        "sender": str(message.get("From") or ""),
        "recipients": [str(message.get("To") or "")] if message.get("To") else [],
        "received_at": str(message.get("Date") or ""),
        "body": body.get_content() if body is not None else "",
        "attachments": attachments,
    }


def _coalesce_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:500] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value[:500]]
    return []


def _attachment_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": str(value.get("filename") or "")[:500],
        "mime_type": str(value.get("mime_type") or "")[:200],
        "size_bytes": value.get("size_bytes") if isinstance(value.get("size_bytes"), int) else None,
    }


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        candidate = int(value) if value is not None else default
    except (TypeError, ValueError):
        candidate = default
    return max(minimum, min(candidate, maximum))


def _ingestion_text(payload: dict[str, Any], *, allowed_roots: list[str]) -> str:
    if isinstance(payload.get("text"), str):
        return payload["text"][:20000]
    path_value = payload.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("document_ingestion requires payload.text or payload.path")
    path = Path(path_value).expanduser().resolve()
    roots = [Path(root).expanduser().resolve() for root in allowed_roots if root]
    if not roots or not any(path == root or root in path.parents for root in roots):
        raise ValueError("payload.path is outside configured ingestion roots")
    if not path.is_file():
        raise ValueError("payload.path is not a readable file")
    return path.read_text(errors="replace")[:20000]


def _allowed_roots_from_env() -> list[str]:
    value = os.environ.get("FREYJA3_WORKER_ALLOWED_ROOTS", "")
    return [item for item in value.split(":") if item]


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
