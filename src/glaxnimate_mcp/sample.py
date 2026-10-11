"""Evaluate animation channels at one time and write the values as static attributes."""

from __future__ import annotations

import bisect
import itertools
import math
import re
from collections.abc import Mapping, Sequence
from xml.etree import ElementTree as ET

from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path

from .svg import MAX_ANIMATIONS, AnimationError, _animation_element, _id_index, _local_name, _number

COLOR_ATTRIBUTES = frozenset({"fill", "stroke", "stop-color", "flood-color"})
NUMBER = re.compile(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
NAMED_COLORS = {
    "black": "#000000", "silver": "#c0c0c0", "gray": "#808080", "white": "#ffffff", "maroon": "#800000",
    "red": "#ff0000", "purple": "#800080", "fuchsia": "#ff00ff", "green": "#008000", "lime": "#00ff00",
    "olive": "#808000", "yellow": "#ffff00", "navy": "#000080", "blue": "#0000ff", "teal": "#008080",
    "aqua": "#00ffff", "orange": "#ffa500",
}
CURVE_STEPS = 256


class _Polyline(BasePen):
    """Flatten path data into subpaths of points."""

    def __init__(self) -> None:
        super().__init__(None)
        self.subpaths: list[list[tuple[float, float]]] = []

    def _moveTo(self, point: tuple[float, float]) -> None:
        self.subpaths.append([point])

    def _lineTo(self, point: tuple[float, float]) -> None:
        self.subpaths[-1].append(point)

    def _curveToOne(self, first: tuple[float, float], second: tuple[float, float], point: tuple[float, float]) -> None:
        start = self.subpaths[-1][-1]
        for step in range(1, CURVE_STEPS + 1):
            s = step / CURVE_STEPS
            weights = ((1 - s) ** 3, 3 * s * (1 - s) ** 2, 3 * s * s * (1 - s), s ** 3)
            self.subpaths[-1].append(tuple(sum(weight * control[axis] for weight, control in zip(weights, (start, first, second, point))) for axis in (0, 1)))

    def _closePath(self) -> None:
        self.subpaths[-1].append(self.subpaths[-1][0])

    def _endPath(self) -> None:
        pass


def _rgb(value: str) -> list[float]:
    value = NAMED_COLORS.get(value.strip().lower(), value.strip())
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        value = "#" + "".join(character * 2 for character in value[1:])
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return [int(value[index:index + 2], 16) for index in (1, 3, 5)]
    match = re.fullmatch(r"rgb\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)", value)
    if match is None:
        raise AnimationError("sampled colors require #RGB, #RRGGBB, rgb(), or a basic color name")
    return [float(channel) for channel in match.groups()]


def _mix(first: str, second: str, fraction: float, color: bool) -> str:
    """Interpolate colors per channel, or the numbers inside structurally equal values."""
    if color:
        channels = [a + (b - a) * fraction for a, b in zip(_rgb(first), _rgb(second))]
        return "rgb(" + ", ".join(f"{channel:.10g}" for channel in channels) + ")"
    first_parts, second_parts = NUMBER.split(first), NUMBER.split(second)
    separators = [[re.sub(r"[\s,]+", " ", part).strip() for part in parts[::2]] for parts in (first_parts, second_parts)]
    if len(first_parts) != len(second_parts) or separators[0] != separators[1]:
        raise AnimationError("sampled values must share the same structure to interpolate")
    parts = list(first_parts)
    parts[1::2] = [f"{float(a) + (float(b) - float(a)) * fraction:.10g}" for a, b in zip(first_parts[1::2], second_parts[1::2])]
    return "".join(parts)


def _bezier(first: float, second: float, s: float) -> float:
    return 3 * first * s * (1 - s) ** 2 + 3 * second * s * s * (1 - s) + s ** 3


def _ease(curve: list[float], x: float) -> float:
    low, high = 0.0, 1.0
    for _ in range(60):
        middle = (low + high) / 2
        if _bezier(curve[0], curve[2], middle) < x:
            low = middle
        else:
            high = middle
    return _bezier(curve[1], curve[3], (low + high) / 2)


def _progress(element: ET.Element, time_ms: float) -> float | None:
    """Return simple-duration progress from 0 to 1, or None when the channel has no effect."""
    begin, duration = float(element.get("begin")[:-2]), float(element.get("dur")[:-2])
    repeat = math.inf if element.get("repeatCount") == "indefinite" else float(element.get("repeatCount"))
    if time_ms < begin:
        return None
    elapsed = time_ms - begin
    if elapsed >= duration * repeat:
        if element.get("fill") != "freeze":
            return None
        return repeat % 1 or 1.0
    return elapsed % duration / duration


def _interval(element: ET.Element, values: list[str], progress: float, color: bool) -> str:
    """Select or interpolate keyframe values for one progress value."""
    if progress >= 1:
        return values[-1]
    times = [float(time) for time in element.get("keyTimes").split(";")]
    index = max(position for position, time in enumerate(times) if time <= progress)
    if element.get("calcMode") == "discrete":
        return values[index]
    local = (progress - times[index]) / (times[index + 1] - times[index])
    if element.get("calcMode") == "spline":
        local = _ease([float(number) for number in element.get("keySplines").split(";")[index].split()], local)
    return _mix(values[index], values[index + 1], local, color)


def _motion(element: ET.Element, progress: float) -> str:
    """Return the supplemental motion transform for a point along the motion path."""
    distance = float(_interval(element, element.get("keyPoints").split(";"), progress, False))
    pen = _Polyline()
    try:
        parse_path(element.get("path"), pen)
    except (ValueError, IndexError, AssertionError) as error:
        raise AnimationError("motion_path is invalid") from error
    segments = [(start, end) for subpath in pen.subpaths for start, end in zip(subpath, subpath[1:]) if start != end]
    if not segments:
        raise AnimationError("motion_path must have a positive length")
    lengths = [math.dist(start, end) for start, end in segments]
    cumulative = list(itertools.accumulate(lengths))
    target = distance * cumulative[-1]
    index = min(bisect.bisect_left(cumulative, target), len(segments) - 1)
    start, end = segments[index]
    fraction = (target - cumulative[index] + lengths[index]) / lengths[index]
    x, y = (a + (b - a) * fraction for a, b in zip(start, end))
    rotation = element.get("rotate")
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    angle = angle if rotation == "auto" else angle + 180 if rotation == "auto-reverse" else float(rotation)
    return f"translate({x:.10g} {y:.10g}) rotate({angle:.10g})"


def sample_frame(root: ET.Element, animations: Sequence[Mapping[str, object]], time_ms: float) -> None:
    """Write each channel's value at time_ms onto its target element.

    Channels that have not begun, or have ended with fill_mode=remove, leave base values.
    Later-beginning channels take priority; equal begin times use array order.
    Transforms follow additive replace and sum. Motion paths precede the transform list.
    """
    if not isinstance(animations, list) or len(animations) > MAX_ANIMATIONS:
        raise AnimationError(f"animations must be an array of at most {MAX_ANIMATIONS} entries")
    time_ms = _number(time_ms, "time_ms", 0, 3_600_000)
    elements = _id_index(root)
    active: list[tuple[float, int, ET.Element, ET.Element, float]] = []
    for order, spec in enumerate(animations):
        if not isinstance(spec, Mapping):
            raise AnimationError("each animation must be an object")
        target_id, element = _animation_element(spec)
        if target_id not in elements:
            raise AnimationError(f"animation target does not exist: {target_id}")
        progress = _progress(element, time_ms)
        if progress is not None:
            active.append((float(element.get("begin")[:-2]), order, elements[target_id], element, progress))
    transforms: dict[ET.Element, str] = {}
    motions: dict[ET.Element, str] = {}
    for _, _, target, element, progress in sorted(active, key=lambda entry: entry[:2]):
        kind = _local_name(element.tag)
        if kind == "animateMotion":
            motions[target] = _motion(element, progress)
        elif kind == "animateTransform":
            value = f"{element.get('type')}({_interval(element, element.get('values').split(';'), progress, False)})"
            underlying = transforms.get(target, target.get("transform", ""))
            transforms[target] = f"{underlying} {value}".strip() if element.get("additive") == "sum" else value
        else:
            name = element.get("attributeName")
            target.set(name, _interval(element, element.get("values").split(";"), progress, name in COLOR_ATTRIBUTES))
    for target in transforms.keys() | motions.keys():
        target.set("transform", " ".join(part for part in (motions.get(target), transforms.get(target, target.get("transform"))) if part))
