"""Check discovery and calls through a real MCP stdio process."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "glaxnimate_mcp.server"], env={"PYTHONPATH": os.environ.get("PYTHONPATH", "")})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            inventory = await session.list_tools()
            names = {tool.name for tool in inventory.tools}
            expected = {
                "glaxnimate_capabilities", "glaxnimate_create_svg", "glaxnimate_edit_svg",
                "glaxnimate_inspect_svg", "glaxnimate_animate_svg", "glaxnimate_set_filters",
                "glaxnimate_export_svg", "glaxnimate_export_css", "glaxnimate_export_media",
                "glaxnimate_export_lottie", "glaxnimate_export_mobile", "glaxnimate_combine_shapes",
                "glaxnimate_text_to_path", "glaxnimate_create_project", "glaxnimate_edit_project",
                "glaxnimate_inspect_project",
                "glaxnimate_export_static",
                "glaxnimate_edit_path",
            }
            assert names == expected, names

            async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                data = result.structuredContent or json.loads(result.content[0].text)
                assert "error" not in data, data
                return data

            capabilities = await call("glaxnimate_capabilities", {})
            assert capabilities["svgator_parity"] is False
            artwork = await call("glaxnimate_create_svg", {"width": 100, "height": 100, "elements": [{"type": "rect", "id": "box", "attributes": {"width": 20, "height": 20}}]})
            created = await call("glaxnimate_create_project", {"svg": artwork["svg"]})
            animation = {"target_id": "box", "property": "translate", "values": ["0 0", "50 0"]}
            edited = await call("glaxnimate_edit_project", {"project": created["project"], "operations": [{"action": "add_track", "id": "move", "animation": animation}]})
            inspected = await call("glaxnimate_inspect_project", {"project": edited["project"]})
            assert inspected["tracks"][0]["id"] == "move"
            for tool in ("glaxnimate_export_svg", "glaxnimate_export_css"):
                exported = await call(tool, {"svg": artwork["svg"], "animations": [animation], "playback": {}})
                assert exported["animated_svg"] and not exported["output_written"]
            vector = await call("glaxnimate_export_lottie", {"svg": artwork["svg"], "animations": [animation]})
            assert vector["lottie"]["layers"]
            frame = await call("glaxnimate_export_static", {"svg": artwork["svg"], "animations": [animation], "time_ms": 500})
            assert 'transform="translate(25 0)"' in frame["svg"], frame
            path = await call("glaxnimate_edit_path", {"svg": '<svg xmlns="http://www.w3.org/2000/svg"><path id="p" d="M0 0L10 0"/></svg>', "target_id": "p", "operations": [{"action": "split_segment", "command_index": 1, "t": 0.5}]})
            assert path["commands"][1]["points"] == [[5, 0]], path
            invalid = await session.call_tool("glaxnimate_create_svg", {"width": 0, "height": 100, "elements": []})
            data = invalid.structuredContent or json.loads(invalid.content[0].text)
            assert "error" in data, data
    print("MCP stdio discovery and artwork/project/export/frame/path calls passed for 18 tools")


if __name__ == "__main__":
    asyncio.run(main())
