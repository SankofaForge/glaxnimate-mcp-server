"""CSS animation export for SVG presentation and transform properties."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from xml.etree import ElementTree as ET

from .export import _prepare_export
from .svg import TRANSFORM_PROPERTIES, AnimationError, _animation_element, _id_index, _number, _tag

LENGTH_PROPERTIES = frozenset({"x", "y", "cx", "cy", "r", "rx", "ry", "width", "height", "stroke-width", "stroke-dashoffset"})
CSS_PROPERTIES = TRANSFORM_PROPERTIES | LENGTH_PROPERTIES | frozenset({"fill", "stroke", "opacity", "fill-opacity", "stroke-opacity", "stop-color", "stop-opacity", "path"})


def _value(property: str, value: str) -> str:
    if any(token in value for token in ("{", "}", "@", "\\", "/*", "*/")):
        raise AnimationError("CSS values must not contain stylesheet syntax")
    if property in TRANSFORM_PROPERTIES:
        try:
            numbers = [float(part) for part in value.replace(",", " ").split()]
        except ValueError as error:
            raise AnimationError("CSS transform values must contain numbers") from error
        numbers = [_number(number, "transform coordinate", -1e9, 1e9) for number in numbers]
        sizes = {"translate": (1, 2), "scale": (1, 2), "rotate": (1, 3), "skewX": (1,), "skewY": (1,)}
        if len(numbers) not in sizes[property]:
            raise AnimationError("CSS transform value has an invalid number of coordinates")
        if property == "translate":
            return "translate(" + ",".join(f"{number:g}px" for number in numbers) + ")"
        if property == "scale":
            return "scale(" + ",".join(f"{number:g}" for number in numbers) + ")"
        angle = f"{property}({numbers[0]:g}deg)"
        if len(numbers) == 3:
            return f"translate({numbers[1]:g}px,{numbers[2]:g}px) {angle} translate({-numbers[1]:g}px,{-numbers[2]:g}px)"
        return angle
    if property == "path":
        return "path(" + json.dumps(value) + ")"
    if property in LENGTH_PROPERTIES:
        try:
            number = float(value)
        except ValueError:
            return value
        return f'{_number(number, "CSS length", -1e9, 1e9):g}px'
    return value


def export_css(svg: str, animations: Sequence[Mapping[str, object]], playback: Mapping[str, object]) -> dict[str, object]:
    """Export CSS keyframes. Reject channels and triggers CSS cannot represent here."""
    root, result, options = _prepare_export(svg, animations, playback)
    if options["trigger"] not in ("load", "hover") or (options["trigger"] == "hover" and options["hover_out"] not in ("freeze", "reset")):
        raise AnimationError("CSS export supports load or hover with freeze or reset")
    if any(spec.get("begin_ms", 0) != 0 for spec in animations):
        raise AnimationError("CSS export currently requires begin_ms=0")
    if any(spec.get("fill_mode", "freeze") != "freeze" for spec in animations):
        raise AnimationError("CSS export currently requires fill_mode=freeze")
    elements = _id_index(root)
    for parent in root.iter():
        for child in list(parent):
            if child.tag in {_tag(name) for name in ("animate", "animateTransform", "animateMotion")}:
                parent.remove(child)
    prefix = "glax-css-" + hashlib.sha256((svg + json.dumps(list(animations), sort_keys=True) + json.dumps(dict(playback), sort_keys=True)).encode()).hexdigest()[:12]
    root.set("data-glax-css", prefix)
    rules: list[str] = []
    tracks: dict[str, list[tuple[str, str]]] = {}
    duration = float(options["duration_ms"])
    direction = ("alternate" if options["alternate"] else "normal") if options["direction"] == 1 else ("alternate-reverse" if options["alternate"] else "reverse")
    iterations = "infinite" if options["iterations"] == 0 else str(options["iterations"])
    for index, spec in enumerate(animations):
        property = spec["property"]
        if property not in CSS_PROPERTIES:
            raise AnimationError("property is unsupported by CSS export")
        target_id, animation = _animation_element(spec)
        values = animation.get("values").split(";")
        times = [float(time) * float(spec.get("duration_ms", 1000)) / duration for time in animation.get("keyTimes").split(";")]
        css_property = "transform" if property in TRANSFORM_PROPERTIES else ("d" if property == "path" else property)
        name = f"{prefix}-{index}"
        frames: list[str] = []
        for key, (time, value) in enumerate(zip(times, values)):
            timing = "steps(1,end)" if animation.get("calcMode") == "discrete" else "linear"
            if animation.get("calcMode") == "spline" and key < len(values) - 1:
                timing = "cubic-bezier(" + ",".join(animation.get("keySplines").split(";")[key].split()) + ")"
            frames.append(f"{time * 100:.10g}%{{{css_property}:{_value(property, value)};animation-timing-function:{timing}}}")
        if times[-1] < 1:
            frames.append(f"100%{{{css_property}:{_value(property, values[-1])}}}")
        rules.append(f"@keyframes {name}{{{''.join(frames)}}}")
        tracks.setdefault(target_id, []).append((f"{name} {duration / float(options['speed']):g}ms linear 0ms {iterations} {direction} forwards", "add" if property in TRANSFORM_PROPERTIES and spec.get("additive") == "sum" else "replace"))
    for index, (target_id, items) in enumerate(tracks.items()):
        token = f"{prefix}-target-{index}"
        elements[target_id].set("data-glax-track", token)
        separator = "" if elements[target_id] is root else " "
        selector = f'[data-glax-css="{prefix}"]{separator}[data-glax-track="{token}"]'
        mode = "paused" if options["trigger"] == "hover" else "running"
        rules.append(f"{selector}{{transform-origin:0 0;transform-box:view-box;animation:{','.join(item[0] for item in items)};animation-composition:{','.join(item[1] for item in items)};animation-play-state:{mode}}}")
        if options["trigger"] == "hover":
            rules.append(f'[data-glax-css="{prefix}"]:hover{separator}[data-glax-track="{token}"]{{animation-play-state:running}}')
            if options["hover_out"] == "reset":
                rules.append(f'[data-glax-css="{prefix}"]:not(:hover){separator}[data-glax-track="{token}"]{{animation-name:none}}')
        rules.append(f"@media(prefers-reduced-motion:reduce){{{selector}{{animation:none}}}}")
    ET.SubElement(root, _tag("style")).text = "\n".join(rules)
    result.update({"animated_svg": ET.tostring(root, encoding="unicode"), "format": "CSS animated SVG", "output_written": False})
    return result
