"""MCP entry point for Glaxnimate-compatible SVG animation tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mcp.server.fastmcp import FastMCP

from .authoring import ELEMENT_TYPES, create_svg, edit_svg
from .css import CSS_PROPERTIES, export_css
from .export import export_svg
from .filters import FILTER_TYPES, set_filters
from .lottie import LOTTIE_PROPERTIES, export_lottie
from .project import create_project, edit_project, inspect_project
from .text import text_to_path
from .geometry import BOOLEAN_OPERATIONS, combine_shapes
from .mobile import export_mobile
from .easing import PRESETS
from .static import export_static
from .path_edit import edit_path
from .render import render_media
from .render import MEDIA_TYPES
from .svg import ANIMATION_PROPERTIES, AnimationError, animate_svg, inspect_svg

mcp = FastMCP("Glaxnimate-compatible SVG animation", json_response=True)


@mcp.tool()
def glaxnimate_capabilities() -> dict[str, object]:
    """List supported animation properties, timeline options, and export formats.

    Check these capabilities before constructing animation requests.
    This server does not provide the full SVGator feature set.
    """
    return {
        "animation_properties": sorted(ANIMATION_PROPERTIES),
        "element_types": sorted(ELEMENT_TYPES),
        "edit_actions": ["insert", "update", "remove", "move", "duplicate", "resize"],
        "filter_types": list(FILTER_TYPES),
        "calc_modes": ["linear", "discrete", "spline"],
        "spline_coordinate_range": [0, 1],
        "keyframes_per_channel": 512,
        "easing_presets": list(PRESETS),
        "numeric_easing_types": ["preset", "cubic", "steps", "bounce-out", "elastic-out"],
        "continuous_easing_sampling": "piecewise linear approximation, 60 samples per interval by default, maximum 512 keyframes per channel",
        "repeat_count": "number from 1 to 1000, or indefinite",
        "fill_modes": ["freeze", "remove"],
        "transform_additive_modes": ["replace", "sum"],
        "export_formats": ["SMIL animated SVG", "JavaScript animated SVG", "CSS animated SVG", "Lottie JSON", "static SVG"],
        "lottie_properties": sorted(LOTTIE_PROPERTIES),
        "mobile_exports": ["react-native", "flutter"],
        "mobile_export_runtime": "platform Lottie library, same vector restrictions as Lottie export",
        "css_properties": sorted(CSS_PROPERTIES),
        "playback_triggers": ["load", "hover", "click", "scroll", "programmatic"],
        "optional_media_formats": list(MEDIA_TYPES),
        "media_requirements": "render extra, Chromium, and FFmpeg for animated formats",
        "svgator_parity": False,
        "project_version": 1,
        "project_actions": ["artwork", "settings", "add_track", "update_track", "remove_track", "duplicate_track", "set_keyframe", "remove_keyframe", "set_interval_easing"],
        "text_outlines": "fonts extra and supplied base64 TTF or OTF font, one horizontal text run",
        "boolean_operations": list(BOOLEAN_OPERATIONS),
        "path_edit_actions": ["set_point", "split_segment", "remove_command"],
        "path_edit_mirror_modes": ["symmetric", "aligned"],
        "path_edit_coordinate_system": "element-local, normalized absolute cubic commands",
        "lottie_paint": ["solid color", "linear gradient", "radial gradient"],
        "lottie_layers": "embedded images, clip-path, and luminance mask on direct children of the root svg",
        "static_frame_sampling": "SMIL timing, discrete, linear, and spline interpolation, additive transforms, and motion paths",
    }


@mcp.tool()
def glaxnimate_edit_path(svg: str, target_id: str, operations: list[dict[str, object]]) -> dict[str, object]:
    """Inspect and edit static path commands. An empty operations array inspects the path.

    set_point needs command_index, point_index, x, and y. Optional mirror accepts symmetric or aligned.
    mirror moves the opposite curve handle at the same node to keep the node smooth.
    split_segment needs command_index and t greater than 0 and less than 1. It splits a lineTo or curveTo.
    remove_command needs command_index. It removes a lineTo or curveTo and its end node.
    Operations run in order. Each index refers to the commands after earlier operations.
    Coordinates are element-local.
    Quadratic curves and arcs become cubic curves. Relative commands become absolute commands.
    Commands use moveTo, lineTo, curveTo, closePath, and endPath.
    The tool preserves IDs and transforms. SVG with stylesheets, scripts, or animations is unsupported.
    It returns SVG and commands. It does not save output.
    """
    try:
        return edit_path(svg, target_id, operations)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_static(
    svg: str, responsive: bool = True, minify_ids: bool = False,
    animations: list[dict[str, object]] | None = None, time_ms: float = 0,
) -> dict[str, object]:
    """Export static SVG. Supply animations to export the frame at time_ms.

    Without animations, the result is the base artwork.
    animations accepts glaxnimate_animate_svg specifications. time_ms accepts 0 to 3600000.
    Sampling follows SMIL timing: begin_ms, repeat_count, fill_mode, calc_mode, key_splines, and easing.
    Later begin times take priority. Equal begin times use array order.
    Transforms follow additive replace and sum. Motion paths precede the transform list.
    Interpolated colors become rgb() values. Other interpolated values need the same structure.
    It removes native animation elements and scripts. SVG with stylesheets or inline styles is unsupported.
    responsive removes width and height. It requires a viewBox or positive numeric dimensions.
    minify_ids creates short IDs and updates local href, URL, and accessibility references.
    The result includes svg, frame, and id_map. This tool is not an embedding sanitizer.
    This tool does not save output.
    """
    try:
        return export_static(svg, responsive, minify_ids, animations, time_ms)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_mobile(svg: str, animations: list[dict[str, object]], platform: str, component_name: str = "SvgAnimation", fps: float = 30, duration_ms: float = 1000) -> dict[str, object]:
    """Export React Native JavaScript or a Flutter Dart widget using a native Lottie player.

    platform accepts react-native or flutter. Supply a component_name that starts with an uppercase letter.
    The result includes source, filename, dependencies, and Lottie data.
    This tool uses the same SVG restrictions as glaxnimate_export_lottie.
    React Native callers can set LottieView props. Flutter callers can supply an animation controller.
    Components play and loop by default. The host application controls interactions and reduced motion.
    This tool does not install a mobile runtime, compile an application, or save files.
    """
    try:
        return export_mobile(svg, animations, platform, component_name, fps, duration_ms)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_combine_shapes(svg: str, target_ids: list[str], operation: str) -> dict[str, object]:
    """Combine static sibling SVG shapes. Install the geometry extra first.

    operation accepts union, subtract, intersect, or exclude.
    Subtract removes subsequent shapes from the first shape.
    All shapes must have the same parent. Static transforms are converted to path coordinates.
    The result retains the first shape's ID and paint. It removes subsequent shape IDs.
    Shapes with children, animations, or inline styles are unsupported.
    Update references to removed IDs in the returned SVG when necessary.
    This tool returns SVG. It does not save output.
    """
    try:
        return combine_shapes(svg, target_ids, operation)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_text_to_path(text: str, font_base64: str, font_size: float = 16, x: float = 0, y: float = 0, direction: str = "auto") -> dict[str, object]:
    """Convert text to SVG path data with a supplied font.

    Install the fonts extra. Supply base64 TTF or OTF data of at most 5 million bytes.
    The result contains d for a path element, advance, glyph_count, and shaping direction.
    x and y specify the baseline start. direction accepts auto, ltr, or rtl.
    This tool shapes one horizontal run. It does not perform paragraph layout or bidirectional run segmentation.
    It does not read font files, contact a font service, or save output.
    """
    try:
        return text_to_path(text, font_base64, font_size, x, y, direction)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_create_project(svg: str, duration_ms: float = 1000, fps: float = 30) -> dict[str, object]:
    """Create editable local project data with artwork and an empty timeline.

    The result contains project and JSON. Store the result in the client.
    This tool does not save files or create a hosted project.
    """
    try:
        return create_project(svg, duration_ms, fps)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_edit_project(project: dict[str, object], operations: list[dict[str, object]]) -> dict[str, object]:
    """Apply atomic artwork, timeline, or playback edits to project data.

    add_track needs id and animation. Use glaxnimate_animate_svg animation specifications.
    update_track needs id and an animation object containing changed fields.
    Update values, key_times, and key_splines together when changing keyframe counts.
    remove_track needs id. duplicate_track needs id, new_id, and optional target_id.
    set_keyframe needs id, time from 0 to 1, and value. It updates or inserts a track-local keyframe.
    remove_keyframe needs id and time. It removes an existing interior keyframe.
    Insertion and removal require linear or discrete tracks without global easing.
    For other tracks, use update_track with complete values, key_times, and easing.
    set_interval_easing needs id, index, and curve. It sets one interval to a cubic spline.
    Other intervals default to linear splines. Global easing must be absent.
    artwork needs operations accepted by glaxnimate_edit_svg.
    settings needs values containing duration_ms, fps, or playback.
    playback accepts glaxnimate_export_svg options. Store snapshots to implement undo and redo.
    Export project.svg with the animation objects in project.tracks through the export tools.
    This tool returns no modified project if any operation fails.
    """
    try:
        return edit_project(project, operations)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_inspect_project(project: dict[str, object]) -> dict[str, object]:
    """Validate saved project data. List artwork IDs, tracks, timing, and playback options."""
    try:
        return inspect_project(project)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_lottie(svg: str, animations: list[dict[str, object]], fps: float = 30, duration_ms: float = 1000) -> dict[str, object]:
    """Export vector Lottie JSON from SVG shapes and groups.

    Use rect, circle, ellipse, line, polyline, polygon, or path elements.
    Supply solid colors as #RGB, #RRGGBB, or basic color names.
    Check glaxnimate_capabilities for supported Lottie animation properties.
    Each channel requires repeat_count=1 and fill_mode=freeze.
    duration_ms must contain all channels. An empty animations array exports static artwork.
    Use viewBox=0 0 width height. Transforms require numeric coordinates without units.
    Rotation accepts an angle or angle,x,y pivot coordinates. Pivots may be animated.
    fill and stroke accept url(#id) references to linearGradient or radialGradient elements.
    Gradients need spreadMethod=pad and no gradientTransform. Gradient stops are static.
    objectBoundingBox radial gradients need square shape bounds. Focal points must lie inside the circle.
    Embedded base64 PNG, JPEG, GIF, or WebP images become image layers. Images need width and height.
    preserveAspectRatio accepts none or an alignment with meet.
    clip-path and mask become track mattes. Use them only on direct children of the root svg.
    clipPath needs clipPathUnits=userSpaceOnUse. mask needs maskUnits=userSpaceOnUse.
    A mask uses luminance. Its region must cover the viewport.
    A root svg that contains images, clip-path, or mask cannot have transform or opacity.
    Text, filters, patterns, markers, and use elements are unsupported.
    This tool returns JSON. It does not save output or add a playback runtime.
    """
    try:
        return export_lottie(svg, animations, fps, duration_ms)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_css(svg: str, animations: list[dict[str, object]], playback: dict[str, object]) -> dict[str, object]:
    """Export SVG with CSS keyframes and no JavaScript player.

    Supply animation and playback options accepted by glaxnimate_export_svg.
    CSS supports load and hover triggers. Hover supports freeze and reset only.
    Channels require begin_ms=0, fill_mode=freeze, and repeat_count=1.
    Check glaxnimate_capabilities for CSS properties. Filter primitives are unsupported.
    The result honors reduced-motion preferences. This tool does not save output.
    """
    try:
        return export_css(svg, animations, playback)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_set_filters(svg: str, target_id: str, effects: list[dict[str, object]]) -> dict[str, object]:
    """Apply an ordered filter chain. Return SVG and IDs for its filter primitives.

    Each effect needs type and value. Check glaxnimate_capabilities for filter types.
    blur value is {x,y}. Shadow value is {blur:{x,y},offset:{x,y},color:{r,g,b,a}}.
    Shadow RGB channels accept 0 to 255. Alpha accepts 0 to 1.
    Other values are numbers. grayscale, invert, opacity, and sepia accept 0 to 1.
    Animate returned primitive IDs with glaxnimate_animate_svg.
    Repeating this tool replaces the filter chain it created for this target.
    This tool does not save output. It replaces the target's filter attribute.
    """
    try:
        return set_filters(svg, target_id, effects)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_media(
    svg: str, animations: list[dict[str, object]], format: str,
    width: int = 512, height: int = 512, duration_ms: float = 1000,
    fps: int = 30, time_ms: float = 0, fit: str = "meet", quality: int = 80,
    playback: dict[str, object] | None = None,
) -> dict[str, object]:
    """Render local raster images, video, or a ZIP archive of PNG frames.

    Install the render extra and Chromium. Animated formats also require FFmpeg.
    GLAXNIMATE_CHROMIUM_PATH can select an existing Chromium executable.
    width and height accept 1 to 4096 pixels. fps accepts 1 to 60.
    duration_ms accepts 1 to 60000. time_ms selects the first frame.
    MP4, AVI, and MKV require even dimensions. The frame budget is 500 million pixels.
    fit accepts meet, slice, or stretch. quality accepts 1 to 100 for lossy codecs.
    The result contains base64 media bytes. No deliverable file remains on the server.
    SVG scripts and network requests are disabled during rendering.
    Optional playback uses export_svg timing options for direction, alternate, iterations, and speed.
    Rendering samples elapsed time. Playback triggers do not require browser interaction.
    """
    try:
        return render_media(svg, animations, format, width, height, duration_ms, fps, time_ms, fit, quality, playback)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_export_svg(
    svg: str, animations: list[dict[str, object]], playback: dict[str, object],
) -> dict[str, object]:
    """Export a standalone SVG with JavaScript playback and a programmatic player.

    Supply animation specifications accepted by glaxnimate_animate_svg.
    Each channel must use repeat_count=1. Use playback iterations=0 for infinite loops.
    Playback options: trigger, direction (1 or -1), alternate, iterations, speed,
    hover_out, click_again, scroll_threshold (1 to 100), and optional root_id.
    Triggers are load, hover, click, scroll, and programmatic.
    hover_out accepts freeze, reset, reverse, or none.
    click_again accepts freeze, restart, reverse, or none.
    Access the player through document.getElementById(root_id).glaxnimatePlayer.
    seek accepts milliseconds. The player honors reduced-motion preferences.
    Use a distinct root_id for each inline SVG instance. This tool does not save files.
    """
    try:
        return export_svg(svg, animations, playback)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_create_svg(width: float, height: float, elements: list[dict[str, object]]) -> dict[str, object]:
    """Create SVG artwork from structured elements. This tool does not save files.

    Each element needs type and id. Optional fields are attributes, text, and children.
    Use glaxnimate_capabilities to list element types. Attribute names follow SVG syntax.
    Give each element a unique ID. href accepts local references such as #symbol-name.
    Embedded images accept data:image/png, jpeg, gif, or webp with base64 data.
    """
    try:
        return create_svg(width, height, elements)
    except AnimationError as error:
        return {"error": str(error)}


@mcp.tool()
def glaxnimate_edit_svg(svg: str, operations: list[dict[str, object]]) -> dict[str, object]:
    """Apply ordered SVG edits. Return no modified SVG if any operation fails.

    Each operation needs action: insert, update, remove, move, duplicate, or resize.
    insert needs element and optional parent_id. Omit parent_id to use the document root.
    update needs target_id and attributes or text. remove needs target_id.
    move needs target_id, optional parent_id, and optional index within the destination.
    duplicate needs target_id and id_prefix. It duplicates the subtree after its source.
    resize needs width and height. It preserves the viewBox and changes the viewport.
    update accepts remove_attributes to remove attributes while preserving the ID.
    IDs remain stable on update. No operation writes files or accesses the network.
    """
    try:
        return edit_svg(svg, operations)
    except AnimationError as error:
        return {"error": str(error)}


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

    Each animation needs target_id, property, and values. Call glaxnimate_capabilities
    for supported properties. Use values such as ["0 0", "120 0"]
    for translate, ["0", "1"] for opacity, or compatible SVG path data for path.
    duration_ms, begin_ms, repeat_count, and key_times are optional.
    Use repeat_count="indefinite" for continuous loops.
    calc_mode accepts linear, discrete, or spline. For spline, supply key_splines.
    Supply one [x1, y1, x2, y2] curve per interval, with each coordinate between 0 and 1.
    Numeric channels can use easing instead of key_splines. easing requires calc_mode=linear.
    easing accepts type=preset with name, type=cubic with curve, or bounce-out and elastic-out.
    Continuous easing is sampled with optional samples=2 to 511. Cubic y coordinates permit overshoot.
    type=steps accepts steps=1 to 100 and jump=start, end, none, or both.
    Step easing uses exact discrete timing. jump=none requires at least 2 steps.
    fill_mode accepts freeze or remove. Transforms accept additive="replace" or "sum".
    For motion-path, supply motion_path as SVG path data and numeric values from 0 to 1.
    motion_rotate accepts auto, auto-reverse, or a rotation in degrees.

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
