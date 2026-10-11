"""Safe, small helpers for standards-based SVG animation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 1_000_000
MAX_ANIMATIONS = 100
MAX_KEYFRAMES = 512
TRANSFORM_PROPERTIES = frozenset({"translate", "rotate", "scale", "skewX", "skewY"})
ANIMATION_PROPERTIES = TRANSFORM_PROPERTIES | frozenset({
    "opacity", "path", "stroke-dashoffset", "stroke-dasharray", "stroke-width",
    "fill", "fill-opacity", "stroke", "stroke-opacity", "stop-color", "stop-opacity",
    "x", "y", "cx", "cy", "r", "rx", "ry", "width", "height", "offset", "motion-path",
    "stdDeviation", "dx", "dy", "flood-color", "flood-opacity", "slope", "intercept",
    "tableValues", "values", "points", "x1", "x2", "y1", "y2", "fx", "fy",
})

ET.register_namespace("", SVG_NS)


class AnimationError(ValueError):
    """Raised when an SVG or animation specification is not safe or valid."""


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_svg(svg: str) -> ET.Element:
    if not isinstance(svg, str) or not svg.strip():
        raise AnimationError("svg must be a non-empty string")
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise AnimationError(f"svg exceeds the {MAX_SVG_BYTES:,}-byte limit")
    if "<!DOCTYPE" in svg.upper() or "<!ENTITY" in svg.upper():
        raise AnimationError("svg must not contain a DOCTYPE or entity declaration")

    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise AnimationError(f"invalid SVG XML: {error}") from error

    if _local_name(root.tag) != "svg":
        raise AnimationError("the document root must be an <svg> element")
    return root


def _id_index(root: ET.Element) -> dict[str, ET.Element]:
    elements: dict[str, ET.Element] = {}
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in elements:
            raise AnimationError(f"duplicate SVG id: {element_id}")
        elements[element_id] = element
    return elements


def inspect_svg(svg: str) -> dict[str, object]:
    """Return the IDs and basic structure that can be addressed by animation tools."""
    root = _parse_svg(svg)
    elements = _id_index(root)
    addressable = [
        {
            "id": element_id,
            "type": _local_name(element.tag),
            "children": len(list(element)),
        }
        for element_id, element in elements.items()
    ]
    return {
        "width": root.get("width"),
        "height": root.get("height"),
        "viewBox": root.get("viewBox"),
        "element_count": sum(1 for _ in root.iter()),
        "addressable_elements": addressable,
        "animation_targets": [item["id"] for item in addressable],
    }


def _number(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnimationError(f"{name} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise AnimationError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def _values(raw: object) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise AnimationError("values must be an array of at least two values")
    if not 2 <= len(raw) <= MAX_KEYFRAMES:
        raise AnimationError(f"values must contain 2 to {MAX_KEYFRAMES} keyframes")
    values = [str(value).strip() for value in raw]
    if any(not value or ";" in value or "<" in value or ">" in value for value in values):
        raise AnimationError("animation values must be non-empty plain values")
    return values


def _key_times(raw: object, count: int) -> str:
    if raw is None:
        if count == 2:
            return "0;1"
        return ";".join(f"{index / (count - 1):.6g}" for index in range(count))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != count:
        raise AnimationError("key_times must have one entry for each value")
    key_times = [_number(value, "key_times entry", 0, 1) for value in raw]
    if key_times[0] != 0 or key_times[-1] != 1:
        raise AnimationError("key_times must start at 0 and end at 1")
    if any(next_time <= current for current, next_time in zip(key_times, key_times[1:])):
        raise AnimationError("key_times must be strictly increasing")
    return ";".join(f"{value:.6g}" for value in key_times)


def _animation_element(spec: Mapping[str, object]) -> tuple[str, ET.Element]:
    if "easing" in spec:
        from .easing import bake_animation
        spec = bake_animation(spec)
    target_id = spec.get("target_id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise AnimationError("target_id must be a non-empty string")

    property_name = spec.get("property")
    if not isinstance(property_name, str) or property_name not in ANIMATION_PROPERTIES:
        valid = ", ".join(sorted(ANIMATION_PROPERTIES))
        raise AnimationError(f"property must be one of: {valid}")

    values = _values(spec.get("values"))
    duration_ms = _number(spec.get("duration_ms", 1000), "duration_ms", 1, 600_000)
    begin_ms = _number(spec.get("begin_ms", 0), "begin_ms", 0, 600_000)
    repeat = spec.get("repeat_count", 1)
    repeat_count = "indefinite" if repeat == "indefinite" else f'{_number(repeat, "repeat_count", 1, 1000):g}'
    key_times = _key_times(spec.get("key_times"), len(values))
    calc_mode = spec.get("calc_mode", "linear")
    if calc_mode not in ("linear", "discrete", "spline"):
        raise AnimationError("calc_mode must be linear, discrete, or spline")
    fill_mode = spec.get("fill_mode", "freeze")
    if fill_mode not in ("freeze", "remove"):
        raise AnimationError("fill_mode must be freeze or remove")

    attributes = {
        "values": ";".join(values),
        "keyTimes": key_times,
        "dur": f"{duration_ms:g}ms",
        "begin": f"{begin_ms:g}ms",
        "repeatCount": repeat_count,
        "fill": fill_mode,
        "calcMode": calc_mode,
    }
    if calc_mode == "spline":
        splines = spec.get("key_splines")
        if not isinstance(splines, (list, tuple)) or len(splines) != len(values) - 1:
            raise AnimationError("key_splines must contain one curve per keyframe interval")
        curves: list[str] = []
        for curve in splines:
            if not isinstance(curve, (list, tuple)) or len(curve) != 4:
                raise AnimationError("each key_splines curve must contain four numbers")
            curves.append(" ".join(f'{_number(value, "key_splines coordinate", 0, 1):g}' for value in curve))
        attributes["keySplines"] = ";".join(curves)
    elif "key_splines" in spec:
        raise AnimationError("key_splines requires calc_mode spline")

    if property_name == "motion-path":
        motion_path = spec.get("motion_path")
        if not isinstance(motion_path, str) or not motion_path.strip():
            raise AnimationError("motion_path must contain SVG path data")
        rotation = spec.get("motion_rotate", "auto")
        if rotation not in ("auto", "auto-reverse"):
            rotation = f'{_number(rotation, "motion_rotate", -360_000, 360_000):g}'
        points = [_number(value, "motion-path value", 0, 1) for value in spec["values"]]
        del attributes["values"]
        attributes.update({
            "path": motion_path, "rotate": rotation,
            "keyPoints": ";".join(f"{point:g}" for point in points),
        })
        return target_id, ET.Element(_tag("animateMotion"), attributes)

    if property_name in TRANSFORM_PROPERTIES:
        additive = spec.get("additive", "replace")
        if additive not in ("replace", "sum"):
            raise AnimationError("additive must be replace or sum")
        attributes["additive"] = additive
        attributes.update({"attributeName": "transform", "type": property_name})
        return target_id, ET.Element(_tag("animateTransform"), attributes)

    attribute_name = "d" if property_name == "path" else property_name
    attributes["attributeName"] = attribute_name
    return target_id, ET.Element(_tag("animate"), attributes)


def animate_svg(svg: str, animations: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Add SMIL keyframe animations to elements addressed by their SVG IDs."""
    if not isinstance(animations, Sequence) or isinstance(animations, (str, bytes)):
        raise AnimationError("animations must be an array")
    if not 1 <= len(animations) <= MAX_ANIMATIONS:
        raise AnimationError(f"animations must contain 1 to {MAX_ANIMATIONS} entries")

    root = _parse_svg(svg)
    elements = _id_index(root)
    target_ids: list[str] = []
    for raw_spec in animations:
        if not isinstance(raw_spec, Mapping):
            raise AnimationError("each animation must be an object")
        target_id, animation = _animation_element(raw_spec)
        target = elements.get(target_id)
        if target is None:
            raise AnimationError(f"animation target does not exist: {target_id}")
        target.append(animation)
        target_ids.append(target_id)

    animated_svg = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return {
        "animated_svg": animated_svg,
        "reduced_motion_svg": svg,
        "animation_count": len(animations),
        "targets": target_ids,
        "format": "SMIL animated SVG",
    }
