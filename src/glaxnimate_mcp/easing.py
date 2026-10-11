"""Numeric easing conversion for portable SVG and Lottie timelines."""

from __future__ import annotations

import math
from collections.abc import Mapping

from .svg import AnimationError, MAX_KEYFRAMES, _key_times, _number, _values

PRESETS = {"linear": [0, 0, 1, 1], "ease": [0.25, 0.1, 0.25, 1], "ease-in": [0.42, 0, 1, 1], "ease-out": [0, 0, 0.58, 1], "ease-in-out": [0.42, 0, 0.58, 1], "back-in": [0.36, 0, 0.66, -0.56], "back-out": [0.34, 1.56, 0.64, 1]}


def _cubic(progress: float, curve: list[float]) -> float:
    def coordinate(time: float, first: float, second: float) -> float:
        return 3 * (1 - time) ** 2 * time * first + 3 * (1 - time) * time ** 2 * second + time ** 3

    low, high = 0.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if coordinate(middle, curve[0], curve[2]) < progress:
            low = middle
        else:
            high = middle
    return coordinate((low + high) / 2, curve[1], curve[3])


def bake_animation(spec: Mapping[str, object]) -> dict[str, object]:
    """Sample continuous easing. Encode step easing as exact discrete keyframes."""
    easing = spec["easing"]
    if not isinstance(easing, Mapping) or set(easing) - {"type", "name", "curve", "samples", "steps", "jump"}:
        raise AnimationError("easing must be an object with supported fields")
    if "key_splines" in spec or spec.get("calc_mode", "linear") != "linear":
        raise AnimationError("easing requires calc_mode=linear and no key_splines")
    raw = _values(spec.get("values"))
    times = [float(time) for time in _key_times(spec.get("key_times"), len(raw)).split(";")]
    values: list[list[float]] = []
    for value in raw:
        try:
            numbers = [float(part) for part in value.replace(",", " ").split()]
        except ValueError as error:
            raise AnimationError("easing currently supports numeric values and transforms without units") from error
        values.append([_number(number, "easing value", -1e9, 1e9) for number in numbers])
    if any(len(value) != len(values[0]) for value in values):
        raise AnimationError("easing values must have equal coordinate counts")
    kind = easing.get("type", "preset")
    curve: list[float] = []
    jump = easing.get("jump", "end")
    samples = easing.get("samples", 60)
    if isinstance(samples, bool) or not isinstance(samples, int) or not 2 <= samples <= 511:
        raise AnimationError("easing samples must be an integer from 2 to 511")
    count = min(samples, (MAX_KEYFRAMES - 1) // (len(values) - 1))
    if kind == "steps":
        count = easing.get("steps")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100 or jump not in ("start", "end", "none", "both") or (jump == "none" and count < 2):
            raise AnimationError("steps requires 1 to 100 steps and jump=start, end, none, or both; none requires at least 2 steps")
    elif kind in ("preset", "cubic"):
        name = easing.get("name", "linear")
        raw_curve = PRESETS.get(name) if kind == "preset" and isinstance(name, str) else easing.get("curve") if kind == "cubic" else None
        if not isinstance(raw_curve, (list, tuple)) or len(raw_curve) != 4:
            raise AnimationError("easing requires a known preset or four cubic coordinates")
        curve = [_number(value, "easing coordinate", 0 if index % 2 == 0 else -10, 1 if index % 2 == 0 else 10) for index, value in enumerate(raw_curve)]
    elif kind not in ("bounce-out", "elastic-out"):
        raise AnimationError("easing type must be preset, cubic, steps, bounce-out, or elastic-out")
    if count * (len(values) - 1) + 1 > MAX_KEYFRAMES:
        raise AnimationError("easing exceeds the keyframe limit")

    def progress(time: float) -> float:
        if kind == "steps":
            step = round(time * count)
            divisor = count + (1 if jump == "both" else -1 if jump == "none" else 0)
            return min(1, (step + (1 if jump in ("start", "both") else 0)) / divisor)
        if time in (0, 1):
            return time
        if kind == "bounce-out":
            if time < 1 / 2.75:
                return 7.5625 * time * time
            if time < 2 / 2.75:
                return 7.5625 * (time - 1.5 / 2.75) ** 2 + 0.75
            if time < 2.5 / 2.75:
                return 7.5625 * (time - 2.25 / 2.75) ** 2 + 0.9375
            return 7.5625 * (time - 2.625 / 2.75) ** 2 + 0.984375
        if kind == "elastic-out":
            return 2 ** (-10 * time) * math.sin((time * 10 - 0.75) * 2 * math.pi / 3) + 1
        return _cubic(time, curve)

    baked_values: list[str] = []
    baked_times: list[float] = []
    for index, (start, end) in enumerate(zip(values, values[1:])):
        for step in range(count + 1):
            fraction = step / count
            value = " ".join(f"{first + (last - first) * progress(fraction):.12g}" for first, last in zip(start, end))
            time = times[index] + (times[index + 1] - times[index]) * fraction
            if baked_times and step == 0:
                baked_values[-1] = value
                continue
            baked_values.append(value)
            baked_times.append(time)
    result = {key: value for key, value in spec.items() if key != "easing"}
    result.update({"values": baked_values, "key_times": baked_times, "calc_mode": "discrete" if kind == "steps" else "linear"})
    if spec.get("property") == "motion-path":
        if len(values[0]) != 1:
            raise AnimationError("motion-path easing requires one numeric progress value per keyframe")
        result["values"] = [float(value) for value in baked_values]
    return result
