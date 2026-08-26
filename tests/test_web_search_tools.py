from __future__ import annotations

import pytest

from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry
from freyja.tools.web_search import _clean_result_url, _parse_duckduckgo_results, web_fetch, web_search


def test_parse_duckduckgo_results() -> None:
    html = """
    <div class="result">
      <a rel="nofollow" class="result__a" href="https://example.com">Example &amp; Result</a>
      <a class="result__snippet">A useful &lt;b&gt;snippet&lt;/b&gt;.</a>
    </div>
    """

    assert _parse_duckduckgo_results(html) == [
        {
            "title": "Example & Result",
            "url": "https://example.com",
            "snippet": "A useful <b>snippet</b>.",
        }
    ]


def test_clean_result_url_unwraps_duckduckgo_redirect() -> None:
    url = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.openclaw.ai%2Ftools%2Fweb&rut=abc"

    assert _clean_result_url(url) == "https://docs.openclaw.ai/tools/web"


@pytest.mark.asyncio
async def test_web_search_returns_validation_error_for_empty_query() -> None:
    result = await web_search(" ")

    assert result["ok"] is False
    assert result["error"] == "query is required"


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_http_url() -> None:
    result = await web_fetch("file:///etc/passwd")

    assert result["ok"] is False
    assert result["error"] == "url must be http or https"


@pytest.mark.asyncio
async def test_builtin_registry_exposes_openclaw_style_web_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(query: str, *, max_results: int = 5) -> dict:
        return {"ok": True, "query": query, "results": [{"title": "One"}], "count": 1}

    monkeypatch.setattr("freyja.tools.builtin.web_search", fake_search)
    registry = ToolRegistry(audit_enabled=False)
    register_builtin_tools(registry)

    assert registry.get_tool("web_search") is not None
    assert registry.get_tool("web_fetch") is not None
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="web_search",
            arguments={"query": "openclaw tools", "max_results": 3},
            metadata={"director_authorized": True},
        )
    )

    assert result.success is True
    assert result.output["query"] == "openclaw tools"
