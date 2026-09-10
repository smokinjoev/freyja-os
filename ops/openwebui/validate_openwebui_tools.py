import asyncio

from open_webui.models.tools import Tools
from open_webui.utils.plugin import load_tool_module_by_id


async def main() -> None:
    bad = []
    tools = await Tools.get_tools(defer_content=False, user_id=None)
    print("tool_count", len(tools))
    for tool in tools:
        try:
            await load_tool_module_by_id(tool.id, content=tool.content)
            print("OK", tool.id, tool.name)
        except Exception as exc:
            print("BAD", tool.id, tool.name, repr(exc))
            bad.append(tool.id)
    if bad:
        raise SystemExit(1)


asyncio.run(main())
