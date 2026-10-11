"""Compile ordered filter effects into editable SVG primitives."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from xml.etree import ElementTree as ET

from .authoring import _result
from .svg import AnimationError, _id_index, _number, _parse_svg, _tag

FILTER_TYPES = ("blur", "brightness", "contrast", "grayscale", "hue-rotate", "invert",
                "opacity", "saturate", "sepia", "drop-shadow", "inner-shadow")


def set_filters(svg: str, target_id: str, effects: list[dict[str, object]]) -> dict[str, object]:
    """Replace this tool's filter chain on one element and return editable node IDs."""
    if not isinstance(effects, list) or not 1 <= len(effects) <= 20:
        raise AnimationError("effects must contain 1 to 20 filter objects")
    root = _parse_svg(svg)
    elements = _id_index(root)
    target = elements.get(str(target_id))
    if target is None or target is root:
        raise AnimationError("target_id must identify an existing non-root element")
    filter_id = "glax-filter-" + hashlib.sha256(str(target_id).encode()).hexdigest()[:16]
    existing = elements.get(filter_id)
    if existing is not None:
        if existing.tag != _tag("filter") or existing.get("data-glax-target") != target_id:
            raise AnimationError("generated filter ID conflicts with an existing element")
        parent = next(node for node in root.iter() if existing in list(node))
        parent.remove(existing)
    defs = root.find(_tag("defs"))
    if defs is None:
        defs = ET.SubElement(root, _tag("defs"))
    chain = ET.SubElement(defs, _tag("filter"), {
        "id": filter_id, "data-glax-target": target_id,
        "x": "-100%", "y": "-100%", "width": "300%", "height": "300%",
        "color-interpolation-filters": "sRGB",
    })
    primitives: list[dict[str, str]] = []
    previous = "SourceGraphic"

    def add(kind: str, attributes: dict[str, str], parent: ET.Element = chain) -> ET.Element:
        node_id = f"{filter_id}-{len(primitives)}"
        node = ET.SubElement(parent, _tag(kind), {"id": node_id, **attributes})
        primitives.append({"id": node_id, "type": kind})
        return node

    for index, effect in enumerate(effects):
        if not isinstance(effect, Mapping) or effect.get("type") not in FILTER_TYPES:
            raise AnimationError("filter type is unsupported")
        kind = effect["type"]
        value = effect.get("value")
        output = f"effect-{index}"
        attrs = {"in": previous, "result": output}
        if kind in ("blur", "drop-shadow", "inner-shadow"):
            if not isinstance(value, Mapping):
                raise AnimationError("blur and shadow values must be objects")
            blur = value if kind == "blur" else value.get("blur")
            if not isinstance(blur, Mapping):
                raise AnimationError("blur must contain x and y")
            deviation = " ".join(f'{_number(blur.get(axis), "blur coordinate", 0, 1000):g}' for axis in ("x", "y"))
            if kind == "blur":
                add("feGaussianBlur", attrs | {"stdDeviation": deviation})
            else:
                offset, color = value.get("offset"), value.get("color")
                if not isinstance(offset, Mapping) or not isinstance(color, Mapping):
                    raise AnimationError("shadow needs offset and color objects")
                dx, dy = (f'{_number(offset.get(axis), "shadow offset", -1000, 1000):g}' for axis in ("x", "y"))
                rgb = [_number(color.get(channel), "shadow color", 0, 255) for channel in ("r", "g", "b")]
                paint = "rgb(" + ",".join(f"{channel:g}" for channel in rgb) + ")"
                alpha = f'{_number(color.get("a"), "shadow alpha", 0, 1):g}'
                if kind == "drop-shadow":
                    add("feDropShadow", attrs | {"stdDeviation": deviation, "dx": dx, "dy": dy, "flood-color": paint, "flood-opacity": alpha})
                else:
                    add("feGaussianBlur", {"in": previous, "stdDeviation": deviation, "result": output + "-blur"})
                    add("feOffset", {"in": output + "-blur", "dx": dx, "dy": dy, "result": output + "-offset"})
                    add("feComposite", {"in": previous, "in2": output + "-offset", "operator": "out", "result": output + "-cut"})
                    add("feFlood", {"flood-color": paint, "flood-opacity": alpha, "result": output + "-color"})
                    add("feComposite", {"in": output + "-color", "in2": output + "-cut", "operator": "in", "result": output + "-shadow"})
                    add("feComposite", {"in": output + "-shadow", "in2": previous, "operator": "over", "result": output})
        else:
            maximum = 1 if kind in ("grayscale", "invert", "opacity", "sepia") else 10_000
            amount = _number(value, "filter value", -360_000 if kind == "hue-rotate" else 0, 360_000 if kind == "hue-rotate" else maximum)
            if kind in ("grayscale", "saturate", "hue-rotate", "sepia"):
                matrix: dict[str, str] = {"type": "saturate", "values": f"{amount:g}"}
                if kind == "grayscale":
                    matrix["values"] = f"{1 - amount:g}"
                if kind == "hue-rotate":
                    matrix["type"] = "hueRotate"
                if kind == "sepia":
                    sepia = [0.393, 0.769, 0.189, 0, 0, 0.349, 0.686, 0.168, 0, 0, 0.272, 0.534, 0.131, 0, 0, 0, 0, 0, 1, 0]
                    identity = [1 if i in (0, 6, 12, 18) else 0 for i in range(20)]
                    matrix = {"type": "matrix", "values": " ".join(f"{base * (1 - amount) + end * amount:g}" for base, end in zip(identity, sepia))}
                add("feColorMatrix", attrs | matrix)
            else:
                transfer = add("feComponentTransfer", attrs)
                channels = ("A",) if kind == "opacity" else ("R", "G", "B")
                for channel in channels:
                    function = {"type": "linear", "slope": f"{amount:g}"}
                    if kind == "contrast":
                        function["intercept"] = f"{(1 - amount) / 2:g}"
                    if kind == "invert":
                        function = {"type": "table", "tableValues": f"{amount:g} {1 - amount:g}"}
                    add("feFunc" + channel, function, transfer)
        previous = output
    target.set("filter", f"url(#{filter_id})")
    result = _result(root)
    result.update({"filter_id": filter_id, "filter_primitives": primitives})
    return result
