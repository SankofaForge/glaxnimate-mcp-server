"""Vector Lottie export with explicit limits on supported SVG content."""

from __future__ import annotations

import base64
import binascii
import itertools
import json
import math
import re
import struct
from collections.abc import Callable, Mapping, Sequence
from xml.etree import ElementTree as ET

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import SVGPath, parse_path

from .svg import AnimationError, _animation_element, _id_index, _local_name, _number, _parse_svg, _tag

LOTTIE_PROPERTIES = frozenset({"translate", "rotate", "scale", "skewX", "skewY", "opacity", "fill", "stroke", "fill-opacity", "stroke-opacity", "stroke-width", "path"})
SHAPES = frozenset({"rect", "circle", "ellipse", "line", "polyline", "polygon", "path"})
PAINT = frozenset({"fill", "stroke", "fill-opacity", "stroke-opacity", "stroke-width", "fill-rule", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit"})
ATTRIBUTES = PAINT | frozenset({"id", "transform", "opacity", "x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "points", "d"})
GRADIENTS = frozenset({"linearGradient", "radialGradient"})
LAYERED = frozenset({"clip-path", "mask"})
TRANSFORM_KEYS = {"translate": "p", "scale": "s", "rotate": "r", "skewX": "sk", "skewY": "sk"}
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
ALIGNMENT = {"Min": 0, "Mid": 0.5, "Max": 1}


class PathPen(BasePen):
    """Convert SVG segments to Lottie vertices and relative cubic tangents."""

    def __init__(self) -> None:
        super().__init__(None)
        self.paths: list[dict[str, object]] = []
        self.current: dict[str, object] = {}

    def _moveTo(self, point: tuple[float, float]) -> None:
        self.current = {"v": [list(point)], "i": [[0, 0]], "o": [[0, 0]], "c": False}
        self.paths.append(self.current)

    def _lineTo(self, point: tuple[float, float]) -> None:
        self.current["v"].append(list(point))
        self.current["i"].append([0, 0])
        self.current["o"].append([0, 0])

    def _curveToOne(self, first: tuple[float, float], second: tuple[float, float], point: tuple[float, float]) -> None:
        start = self.current["v"][-1]
        self.current["o"][-1] = [first[0] - start[0], first[1] - start[1]]
        self._lineTo(point)
        self.current["i"][-1] = [second[0] - point[0], second[1] - point[1]]

    def _closePath(self) -> None:
        if len(self.current["v"]) > 1 and self.current["v"][-1] == self.current["v"][0]:
            self.current["i"][0] = self.current["i"].pop()
            self.current["v"].pop()
            self.current["o"].pop()
        self.current["c"] = True

    def _endPath(self) -> None:
        pass


def _numeric(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AnimationError("Lottie values must use finite numbers without units") from error
    return _number(number, "Lottie value", -1e9, 1e9)


def _numbers(value: str) -> list[float]:
    return [_numeric(part) for part in value.replace(",", " ").split()]


def _color(value: str) -> list[float]:
    names = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00"}
    value = names.get(value.lower(), value)
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        value = "#" + "".join(character * 2 for character in value[1:])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise AnimationError("Lottie colors require #RGB, #RRGGBB, or a supported basic color name")
    return [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]


def _path(value: str) -> list[dict[str, object]]:
    pen = PathPen()
    try:
        parse_path(value, pen)
    except (ValueError, IndexError, AssertionError) as error:
        raise AnimationError("invalid SVG path for Lottie export") from error
    if not pen.paths:
        raise AnimationError("Lottie path must contain at least one contour")
    return pen.paths


def _static(value: object) -> dict[str, object]:
    return {"a": 0, "k": value}


def _animated(spec: Mapping[str, object], fps: float, convert: Callable[[str], object], base: object) -> dict[str, object]:
    _, element = _animation_element(spec)
    values = [convert(value) for value in element.get("values").split(";")]
    begin = float(spec.get("begin_ms", 0)) * fps / 1000
    duration = float(spec.get("duration_ms", 1000)) * fps / 1000
    keys: list[dict[str, object]] = []
    if begin > 0:
        keys.append({"t": 0, "s": base if isinstance(base, list) else [base], "h": 1})
    for index, (time, value) in enumerate(zip(element.get("keyTimes").split(";"), values)):
        key = {"t": begin + float(time) * duration, "s": value if isinstance(value, list) else [value]}
        if element.get("calcMode") == "discrete":
            key["h"] = 1
        else:
            curve = [0, 0, 1, 1]
            if element.get("calcMode") == "spline" and index < len(values) - 1:
                curve = _numbers(element.get("keySplines").split(";")[index])
            key.update({"o": {"x": [curve[0]], "y": [curve[1]]}, "i": {"x": [curve[2]], "y": [curve[3]]}})
        keys.append(key)
    return {"a": 1, "k": keys}


def _channel(channels: Mapping[str, Mapping[str, object]], consumed: set[str], name: str, base: object, convert: Callable[[str], object], fps: float) -> dict[str, object]:
    spec = channels.get(name)
    if spec is None:
        return _static(base)
    consumed.add(name)
    return _animated(spec, fps, convert, base)


def _transform() -> dict[str, object]:
    return {"ty": "tr", "a": _static([0, 0]), "p": _static([0, 0]), "s": _static([100, 100]), "r": _static(0), "o": _static(100), "sk": _static(0), "sa": _static(0)}


def _transform_value(kind: str, value: str) -> object:
    numbers = _numbers(value)
    sizes = {"translate": (1, 2), "scale": (1, 2), "rotate": (1, 3), "skewX": (1,), "skewY": (1,)}
    if len(numbers) not in sizes[kind]:
        raise AnimationError("Lottie transforms require translate(x,y), scale(x,y), rotate(angle[,x,y]), or a single skew angle")
    if kind == "translate":
        return [numbers[0], numbers[1] if len(numbers) == 2 else 0]
    if kind == "scale":
        return [numbers[0] * 100, (numbers[1] if len(numbers) == 2 else numbers[0]) * 100]
    return -numbers[0] if kind.startswith("skew") else numbers[0]


def _transforms(element: ET.Element, channels: Mapping[str, Mapping[str, object]], consumed: set[str], fps: float) -> list[dict[str, object]]:
    """Return Lottie transforms for an element, outermost first."""
    transforms: list[dict[str, object]] = []
    raw_transform = element.get("transform", "")
    parsed = list(re.finditer(r"(translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", raw_transform))
    remaining = re.sub(r"(translate|scale|rotate|skewX|skewY)\s*\([^)]*\)", "", raw_transform)
    if remaining.strip(" ,\t\r\n"):
        raise AnimationError("Lottie static transform syntax is unsupported")
    for match in parsed:
        kind, value = match.groups()
        transform = _transform()
        transform[TRANSFORM_KEYS[kind]] = _static(_transform_value(kind, value))
        if kind == "rotate":
            pivot = _numbers(value)[1:] or [0, 0]
            transform["a"] = _static(pivot)
            transform["p"] = _static(pivot)
        transform["sa"] = _static(90 if kind == "skewY" else 0)
        transforms.append(transform)
    for spec in channels.values():
        kind = spec["property"]
        if kind not in TRANSFORM_KEYS:
            continue
        transform = _transform()
        key = TRANSFORM_KEYS[kind]
        transform[key] = _channel(channels, consumed, kind, transform[key]["k"], lambda value: _transform_value(kind, value), fps)
        if kind == "rotate":
            pivot = _animated(spec, fps, lambda value: _numbers(value)[1:] or [0, 0], [0, 0])
            transform["a"] = pivot
            transform["p"] = pivot
        transform["sa"] = _static(90 if kind == "skewY" else 0)
        if spec.get("additive", "replace") == "replace":
            if transforms and float(spec.get("begin_ms", 0)) > 0:
                raise AnimationError("Lottie cannot preserve a delayed replacing transform over an existing transform")
            transforms = []
        transforms.append(transform)
    return transforms


def _wrap(items: list[dict[str, object]], transform: dict[str, object], name: str) -> list[dict[str, object]]:
    return [{"ty": "gr", "nm": name, "it": items + [transform]}]


def _reference(value: str) -> str | None:
    match = re.fullmatch(r"url\(\s*#([^\s)'\"]+)\s*\)", value.strip())
    return match[1] if match else None


def _fraction(value: str) -> float:
    value = value.strip()
    return _numeric(value[:-1]) / 100 if value.endswith("%") else _numeric(value)


def _gradient(source: ET.Element, bounds: tuple[float, float, float, float] | None, width: float, height: float) -> dict[str, object]:
    """Convert a gradient to Lottie start, end, and color stops in the shape's coordinates."""
    radial = _local_name(source.tag) == "radialGradient"
    geometry = ("cx", "cy", "r", "fx", "fy") if radial else ("x1", "y1", "x2", "y2")
    if any(name not in {"id", "gradientUnits", "spreadMethod", *geometry} for name in source.attrib):
        raise AnimationError("Lottie gradients support geometry, gradientUnits, and spreadMethod=pad only")
    units = source.get("gradientUnits", "objectBoundingBox")
    if units not in ("objectBoundingBox", "userSpaceOnUse") or source.get("spreadMethod", "pad") != "pad":
        raise AnimationError("Lottie gradients require known gradientUnits and spreadMethod=pad")
    stops: list[tuple[float, list[float], float]] = []
    for stop in source:
        if _local_name(stop.tag) != "stop" or len(stop) or any(name not in {"id", "offset", "stop-color", "stop-opacity"} for name in stop.attrib):
            raise AnimationError("Lottie gradient children must be stops with offset, stop-color, and stop-opacity")
        offset = max(min(_fraction(stop.get("offset", "0")), 1), 0, stops[-1][0] if stops else 0)
        stops.append((offset, _color(stop.get("stop-color", "black")), max(min(_numeric(stop.get("stop-opacity", "1")), 1), 0)))
    if not stops:
        raise AnimationError("Lottie gradients require at least one stop")
    if len(stops) == 1:
        stops = [(0, stops[0][1], stops[0][2]), (1, stops[0][1], stops[0][2])]
    colors = [number for offset, color, _ in stops for number in (offset, *color)]
    if any(opacity != 1 for *_, opacity in stops):
        colors += [number for offset, _, opacity in stops for number in (offset, opacity)]
    defaults = {"x1": "0%", "y1": "0%", "x2": "100%", "y2": "0%", "cx": "50%", "cy": "50%", "r": "50%"}
    defaults.update({"fx": source.get("cx", "50%"), "fy": source.get("cy", "50%")})
    raw = {name: source.get(name, defaults[name]) for name in geometry}
    axis = {"x1": "x", "x2": "x", "cx": "x", "fx": "x", "y1": "y", "y2": "y", "cy": "y", "fy": "y", "r": "r"}
    if units == "objectBoundingBox":
        if bounds is None or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise AnimationError("objectBoundingBox gradients require static geometry with nonzero width and height")
        left, top, right, bottom = bounds
        if radial and not math.isclose(right - left, bottom - top):
            raise AnimationError("objectBoundingBox radial gradients require square bounds; use userSpaceOnUse")
        origins = {"x": left, "y": top, "r": 0}
        sizes = {"x": right - left, "y": bottom - top, "r": right - left}
        value = {name: origins[axis[name]] + _fraction(text) * sizes[axis[name]] for name, text in raw.items()}
    else:
        sizes = {"x": width, "y": height, "r": math.hypot(width, height) / math.sqrt(2)}
        value = {name: _fraction(text) * sizes[axis[name]] if text.strip().endswith("%") else _numeric(text) for name, text in raw.items()}
    result: dict[str, object] = {"g": {"p": len(stops), "k": _static(colors)}}
    if not radial:
        return result | {"s": _static([value["x1"], value["y1"]]), "e": _static([value["x2"], value["y2"]]), "t": 1}
    radius, focus = value["r"], math.hypot(value["fx"] - value["cx"], value["fy"] - value["cy"])
    if radius <= 0 or focus >= radius:
        raise AnimationError("Lottie radial gradients require a positive radius and a focal point inside the circle")
    angle = math.degrees(math.atan2(value["fy"] - value["cy"], value["fx"] - value["cx"])) if focus else 0
    return result | {"s": _static([value["cx"], value["cy"]]), "e": _static([value["cx"] + radius, value["cy"]]), "t": 2, "h": _static(focus / radius * 100), "a": _static(angle)}


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 <= len(data) and data[index] == 0xFF:
        marker = data[index + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[index + 5:index + 9])
            return width, height
        index += 2 + struct.unpack(">H", data[index + 2:index + 4])[0]
    return None


def _image_size(uri: str) -> tuple[int, int]:
    """Read intrinsic pixel dimensions from an embedded image header."""
    match = re.fullmatch(r"data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)", uri)
    if match is None:
        raise AnimationError("Lottie images require base64 PNG, JPEG, GIF, or WebP data URIs")
    try:
        data = base64.b64decode(match[2], validate=True)
    except binascii.Error as error:
        raise AnimationError("Lottie image data is not valid base64") from error
    kind, size = match[1], None
    if kind == "png" and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        size = struct.unpack(">II", data[16:24])
    elif kind == "gif" and data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        size = struct.unpack("<HH", data[6:10])
    elif kind == "jpeg" and data[:2] == b"\xff\xd8":
        size = _jpeg_size(data)
    elif kind == "webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            size = (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
        elif chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            size = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif chunk == b"VP8 ":
            size = (int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF)
    if not size or 0 in size:
        raise AnimationError("Lottie could not read the embedded image dimensions")
    return size


def export_lottie(svg: str, animations: Sequence[Mapping[str, object]], fps: float = 30, duration_ms: float = 1000) -> dict[str, object]:
    """Export a vector composition. Reject content that this exporter cannot preserve.

    Gradients become Lottie gradient fills and strokes. Images and elements with
    clip-path or mask become separate layers; they must be direct children of the root.
    """
    root = _parse_svg(svg)
    elements = _id_index(root)
    fps = _number(fps, "fps", 1, 120)
    duration_ms = _number(duration_ms, "duration_ms", 1, 600_000)
    if not isinstance(animations, list) or len(animations) > 100:
        raise AnimationError("animations must be an array of at most 100 entries")
    tracks: dict[str, dict[str, Mapping[str, object]]] = {}
    for spec in animations:
        if not isinstance(spec, Mapping):
            raise AnimationError("each animation must be an object")
        target, _ = _animation_element(spec)
        property = spec["property"]
        if target not in elements or property not in LOTTIE_PROPERTIES:
            raise AnimationError("Lottie animation target or property is unsupported")
        if spec.get("repeat_count", 1) != 1 or spec.get("fill_mode", "freeze") != "freeze":
            raise AnimationError("Lottie channels require repeat_count=1 and fill_mode=freeze")
        if float(spec.get("begin_ms", 0)) + float(spec.get("duration_ms", 1000)) > duration_ms:
            raise AnimationError("duration_ms must contain every Lottie channel")
        if property in tracks.setdefault(target, {}):
            raise AnimationError("Lottie supports one channel per target and property")
        tracks[target][property] = spec
    width, height = _numeric(root.get("width", "512")), _numeric(root.get("height", "512"))
    _number(width, "width", 1, 100_000)
    _number(height, "height", 1, 100_000)
    viewbox = _numbers(root.get("viewBox", f"0 0 {width:g} {height:g}"))
    if viewbox != [0, 0, width, height]:
        raise AnimationError("Lottie requires viewBox=0 0 width height")
    frames = duration_ms * fps / 1000
    applied: set[str | None] = set()
    assets: list[dict[str, object]] = []
    counter = itertools.count(1)

    def node(element: ET.Element, inherited: dict[str, str], channels: Mapping[str, Mapping[str, object]] | None = None) -> list[dict[str, object]]:
        kind = _local_name(element.tag)
        if kind in {"title", "desc", "metadata", "defs", "clipPath", "mask"} | GRADIENTS:
            return []
        if kind == "image" or LAYERED & set(element.attrib):
            raise AnimationError("Lottie supports images, clip-path, and mask only on direct children of the root svg")
        if kind not in SHAPES | {"svg", "g"}:
            raise AnimationError(f"Lottie element is unsupported: {kind}")
        allowed = ATTRIBUTES | ({"viewBox", "version", "xmlns"} if element is root else set())
        if any(attribute not in allowed for attribute in element.attrib):
            raise AnimationError("Lottie cannot preserve an SVG attribute on this element")
        styles = inherited | {name: value for name, value in element.attrib.items() if name in PAINT}
        if channels is None:
            channels = tracks.get(element.get("id"), {})
            applied.add(element.get("id"))
        consumed: set[str] = set()

        def property(name: str, base: object, convert: Callable[[str], object]) -> dict[str, object]:
            return _channel(channels, consumed, name, base, convert, fps)

        if kind in ("svg", "g"):
            items = [item for child in reversed(list(element)) for item in node(child, styles)]
        else:
            if len(element):
                raise AnimationError("Lottie shape elements cannot contain children")
            copy = ET.Element(kind, {name: value for name, value in element.attrib.items() if name not in PAINT | {"transform", "opacity", "id"}})
            pen, bounds_pen = PathPen(), BoundsPen(None)
            try:
                for target in (pen, bounds_pen):
                    SVGPath.fromstring(ET.tostring(copy, encoding="unicode")).draw(target)
            except (ValueError, IndexError, AssertionError) as error:
                raise AnimationError("invalid SVG geometry for Lottie export") from error
            paths = pen.paths
            if not paths:
                raise AnimationError("Lottie shape has no drawable geometry")
            bounds = bounds_pen.bounds
            items = []
            morph = channels.get("path")
            if morph is not None:
                if kind != "path":
                    raise AnimationError("Lottie path animation requires a path element")
                frames_data = [_path(value) for value in _animation_element(morph)[1].get("values").split(";")]
                signatures = [[(len(path["v"]), path["c"]) for path in frame] for frame in [paths] + frames_data]
                if any(signature != signatures[0] for signature in signatures):
                    raise AnimationError("Lottie morph paths require equal contour and vertex counts")
                consumed.add("path")
                bounds = None
            for index, path in enumerate(paths):
                shape = _static(path)
                if morph is not None:
                    shape = _animated(morph, fps, lambda value: [_path(value)[index]], [path])
                items.append({"ty": "sh", "ks": shape, "d": 1})
            for paint, solid, gradient in (("fill", "fl", "gf"), ("stroke", "st", "gs")):
                value = styles.get(paint, "black" if paint == "fill" else "none")
                if value == "none":
                    continue
                reference = _reference(value)
                if reference is not None:
                    source = elements.get(reference)
                    if source is None or _local_name(source.tag) not in GRADIENTS:
                        raise AnimationError("Lottie paint references must identify a linear or radial gradient")
                    style = {"ty": gradient, **_gradient(source, bounds, width, height)}
                else:
                    style = {"ty": solid, "c": property(paint, _color(value), _color)}
                style["o"] = property(paint + "-opacity", _numeric(styles.get(paint + "-opacity", "1")) * 100, lambda value: _numeric(value) * 100)
                if paint == "fill":
                    rule = styles.get("fill-rule", "nonzero")
                    if rule not in ("nonzero", "evenodd"):
                        raise AnimationError("Lottie fill-rule must be nonzero or evenodd")
                    style["r"] = 2 if rule == "evenodd" else 1
                else:
                    cap = styles.get("stroke-linecap", "butt")
                    join = styles.get("stroke-linejoin", "miter")
                    if cap not in ("butt", "round", "square") or join not in ("miter", "round", "bevel"):
                        raise AnimationError("Lottie stroke cap or join is unsupported")
                    style.update({"w": property("stroke-width", _numeric(styles.get("stroke-width", "1")), _numeric), "lc": ("butt", "round", "square").index(cap) + 1, "lj": ("miter", "round", "bevel").index(join) + 1, "ml": _numeric(styles.get("stroke-miterlimit", "4"))})
                items.append(style)
        opacity = _transform()
        opacity["o"] = property("opacity", _numeric(element.get("opacity", "1")) * 100, lambda value: _numeric(value) * 100)
        items = _wrap(items, opacity, element.get("id", kind))
        for transform in reversed(_transforms(element, channels, consumed, fps)):
            items = _wrap(items, transform, "transform")
        if set(channels) - consumed:
            raise AnimationError("Lottie animation cannot apply to this element or paint")
        return items

    def layer(ty: int, name: str, transform: dict[str, object] | None = None, **extra: object) -> dict[str, object]:
        transform = {key: value for key, value in (transform or _transform()).items() if key != "ty"}
        return {"ty": ty, "ind": next(counter), "nm": name, "ip": 0, "op": frames, "st": 0, "sr": 1, "ks": transform, **extra}

    def image(element: ET.Element) -> list[dict[str, object]]:
        """Return an image layer followed by null parents for its transforms."""
        allowed = {"id", "href", XLINK_HREF, "x", "y", "width", "height", "preserveAspectRatio", "transform", "opacity"}
        if len(element) or any(name not in allowed for name in element.attrib):
            raise AnimationError("Lottie images support href, position, size, preserveAspectRatio, transform, and opacity only")
        uri = element.get("href", element.get(XLINK_HREF, ""))
        intrinsic_width, intrinsic_height = _image_size(uri)
        x, y = _numeric(element.get("x", "0")), _numeric(element.get("y", "0"))
        box_width, box_height = _numeric(element.get("width", "0")), _numeric(element.get("height", "0"))
        if box_width <= 0 or box_height <= 0:
            raise AnimationError("Lottie images require positive width and height attributes")
        aspect = element.get("preserveAspectRatio", "xMidYMid meet").split()
        if aspect == ["none"]:
            scale_x, scale_y, offset_x, offset_y = box_width / intrinsic_width, box_height / intrinsic_height, 0, 0
        else:
            match = re.fullmatch(r"x(Min|Mid|Max)Y(Min|Mid|Max)", aspect[0] if aspect else "")
            if match is None or aspect[1:] not in ([], ["meet"]):
                raise AnimationError("Lottie images support preserveAspectRatio none or an alignment with meet")
            scale_x = scale_y = min(box_width / intrinsic_width, box_height / intrinsic_height)
            offset_x = (box_width - intrinsic_width * scale_x) * ALIGNMENT[match[1]]
            offset_y = (box_height - intrinsic_height * scale_y) * ALIGNMENT[match[2]]
        channels = tracks.get(element.get("id"), {})
        applied.add(element.get("id"))
        consumed: set[str] = set()
        placement = _transform()
        placement.update({"p": _static([x + offset_x, y + offset_y]), "s": _static([scale_x * 100, scale_y * 100])})
        placement["o"] = _channel(channels, consumed, "opacity", _numeric(element.get("opacity", "1")) * 100, lambda value: _numeric(value) * 100, fps)
        parents = [layer(3, "transform", transform) for transform in _transforms(element, channels, consumed, fps)]
        if set(channels) - consumed:
            raise AnimationError("Lottie image animations support transforms and opacity only")
        for child, parent in zip(parents[1:], parents):
            child["parent"] = parent["ind"]
        asset = f"image_{len(assets)}"
        assets.append({"id": asset, "w": intrinsic_width, "h": intrinsic_height, "u": "", "p": uri, "e": 1})
        content = layer(2, element.get("id", "image"), placement, refId=asset)
        if parents:
            content["parent"] = parents[-1]["ind"]
        return [content, *parents]

    def matte(element: ET.Element, attribute: str) -> dict[str, object]:
        """Build a hidden matte layer in the referencing element's user space."""
        reference = _reference(element.get(attribute))
        source = elements.get(reference) if reference else None
        expected = "clipPath" if attribute == "clip-path" else "mask"
        if source is None or _local_name(source.tag) != expected:
            raise AnimationError(f"Lottie {attribute} must reference a {expected} element")
        if attribute == "clip-path":
            if any(name not in {"id", "clipPathUnits", "transform", "clip-rule"} for name in source.attrib) or source.get("clipPathUnits", "userSpaceOnUse") != "userSpaceOnUse":
                raise AnimationError("Lottie clip paths require clipPathUnits=userSpaceOnUse")
            content = ET.Element(_tag("g"), {"transform": source.get("transform")} if source.get("transform") else {})
            for child in source:
                if _local_name(child.tag) not in SHAPES:
                    raise AnimationError("Lottie clip paths support basic shapes and paths only")
                rule = child.get("clip-rule", source.get("clip-rule", "nonzero"))
                attributes = {name: value for name, value in child.attrib.items() if name not in PAINT | {"opacity", "clip-rule"}}
                content.append(ET.Element(child.tag, attributes | {"fill": "#ffffff", "fill-rule": rule}))
        else:
            if any(name not in {"id", "maskUnits", "maskContentUnits", "x", "y", "width", "height"} for name in source.attrib) or source.get("maskUnits") != "userSpaceOnUse" or source.get("maskContentUnits", "userSpaceOnUse") != "userSpaceOnUse":
                raise AnimationError("Lottie masks require maskUnits=userSpaceOnUse and maskContentUnits=userSpaceOnUse")
            region = [source.get(name) for name in ("x", "y", "width", "height")]
            if any(value is not None for value in region):
                left, top, region_width, region_height = (_numeric(value) for value in region)
                if left > 0 or top > 0 or left + region_width < width or top + region_height < height:
                    raise AnimationError("Lottie mask regions must cover the whole viewport")
            content = ET.Element(_tag("g"))
            content.extend(list(source))
        wrapper = ET.Element(_tag("g"), {"transform": element.get("transform")} if element.get("transform") else {})
        wrapper.append(content)
        transform_channels = {name: spec for name, spec in tracks.get(element.get("id"), {}).items() if name in TRANSFORM_KEYS}
        return layer(4, expected, shapes=node(wrapper, root_styles if expected == "mask" else {}, transform_channels), td=1)

    root_styles = {name: value for name, value in root.attrib.items() if name in PAINT}
    if not any(_local_name(child.tag) == "image" or LAYERED & set(child.attrib) for child in root):
        layers = [layer(4, "SVG artwork", shapes=node(root, {}))]
    else:
        if any(name not in ATTRIBUTES | {"viewBox", "version", "xmlns"} or name in {"transform", "opacity"} for name in root.attrib):
            raise AnimationError("Lottie layers require a root svg without transform, opacity, or unsupported attributes")
        units: list[list[dict[str, object]]] = []
        run: list[ET.Element] = []
        for child in [*root, None]:
            isolated = child is not None and (_local_name(child.tag) == "image" or bool(LAYERED & set(child.attrib)))
            if child is not None and not isolated:
                run.append(child)
                continue
            shapes = [item for element in reversed(run) for item in node(element, root_styles)]
            if shapes:
                units.append([layer(4, "SVG artwork", shapes=shapes)])
            run = []
            if child is None:
                continue
            attributes = [name for name in ("clip-path", "mask") if name in child.attrib]
            if len(attributes) > 1:
                raise AnimationError("Lottie supports either clip-path or mask on one element")
            bare = ET.Element(child.tag, {name: value for name, value in child.attrib.items() if name not in LAYERED})
            bare.extend(list(child))
            content = image(bare) if _local_name(child.tag) == "image" else [layer(4, child.get("id", "artwork"), shapes=node(bare, root_styles))]
            if attributes:
                content[0]["tt"] = 1 if attributes[0] == "clip-path" else 3
                content.insert(0, matte(child, attributes[0]))
            units.append(content)
        layers = [item for unit in reversed(units) for item in unit]
    if set(tracks) - applied:
        raise AnimationError("Lottie animation targets must be rendered shapes, groups, images, or the root")
    data = {"v": "5.12.2", "fr": fps, "ip": 0, "op": frames, "w": width, "h": height, "nm": "SVG animation", "ddd": 0, "assets": assets, "layers": layers}
    encoded = json.dumps(data, separators=(",", ":"), allow_nan=False)
    return {"lottie": data, "json": encoded, "format": "Lottie JSON", "output_written": False}
