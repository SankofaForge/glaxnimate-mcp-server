"""Boolean operations on static sibling SVG shapes."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
import math
import re
from xml.etree import ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform
from fontTools.svgLib.path import SVGPath

from .authoring import _result
from .lottie import SHAPES, _numbers
from .svg import AnimationError, _id_index, _local_name, _parse_svg, _tag

BOOLEAN_OPERATIONS = ("union", "subtract", "intersect", "exclude")


def _matrix(value: str) -> Transform:
    expression = r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)"
    if re.sub(expression, "", value).strip(" ,\t\r\n"):
        raise AnimationError("SVG transform syntax is unsupported")
    result = Transform()
    for kind, raw in re.findall(expression, value):
        numbers = _numbers(raw)
        sizes = {"matrix": (6,), "translate": (1, 2), "scale": (1, 2), "rotate": (1, 3), "skewX": (1,), "skewY": (1,)}
        if len(numbers) not in sizes[kind]:
            raise AnimationError("SVG transform has an invalid number of coordinates")
        if kind == "matrix":
            result = result.transform(Transform(*numbers))
        elif kind == "translate":
            result = result.translate(numbers[0], numbers[1] if len(numbers) == 2 else 0)
        elif kind == "scale":
            result = result.scale(numbers[0], numbers[1] if len(numbers) == 2 else numbers[0])
        elif kind == "rotate":
            x, y = numbers[1:] if len(numbers) == 3 else (0, 0)
            result = result.translate(x, y).rotate(math.radians(numbers[0])).translate(-x, -y)
        else:
            angle = math.radians(numbers[0])
            result = result.skew(angle if kind == "skewX" else 0, angle if kind == "skewY" else 0)
    return result


def combine_shapes(svg: str, target_ids: Sequence[str], operation: str) -> dict[str, object]:
    """Combine static sibling outlines. Retain the first shape's ID and paint."""
    if operation not in BOOLEAN_OPERATIONS:
        raise AnimationError("operation must be union, subtract, intersect, or exclude")
    minimum = 1 if operation == "union" else 2
    if not isinstance(target_ids, list) or not minimum <= len(target_ids) <= 100 or any(not isinstance(value, str) for value in target_ids) or len(set(target_ids)) != len(target_ids):
        raise AnimationError("target_ids must contain unique shape IDs within the operation limit")
    root = _parse_svg(svg)
    elements = _id_index(root)
    shapes = [elements.get(element_id) for element_id in target_ids]
    if any(shape is None or _local_name(shape.tag) not in SHAPES for shape in shapes):
        raise AnimationError("target_ids must identify supported SVG shapes")
    parents = {child: parent for parent in root.iter() for child in parent}
    parent = parents[shapes[0]]
    if any(parents[shape] is not parent for shape in shapes):
        raise AnimationError("Boolean shapes must have the same parent")
    if any(len(shape) or shape.get("style") for shape in shapes):
        raise AnimationError("Boolean shapes must not contain children, animations, or inline styles")

    def inherited(shape: ET.Element, name: str, default: str) -> str:
        while shape is not None:
            if name in shape.attrib:
                return shape.get(name)
            shape = parents.get(shape)
        return default

    try:
        import pathops
    except ImportError as error:
        raise AnimationError("install the geometry extra to combine shapes") from error
    try:
        paths = []
        for shape in shapes:
            path = pathops.Path()
            path.fillType = pathops.FillType.EVEN_ODD if inherited(shape, "fill-rule", "nonzero") == "evenodd" else pathops.FillType.WINDING
            converted = deepcopy(shape)
            transform = _matrix(converted.attrib.pop("transform", ""))
            if transform != Transform() and (inherited(shape, "stroke", "none") != "none" or any(inherited(shape, name, "none") != "none" for name in ("filter", "mask", "clip-path")) or "url(" in inherited(shape, "fill", "black")):
                raise AnimationError("Boolean transform conversion cannot preserve strokes or referenced paints and effects")
            SVGPath.fromstring(ET.tostring(converted, encoding="unicode")).draw(TransformPen(path.getPen(), transform))
            paths.append(path)
        operations = {"union": pathops.PathOp.UNION, "subtract": pathops.PathOp.DIFFERENCE, "intersect": pathops.PathOp.INTERSECTION, "exclude": pathops.PathOp.XOR}
        result = pathops.simplify(paths[0])
        for path in paths[1:]:
            result = pathops.op(result, path, operations[operation])
        pen = SVGPathPen(None)
        result.draw(pen)
    except (pathops.PathOpsError, ValueError, IndexError, AssertionError) as error:
        if isinstance(error, AnimationError):
            raise
        raise AnimationError("Boolean geometry conversion failed") from error
    combined = deepcopy(shapes[0])
    combined.tag = _tag("path")
    geometry = {"x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "points", "transform", "d"}
    for name in geometry:
        combined.attrib.pop(name, None)
    combined.set("d", pen.getCommands())
    combined.set("fill-rule", "nonzero")
    position = list(parent).index(shapes[0])
    parent.insert(position, combined)
    for shape in shapes:
        parent.remove(shape)
    return {**_result(root), "target_id": target_ids[0], "removed_ids": list(target_ids[1:]), "operation": operation}
