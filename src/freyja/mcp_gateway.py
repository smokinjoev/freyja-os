from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class GatewayTool:
    name: str
    category: str
    description: str
    risk: str = "read"


TOOL_CATALOG = (
    GatewayTool("status.check", "system", "Check Freyja Core and downstream service health."),
    GatewayTool("calendar.resolve_date", "calendar", "Resolve natural-language dates deterministically."),
    GatewayTool("calendar.list_events", "calendar", "List calendar events in an authorized time window."),
    GatewayTool("calendar.create_event", "calendar", "Create an Apple Calendar event.", "write"),
    GatewayTool("calendar.delete_event", "calendar", "Delete an approved Freyja smoke event.", "destructive"),
    GatewayTool("home_assistant.read_state", "home", "Read one Home Assistant entity state."),
    GatewayTool("home_assistant.list_states", "home", "List read-only Home Assistant states."),
    GatewayTool("opencode.start", "coding", "Start the managed OpenCode session.", "write"),
    GatewayTool("opencode.stop", "coding", "Stop the managed OpenCode session.", "write"),
    GatewayTool("opencode.status", "coding", "Read managed OpenCode session status."),
    GatewayTool("opencode.send", "coding", "Send work to the managed OpenCode session.", "write"),
    GatewayTool("opencode.read", "coding", "Read recent managed OpenCode output."),
    GatewayTool("memory.search", "memory", "Search the caller's authorized local memory."),
    GatewayTool("memory.write", "memory", "Write an authorized local memory record.", "write"),
    GatewayTool("memory.delete", "memory", "Delete a caller-owned local memory record.", "destructive"),
)

AGENT_POLICIES: dict[str, tuple[str, ...]] = {
    "freyja": ("*",),
    "freyja-test": (
        "status.*",
        "calendar.resolve_date",
        "calendar.list_events",
        "calendar.create_event",
        "home_assistant.read_state",
        "home_assistant.list_states",
        "opencode.*",
        "memory.*",
    ),
    # Freyja 6.1 begins with a deliberately read-only parent surface. Later
    # activation stages expand this only after their Core and Discord evidence.
    "freyja61-parent": (
        "status.*",
        "calendar.resolve_date",
        "calendar.list_events",
        "memory.search",
    ),
    "freyja61-research": ("status.*", "memory.search"),
    "freyja61-household": (
        "status.*",
        "calendar.resolve_date",
        "calendar.list_events",
        "home_assistant.read_state",
        "home_assistant.list_states",
        "memory.search",
        "memory.write",
        "memory.delete",
    ),
    "freyja61-coding": ("status.*", "opencode.status", "opencode.read", "memory.search"),
    "cloyd-gibbler": ("status.*", "opencode.*", "memory.*"),
    "smith": ("status.*", "opencode.*", "memory.search"),
    "benedict": ("status.*", "calendar.resolve_date", "memory.*"),
    # Agent 47 is the technical executor. It may inspect the managed coding
    # session, but cannot start, stop, or send work without a later approval.
    "agent-47": ("status.*", "opencode.status", "opencode.read", "memory.*"),
    "jennacide": ("status.*", "memory.*"),
    "benedict-paralegal": ("status.*",),
    "generic": ("status.*", "memory.search"),
}

_CURRENT_AGENT: ContextVar[str] = ContextVar("freyja_mcp_agent", default="generic")


def set_current_agent(agent_id: str):
    return _CURRENT_AGENT.set(agent_id if agent_id in AGENT_POLICIES else "generic")


def reset_current_agent(token: Any) -> None:
    _CURRENT_AGENT.reset(token)


def current_agent() -> str:
    return _CURRENT_AGENT.get()


def is_allowed(agent_id: str, tool_name: str) -> bool:
    return any(fnmatch(tool_name, pattern) for pattern in AGENT_POLICIES.get(agent_id, AGENT_POLICIES["generic"]))


def discover_tools(query: str = "", category: str = "", limit: int = 20) -> dict[str, Any]:
    agent_id = current_agent()
    words = [word.lower() for word in query.split() if word.strip()]
    matches = []
    for tool in TOOL_CATALOG:
        if not is_allowed(agent_id, tool.name):
            continue
        if category and tool.category != category:
            continue
        haystack = f"{tool.name} {tool.category} {tool.description}".lower()
        if words and not all(word in haystack for word in words):
            continue
        matches.append(asdict(tool))
    bounded_limit = min(max(int(limit), 1), 50)
    return {
        "ok": True,
        "agent_id": agent_id,
        "query": query,
        "category": category,
        "tools": matches[:bounded_limit],
        "count": min(len(matches), bounded_limit),
    }


def profile() -> dict[str, Any]:
    agent_id = current_agent()
    visible = [tool.name for tool in TOOL_CATALOG if is_allowed(agent_id, tool.name)]
    return {"ok": True, "agent_id": agent_id, "tools": visible, "tool_count": len(visible)}


async def dispatch_tool(
    tool_name: str,
    arguments: dict[str, Any],
    caller: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    agent_id = current_agent()
    known = any(tool.name == tool_name for tool in TOOL_CATALOG)
    if not known:
        return {"ok": False, "error": f"Unknown gateway tool: {tool_name}"}
    if not is_allowed(agent_id, tool_name):
        return {
            "ok": False,
            "error": "Tool is not allowed for this agent.",
            "agent_id": agent_id,
            "tool": tool_name,
        }
    result = await caller(tool_name, arguments)
    return {**result, "gateway": {"agent_id": agent_id, "tool": tool_name}}
