"""Inspect and edit static path coordinates in the element's coordinate system."""

from collections.abc import Mapping
import math
import re

from fontTools.pens.basePen import BasePen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.svgLib.path import parse_path

from .authoring import _result
from .svg import AnimationError, _id_index, _local_name, _number, _parse_svg

MAX_COMMANDS = 10_000


class _Commands(BasePen):
    def __init__(self) -> None:
        super().__init__(None)
        self.commands: list[dict[str, object]] = []

    def _append(self, command: str, *points: tuple[float, float]) -> None:
        if len(self.commands) >= MAX_COMMANDS:
            raise AnimationError("path exceeds the 10000-command limit")
        coordinates = [[_number(value, "path coordinate", -1e9, 1e9) for value in point] for point in points]
        self.commands.append({"command": command, "points": coordinates})

    def _moveTo(self, point: tuple[float, float]) -> None:
        self._append("moveTo", point)

    def _lineTo(self, point: tuple[float, float]) -> None:
        self._append("lineTo", point)

    def _curveToOne(self, first: tuple[float, float], second: tuple[float, float], point: tuple[float, float]) -> None:
        self._append("curveTo", first, second, point)

    def _closePath(self) -> None:
        self._append("closePath")

    def _endPath(self) -> None:
        self._append("endPath")


ACTIONS = {
    "set_point": {"command_index", "point_index", "x", "y"},
    "split_segment": {"command_index", "t"},
    "remove_command": {"command_index"},
}
SEGMENTS = ("lineTo", "curveTo")


def _lerp(first: list[float], second: list[float], t: float) -> list[float]:
    return [a + (b - a) * t for a, b in zip(first, second)]


def _mirror(commands: list[dict[str, object]], index: int, point_index: int, mode: object) -> None:
    """Keep the handle on the other side of a node collinear with the edited handle."""
    if mode not in ("symmetric", "aligned") or commands[index]["command"] != "curveTo" or point_index == 2:
        raise AnimationError("mirror accepts symmetric or aligned on a curveTo control point")
    neighbor, opposite = (index + 1, 0) if point_index == 1 else (index - 1, 1)
    if not 0 <= neighbor < len(commands) or commands[neighbor]["command"] != "curveTo":
        raise AnimationError("mirror requires an adjacent curveTo command")
    node = commands[index]["points"][2] if point_index == 1 else commands[neighbor]["points"][2]
    handle = [a - b for a, b in zip(commands[index]["points"][point_index], node)]
    points = commands[neighbor]["points"]
    scale = 1.0
    if mode == "aligned":
        length = math.dist(handle, [0, 0])
        scale = math.dist(points[opposite], node) / length if length else 0
    if mode == "symmetric" or scale:
        points[opposite] = [n - h * scale for n, h in zip(node, handle)]


def edit_path(svg: str, target_id: str, operations: list[dict[str, object]]) -> dict[str, object]:
    """Normalize a static path and edit its commands. An empty list inspects the path.

    Commands use absolute coordinates in the element's coordinate system.
    set_point needs command_index, point_index, x, and y, and accepts mirror.
    split_segment needs command_index and t between 0 and 1. It splits a line or curve.
    remove_command needs command_index. It removes a line or curve and its end node.
    Operations run in order. Indices refer to the commands after earlier operations.
    This function preserves element IDs, transforms, and other attributes.
    """
    if not isinstance(operations, list) or len(operations) > 100:
        raise AnimationError("operations must be an array of at most 100 objects")
    root = _parse_svg(svg)
    target = _id_index(root).get(target_id) if isinstance(target_id, str) else None
    if target is None or _local_name(target.tag) != "path":
        raise AnimationError("target_id must identify a path element")
    if any(_local_name(node.tag) in {"style", "animate", "animateTransform", "animateMotion", "set", "script"} for node in root.iter()):
        raise AnimationError("path editing requires SVG without stylesheets, scripts, or animations")
    parents = {child: parent for parent in root.iter() for child in parent}
    ancestor = target
    while ancestor is not None:
        if "style" in ancestor.attrib:
            raise AnimationError("the path and its ancestors must not have inline styles")
        ancestor = parents.get(ancestor)
    data = target.get("d", "")
    if re.search(r"[^MmZzLlHhVvCcSsQqTtAaEe0-9+.,\s-]", data):
        raise AnimationError("path data contains an invalid character")
    pen = _Commands()
    try:
        parse_path(data, pen)
    except AnimationError:
        raise
    except (ValueError, IndexError, AssertionError, TypeError) as error:
        raise AnimationError("path data is invalid") from error
    if not pen.commands:
        raise AnimationError("path data must contain at least one command")
    commands = pen.commands
    for operation in operations:
        action = operation.get("action") if isinstance(operation, Mapping) else None
        if action not in ACTIONS:
            raise AnimationError("each operation needs action set_point, split_segment, or remove_command")
        fields = set(operation) - {"action"}
        if fields - {"mirror"} != ACTIONS[action] or ("mirror" in fields and action != "set_point"):
            raise AnimationError(f"{action} needs {', '.join(sorted(ACTIONS[action]))}" + (" and optional mirror" if action == "set_point" else ""))
        command_index = operation["command_index"]
        if type(command_index) is not int or not 0 <= command_index < len(commands):
            raise AnimationError("command_index must identify an existing command")
        command = commands[command_index]
        if action == "set_point":
            point_index = operation["point_index"]
            if type(point_index) is not int or not 0 <= point_index < len(command["points"]):
                raise AnimationError("point_index must identify a point in the command")
            command["points"][point_index] = [_number(operation[axis], axis, -1e9, 1e9) for axis in ("x", "y")]
            if "mirror" in operation:
                _mirror(commands, command_index, point_index, operation["mirror"])
            continue
        if command["command"] not in SEGMENTS:
            raise AnimationError(f"{action} requires a lineTo or curveTo command")
        if action == "remove_command":
            del commands[command_index]
            continue
        t = _number(operation["t"], "t", 0, 1)
        if t in (0, 1):
            raise AnimationError("t must be greater than 0 and less than 1")
        if len(commands) >= MAX_COMMANDS:
            raise AnimationError("path exceeds the 10000-command limit")
        start = commands[command_index - 1]["points"][-1]
        if command["command"] == "lineTo":
            commands.insert(command_index, {"command": "lineTo", "points": [_lerp(start, command["points"][0], t)]})
            continue
        first, second, end = command["points"]
        a, b, c = _lerp(start, first, t), _lerp(first, second, t), _lerp(second, end, t)
        d, e = _lerp(a, b, t), _lerp(b, c, t)
        command["points"] = [e, c, end]
        commands.insert(command_index, {"command": "curveTo", "points": [a, d, _lerp(d, e, t)]})
    output = SVGPathPen(None)
    for command in pen.commands:
        getattr(output, command["command"])(*[tuple(point) for point in command["points"]])
    target.set("d", output.getCommands())
    return {**_result(root), "target_id": target_id, "commands": pen.commands, "coordinate_system": "element-local"}
