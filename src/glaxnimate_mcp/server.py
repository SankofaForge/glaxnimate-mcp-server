"""MCP entry point for Glaxnimate-compatible SVG animation tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mcp.server.fastmcp import FastMCP

from .svg import AnimationError, animate_svg, inspect_svg

mcp = FastMCP("Glaxnimate-compatible SVG animation", json_response=True)


@mcp.tool()
def glaxnimate_inspect_svg(svg: str, dry_run: bool = False) -> dict[str, object]:
    """Inspect an SVG and list the element IDs that can receive animation keyframes.

    Give generated artwork stable, semantic IDs such as character, arm-left, eye-right,
    or background before calling this tool. The result confirms which IDs are available.
    Set dry_run=true to mark the result as a preview. This tool does not save output.
    """
    try:
        result = inspect_svg(svg)
        if dry_run:
            result.update({"dry_run": True, "output_written": False})
        return result
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_animate_svg(
    svg: str,
    animations: Sequence[Mapping[str, object]],
    dry_run: bool = False,
) -> dict[str, object]:
    """Add standards-based SMIL keyframes to a custom SVG.

    Each animation needs target_id, property, and values. Property is translate, rotate,
    scale, opacity, path, or stroke-dashoffset. Use values such as ["0 0", "120 0"]
    for translate, ["0", "1"] for opacity, or compatible SVG path data for path.
    duration_ms, begin_ms, repeat_count, and key_times are optional.

    The response contains animated_svg for the normal experience and the unchanged
    reduced_motion_svg for consumers that honor prefers-reduced-motion. Set
    dry_run=true to mark the animation as a preview. This tool does not save output.
    """
    try:
        result = animate_svg(svg, animations)
        if dry_run:
            result.update({"dry_run": True, "output_written": False})
        return result
    except AnimationError as error:
        return {"error": str(error)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
