"""Portable, editable project state for agent workflows."""

from __future__ import annotations

import json
from bisect import bisect_left
from copy import deepcopy
from collections.abc import Mapping, Sequence

from .authoring import NAME, edit_svg
from .export import _playback_options
from .svg import AnimationError, _animation_element, _number, _values, inspect_svg


def _validate(project: object) -> dict[str, object]:
    if not isinstance(project, Mapping) or set(project) != {"version", "svg", "tracks", "duration_ms", "fps", "playback"} or type(project.get("version")) is not int or project.get("version") != 1:
        raise AnimationError("project must use the version 1 project schema")
    result = deepcopy(dict(project))
    inspection = inspect_svg(result["svg"])
    result["duration_ms"] = _number(result["duration_ms"], "duration_ms", 1, 600_000)
    result["fps"] = _number(result["fps"], "fps", 1, 120)
    _playback_options(result["playback"])
    tracks = result["tracks"]
    if not isinstance(tracks, list) or len(tracks) > 100:
        raise AnimationError("tracks must be an array of at most 100 objects")
    ids: set[str] = set()
    for track in tracks:
        if not isinstance(track, Mapping) or set(track) != {"id", "animation"}:
            raise AnimationError("each track needs id and animation")
        track_id = track["id"]
        if not isinstance(track_id, str) or not NAME.fullmatch(track_id) or track_id in ids:
            raise AnimationError("track IDs must be valid and unique")
        ids.add(track_id)
        spec = track["animation"]
        if not isinstance(spec, Mapping):
            raise AnimationError("track animation must be an object")
        target, _ = _animation_element(spec)
        if target not in inspection["animation_targets"]:
            raise AnimationError("track target does not exist")
        if float(spec.get("begin_ms", 0)) + float(spec.get("duration_ms", 1000)) > result["duration_ms"]:
            raise AnimationError("project duration_ms must contain every track")
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise AnimationError("project values must use finite JSON data") from error
    return result


def _result(project: object) -> dict[str, object]:
    validated = _validate(project)
    encoded = json.dumps(validated, allow_nan=False, separators=(",", ":"))
    return {"project": validated, "json": encoded, "output_written": False}


def create_project(svg: str, duration_ms: float = 1000, fps: float = 30) -> dict[str, object]:
    """Create versioned project data. The caller stores and restores project snapshots."""
    return _result({"version": 1, "svg": svg, "tracks": [], "duration_ms": duration_ms, "fps": fps, "playback": {}})


def _edit_keyframe(animation: dict[str, object], operation: Mapping[str, object]) -> None:
    values = list(animation["values"])
    times = list(animation["key_times"]) if animation.get("key_times") is not None else [index / (len(values) - 1) for index in range(len(values))]
    action = operation["action"]
    if action == "set_interval_easing":
        index = operation.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(values) - 1:
            raise AnimationError("interval index must identify an existing keyframe interval")
        if "easing" in animation:
            raise AnimationError("interval easing requires a track without global easing")
        curves = deepcopy(animation.get("key_splines", [[0, 0, 1, 1] for _ in range(len(values) - 1)]))
        curves[index] = deepcopy(operation.get("curve"))
        animation.update({"calc_mode": "spline", "key_splines": curves})
        return
    time = _number(operation.get("time"), "keyframe time", 0, 1)
    index = bisect_left(times, time)
    exists = index < len(times) and times[index] == time
    if action == "remove_keyframe":
        if not exists or time in (0, 1):
            raise AnimationError("remove_keyframe requires an existing interior keyframe")
    else:
        value = operation.get("value")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise AnimationError("keyframe value must be a string or number")
        _values([value, value])
        if exists:
            values[index] = value
            animation.update({"values": values, "key_times": times})
            return
    if animation.get("calc_mode") == "spline" or "easing" in animation:
        raise AnimationError("insert or remove on an eased track requires update_track with complete values and easing")
    if action == "remove_keyframe":
        del values[index]
        del times[index]
    else:
        values.insert(index, value)
        times.insert(index, time)
    animation.update({"values": values, "key_times": times})


def edit_project(project: Mapping[str, object], operations: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Apply a transaction to artwork, tracks, and playback settings."""
    result = _validate(project)
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        raise AnimationError("operations must contain 1 to 100 objects")
    for operation in operations:
        if not isinstance(operation, Mapping):
            raise AnimationError("each operation must be an object")
        action = operation.get("action")
        if action == "artwork":
            result["svg"] = edit_svg(result["svg"], operation.get("operations"))["svg"]
            continue
        if action == "settings":
            values = operation.get("values")
            if not isinstance(values, Mapping) or set(values) - {"fps", "duration_ms", "playback"}:
                raise AnimationError("settings values must contain fps, duration_ms, or playback")
            result.update(deepcopy(values))
            continue
        if action == "add_track":
            result["tracks"].append({"id": operation.get("id"), "animation": deepcopy(operation.get("animation"))})
            continue
        track = next((track for track in result["tracks"] if track["id"] == operation.get("id")), None)
        if track is None:
            raise AnimationError("track id does not exist")
        if action in ("set_keyframe", "remove_keyframe", "set_interval_easing"):
            _edit_keyframe(track["animation"], operation)
            continue
        if action == "remove_track":
            result["tracks"].remove(track)
            continue
        if action == "update_track":
            patch = operation.get("animation")
            if not isinstance(patch, Mapping):
                raise AnimationError("animation update must be an object")
            track["animation"].update(deepcopy(patch))
            continue
        if action == "duplicate_track":
            animation = deepcopy(track["animation"])
            if "target_id" in operation:
                animation["target_id"] = operation["target_id"]
            result["tracks"].append({"id": operation.get("new_id"), "animation": animation})
            continue
        raise AnimationError("project action is unsupported")
    return _result(result)


def inspect_project(project: Mapping[str, object]) -> dict[str, object]:
    """Validate saved project state and expose its artwork and animation tracks."""
    result = _validate(project)
    return {**inspect_svg(result["svg"]), "tracks": result["tracks"], "duration_ms": result["duration_ms"], "fps": result["fps"], "playback": result["playback"], "output_written": False}
