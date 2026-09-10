import asyncio

from open_webui.models.tools import Tools
from open_webui.utils.plugin import load_tool_module_by_id


async def main() -> None:
    for tool_id, method in (
        ("atlas_status", "atlas_status"),
        ("vulcan_status", "vulcan_status"),
        ("vulcan_free_ram", "vulcan_free_ram"),
    ):
        tool = await Tools.get_tool_by_id(tool_id)
        module, _ = await load_tool_module_by_id(tool_id, content=tool.content)
        print("--", tool_id)
        print(getattr(module, method)())

    tool = await Tools.get_tool_by_id("vulcan_agent")
    module, _ = await load_tool_module_by_id("vulcan_agent", content=tool.content)
    for action in ("gpu_inventory", "gpu_memory", "freyja_os_git_status"):
        print("-- vulcan_agent", action)
        print(module.vulcan_agent(action))


asyncio.run(main())
