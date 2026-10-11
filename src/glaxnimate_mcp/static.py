"""Base-artwork SVG export with responsive sizing and local ID rewriting."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from .sample import sample_frame
from .svg import AnimationError, _id_index, _parse_svg, _tag


def export_static(svg: str, responsive: bool = True, minify_ids: bool = False, animations: list[dict[str, object]] | None = None, time_ms: float = 0) -> dict[str, object]:
    """Export base artwork, or the frame at time_ms when animation channels are supplied."""
    if not isinstance(responsive, bool) or not isinstance(minify_ids, bool):
        raise AnimationError("responsive and minify_ids must be booleans")
    root = _parse_svg(svg)
    for parent in root.iter():
        for child in list(parent):
            if child.tag in {_tag(name) for name in ("animate", "animateTransform", "animateMotion", "set", "script")}:
                parent.remove(child)
    if any(node.tag == _tag("style") for node in root.iter()):
        raise AnimationError("static export requires SVG without stylesheets; CSS animation cannot be removed safely")
    if any("style" in node.attrib for node in root.iter()):
        raise AnimationError("static export requires SVG without inline style attributes")
    frame = "base artwork"
    if animations is not None:
        sample_frame(root, animations, time_ms)
        frame = f"{time_ms:g} ms"
    elements = _id_index(root)
    if responsive:
        if not root.get("viewBox"):
            width, height = root.get("width", ""), root.get("height", "")
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", width) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", height) or float(width) <= 0 or float(height) <= 0:
                raise AnimationError("responsive export needs a viewBox or positive numeric width and height")
            root.set("viewBox", f"0 0 {width} {height}")
        root.attrib.pop("width", None)
        root.attrib.pop("height", None)
    replacements = {name: f"s{index}" for index, name in enumerate(elements)} if minify_ids else {}
    for name, replacement in replacements.items():
        elements[name].set("id", replacement)
    for node in root.iter():
        for name, value in list(node.attrib.items()):
            if name in ("href", "{http://www.w3.org/1999/xlink}href") and value.startswith("#"):
                node.set(name, "#" + replacements.get(value[1:], value[1:]))
            elif name in ("aria-labelledby", "aria-describedby"):
                node.set(name, " ".join(replacements.get(token, token) for token in value.split()))
            elif name != "id":
                node.set(name, re.sub(r"url\(\s*(['\"]?)#([^\s)'\"]+)\1\s*\)", lambda match: "url(#" + replacements.get(match[2], match[2]) + ")", value))
    return {"svg": ET.tostring(root, encoding="unicode"), "format": "static SVG", "responsive": responsive, "id_map": replacements, "frame": frame, "output_written": False}
