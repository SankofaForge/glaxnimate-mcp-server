"""MCP entry point for Glaxnimate-compatible SVG animation tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP

from .svg import AnimationError, animate_svg, inspect_svg

mcp = FastMCP("Glaxnimate-compatible SVG animation", json_response=True)


@mcp.tool()
def glaxnimate_inspect_svg(svg: str) -> dict[str, Any]:
    """Inspect an SVG and list the element IDs that can receive animation keyframes.

    Give generated artwork stable, semantic IDs such as character, arm-left, eye-right,
    or background before calling this tool. The result confirms which IDs are available.
    """
    try:
        return inspect_svg(svg)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_animate_svg(
    svg: str,
    animations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Add standards-based SMIL keyframes to a custom SVG.

    Each animation needs target_id, property, and values. Property is translate, rotate,
    scale, opacity, path, or stroke-dashoffset. Use values such as ["0 0", "120 0"]
    for translate, ["0", "1"] for opacity, or compatible SVG path data for path.
    duration_ms, begin_ms, repeat_count, and key_times are optional.

    The response contains animated_svg for the normal experience and the unchanged
    reduced_motion_svg for consumers that honor prefers-reduced-motion.
    """
    try:
        return animate_svg(svg, animations)
    except AnimationError as error:
        return {"error": str(error)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
