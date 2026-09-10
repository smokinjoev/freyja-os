import asyncio
import json

from open_webui.models.tools import Tools
from open_webui.utils.plugin import load_tool_module_by_id
from open_webui.utils.tools import get_tool_specs


PLACEHOLDERS = {
    "freyja_home_memory": (
        "Freyja Home Memory",
        "Freyja Home Memory is not wired to a live adapter yet.",
        ["search", "remember", "update", "forget", "record_decision", "recent_events"],
    ),
    "iris_apple": (
        "Iris Apple Capabilities",
        "Iris Apple Capabilities are not wired to a live adapter yet.",
        [
            "calendar_read",
            "calendar_create",
            "reminders_read",
            "reminders_create",
            "imessage_send_approved",
            "shortcuts_run",
        ],
    ),
    "home_assistant": (
        "Home Assistant",
        "Home Assistant is not wired to a live adapter yet.",
        ["home_status", "home_device_action"],
    ),
    "household_analysis": (
        "Household Files And Analysis",
        "Household Files And Analysis is not wired to a live adapter yet.",
        ["files_household_read", "files_beth_read", "pdf_analyze", "image_analyze"],
    ),
    "infrastructure_health": (
        "Infrastructure Health",
        "Infrastructure Health is not wired to a live adapter yet. Use Atlas Status or Vulcan Status for host checks.",
        ["infrastructure_health"],
    ),
    "weather": (
        "Weather",
        "Weather is not wired to a live adapter yet.",
        ["weather_read"],
    ),
}


def build_content(title: str, message: str, methods: list[str]) -> str:
    lines = [f'"""Safe placeholder for {title}."""', "", "", "class Tools:"]
    for method in methods:
        lines.extend(
            [
                f"    def {method}(self) -> str:",
                f'        """Return configuration status for {title}."""',
                f"        return {message!r}",
                "",
            ]
        )
    return "\n".join(lines)


async def main() -> None:
    changed = []
    skipped = []
    for tool_id, (title, message, methods) in PLACEHOLDERS.items():
        tool = await Tools.get_tool_by_id(tool_id)
        if not tool:
            skipped.append((tool_id, "missing"))
            continue
        if "class Tools" in (tool.content or ""):
            skipped.append((tool_id, "already_has_tools_class"))
            continue

        content = build_content(title, message, methods)
        module, frontmatter = await load_tool_module_by_id(tool_id, content=content)
        specs = get_tool_specs(module)
        updated = await Tools.update_tool_by_id(
            tool_id,
            {
                "content": content,
                "specs": specs,
                "meta": {
                    "description": tool.meta.description if tool.meta else message,
                    "manifest": frontmatter,
                    "has_user_valves": False,
                },
                "valves": {},
            },
        )
        if updated is None:
            raise RuntimeError(f"failed to update {tool_id}")
        changed.append((tool_id, [spec["name"] for spec in specs]))

    print(json.dumps({"changed": changed, "skipped": skipped}, indent=2))


asyncio.run(main())
