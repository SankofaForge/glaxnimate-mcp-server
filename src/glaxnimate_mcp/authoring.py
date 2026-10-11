"""Structured SVG authoring with atomic, in-memory edits."""

from __future__ import annotations

import re
import base64
import binascii
import math
from copy import deepcopy
from collections.abc import Mapping, Sequence
from xml.etree import ElementTree as ET

from .svg import AnimationError, _id_index, _number, _parse_svg, _tag

ELEMENT_TYPES = frozenset({
    "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "image",
    "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "use",
    "symbol", "mask", "clipPath", "pattern", "marker", "filter", "feGaussianBlur",
    "feOffset", "feFlood", "feComposite", "feBlend", "feColorMatrix",
    "feComponentTransfer", "feFuncR", "feFuncG", "feFuncB", "feFuncA",
    "feMerge", "feMergeNode", "feDropShadow", "title", "desc",
})
MAX_EDITS = 100
MAX_DEPTH = 32
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def _attributes(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise AnimationError("attributes must be an object")
    result: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or name.lower().startswith("on") or name in ("style", "xmlns"):
            raise AnimationError("attribute name is invalid or unsupported")
        if not isinstance(value, (str, int, float)) or isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)):
            raise AnimationError("attribute values must be strings or numbers")
        text = str(value)
        if name == "href" and not re.fullmatch(r"#[A-Za-z_][A-Za-z0-9_.-]*", text):
            match = re.fullmatch(r"data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)", text)
            if match is None or len(text) > 1_000_000:
                raise AnimationError("href must reference a local ID or an embedded raster image")
            try:
                data = base64.b64decode(match[2], validate=True)
            except binascii.Error as error:
                raise AnimationError("image data must contain valid base64") from error
            signatures = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff", "gif": b"GIF8", "webp": b"RIFF"}
            if not data.startswith(signatures[match[1]]) or (match[1] == "webp" and data[8:12] != b"WEBP"):
                raise AnimationError("embedded image bytes must match their MIME type")
        result[name] = text
    return result


def _element(raw: object, depth: int = 0) -> ET.Element:
    if depth > MAX_DEPTH:
        raise AnimationError("element nesting exceeds 32 levels")
    if not isinstance(raw, Mapping):
        raise AnimationError("each element must be an object")
    kind = raw.get("type")
    if not isinstance(kind, str) or kind not in ELEMENT_TYPES:
        raise AnimationError("element type is unsupported")
    attributes = _attributes(raw.get("attributes", {}))
    element_id = raw.get("id")
    if not isinstance(element_id, str) or not NAME.fullmatch(element_id):
        raise AnimationError("each element needs a valid id")
    if "id" in attributes:
        raise AnimationError("set the element id outside attributes")
    element = ET.Element(_tag(kind), {"id": element_id, **attributes})
    text = raw.get("text")
    if text is not None:
        if not isinstance(text, str) or kind not in ("text", "tspan", "title", "desc"):
            raise AnimationError("text is supported only on text, tspan, title, and desc elements")
        element.text = text
    children = raw.get("children", [])
    if not isinstance(children, list) or len(children) > MAX_EDITS:
        raise AnimationError("children must be an array of at most 100 elements")
    element.extend([_element(child, depth + 1) for child in children])
    return element


def _result(root: ET.Element) -> dict[str, object]:
    _id_index(root)
    svg = ET.tostring(root, encoding="unicode")
    _parse_svg(svg)
    return {"svg": svg, "output_written": False}


def create_svg(width: float, height: float, elements: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Create an SVG from a tree of element specifications."""
    width = _number(width, "width", 1, 100_000)
    height = _number(height, "height", 1, 100_000)
    root = ET.Element(_tag("svg"), {"width": f"{width:g}", "height": f"{height:g}", "viewBox": f"0 0 {width:g} {height:g}"})
    if not isinstance(elements, list) or len(elements) > MAX_EDITS:
        raise AnimationError("elements must be an array of at most 100 elements")
    root.extend([_element(element) for element in elements])
    return _result(root)


def edit_svg(svg: str, operations: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Apply ordered edits and return the SVG only when every edit succeeds."""
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_EDITS:
        raise AnimationError("operations must contain 1 to 100 objects")
    root = _parse_svg(svg)
    for operation in operations:
        if not isinstance(operation, Mapping):
            raise AnimationError("each operation must be an object")
        elements = _id_index(root)
        action = operation.get("action")
        if action == "resize":
            width = _number(operation.get("width"), "width", 1, 100_000)
            height = _number(operation.get("height"), "height", 1, 100_000)
            root.set("width", f"{width:g}")
            root.set("height", f"{height:g}")
            continue
        if action == "insert":
            parent_id = operation.get("parent_id")
            parent = root if parent_id is None else elements.get(str(parent_id))
            if parent is None:
                raise AnimationError("parent_id does not exist")
            parent.append(_element(operation.get("element")))
            continue
        target = elements.get(str(operation.get("target_id")))
        if target is None:
            raise AnimationError("target_id must identify an existing element")
        if action == "update":
            attributes = _attributes(operation.get("attributes", {}))
            if "id" in attributes:
                raise AnimationError("updates must preserve element IDs")
            target.attrib.update(attributes)
            removed = operation.get("remove_attributes", [])
            if not isinstance(removed, list) or any(not isinstance(name, str) or not NAME.fullmatch(name) or name == "id" for name in removed):
                raise AnimationError("remove_attributes must list attribute names other than id")
            for name in removed:
                target.attrib.pop(name, None)
            if "text" in operation:
                text = operation["text"]
                if not isinstance(text, str) or target.tag not in {_tag(kind) for kind in ("text", "tspan", "title", "desc")}:
                    raise AnimationError("text updates require a text element and a string")
                target.text = text
            continue
        if target is root:
            raise AnimationError("remove, move, and duplicate require a non-root element")
        parent = next(node for node in root.iter() if target in list(node))
        if action == "duplicate":
            prefix = operation.get("id_prefix")
            if not isinstance(prefix, str) or not NAME.fullmatch(prefix):
                raise AnimationError("duplicate needs a valid id_prefix")
            clone = deepcopy(target)
            ids = {node.get("id"): prefix + node.get("id") for node in clone.iter() if node.get("id")}
            for node in clone.iter():
                if node.get("id"):
                    node.set("id", ids[node.get("id")])
                for name, value in list(node.attrib.items()):
                    if name == "href" and value.startswith("#"):
                        node.set(name, "#" + ids.get(value[1:], value[1:]))
                    else:
                        node.set(name, re.sub(r"url\(#([^)]*)\)", lambda match: f"url(#{ids.get(match[1], match[1])})", value))
            parent.insert(list(parent).index(target) + 1, clone)
            continue
        if action == "remove":
            parent.remove(target)
            continue
        if action == "move":
            parent_id = operation.get("parent_id")
            destination = root if parent_id is None else elements.get(str(parent_id))
            if destination is None or destination in target.iter():
                raise AnimationError("move destination is missing or inside the target")
            index = operation.get("index", len(destination))
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= len(destination):
                raise AnimationError("index must be an integer within the destination children")
            parent.remove(target)
            destination.insert(index, target)
            continue
        raise AnimationError("action must be insert, update, remove, move, duplicate, or resize")
    return _result(root)
