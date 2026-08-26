"""Small read-only web search/fetch tools for agent live-data lookup."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

_DUCKDUCKGO_HTML_URL = "https://duckduckgo.com/html/"
_HTTP_TIMEOUT_SECONDS = 25.0
_MAX_QUERY_CHARS = 300
_MAX_FETCH_CHARS = 12000


async def web_search(query: str, *, max_results: int = 5) -> dict:
    cleaned = " ".join(str(query or "").split())[:_MAX_QUERY_CHARS]
    if not cleaned:
        return {"ok": False, "query": "", "results": [], "error": "query is required"}
    limit = max(1, min(int(max_results or 5), 10))
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(
                _DUCKDUCKGO_HTML_URL,
                params={"q": cleaned},
                headers={"User-Agent": "Freyja-OS/3.0 (+local-agent-web-search)"},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - tool result should be model-readable
        return {"ok": False, "query": cleaned, "results": [], "error": type(exc).__name__}

    results = _parse_duckduckgo_results(response.text)[:limit]
    return {"ok": True, "query": cleaned, "provider": "duckduckgo_html", "results": results, "count": len(results)}


async def web_fetch(url: str, *, max_chars: int = _MAX_FETCH_CHARS) -> dict:
    cleaned = str(url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "url": cleaned, "error": "url must be http or https"}
    limit = max(500, min(int(max_chars or _MAX_FETCH_CHARS), _MAX_FETCH_CHARS))
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(
                cleaned,
                headers={"User-Agent": "Freyja-OS/3.0 (+local-agent-web-fetch)"},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": cleaned, "error": type(exc).__name__}

    content_type = response.headers.get("content-type", "")
    text = _html_to_text(response.text) if "html" in content_type.lower() else response.text
    return {
        "ok": True,
        "url": str(response.url),
        "content_type": content_type,
        "text": text[:limit],
        "truncated": len(text) > limit,
    }


def _parse_duckduckgo_results(html: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        title = _html_to_text(match.group("title"))
        snippet = _html_to_text(match.group("snippet"))
        url = _clean_result_url(unescape(match.group("url")))
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    if results:
        return results

    fallback = re.compile(r'<a[^>]+href="(?P<url>https?://[^"]+)"[^>]*>(?P<title>.*?)</a>', re.IGNORECASE | re.DOTALL)
    for match in fallback.finditer(html):
        title = _html_to_text(match.group("title"))
        url = _clean_result_url(unescape(match.group("url")))
        if title and url and "duckduckgo.com" not in url:
            results.append({"title": title, "url": url, "snippet": ""})
    return results


def _clean_result_url(url: str) -> str:
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return target
    return url


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def search_url(query: str) -> str:
    return f"{_DUCKDUCKGO_HTML_URL}?q={quote_plus(query)}"
