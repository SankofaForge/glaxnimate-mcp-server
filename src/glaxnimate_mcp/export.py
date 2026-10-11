"""Standalone SVG playback exports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from xml.etree import ElementTree as ET

from .authoring import NAME
from .svg import AnimationError, _id_index, _number, _parse_svg, _tag, animate_svg


def _playback_options(playback: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(playback, Mapping):
        raise AnimationError("playback must be an object")
    valid = {"trigger", "direction", "alternate", "iterations", "speed", "hover_out", "click_again", "scroll_threshold", "root_id"}
    if set(playback) - valid:
        raise AnimationError("playback contains unsupported options")
    options: dict[str, object] = {
        "trigger": "load", "direction": 1, "alternate": False, "iterations": 1,
        "speed": 1, "hover_out": "freeze", "click_again": "restart", "scroll_threshold": 25,
        **playback,
    }
    for name, allowed in {
        "trigger": ("load", "hover", "click", "scroll", "programmatic"),
        "hover_out": ("freeze", "reset", "reverse", "none"),
        "click_again": ("freeze", "restart", "reverse", "none"),
    }.items():
        if options[name] not in allowed:
            raise AnimationError(f"{name} must be one of: {', '.join(allowed)}")
    if isinstance(options["direction"], bool) or options["direction"] not in (-1, 1):
        raise AnimationError("direction must be 1 or -1")
    if not isinstance(options["alternate"], bool):
        raise AnimationError("alternate must be a boolean")
    iterations = options["iterations"]
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 0 <= iterations <= 1000:
        raise AnimationError("iterations must be an integer from 0 to 1000")
    options["speed"] = _number(options["speed"], "speed", 0.001, 100)
    options["scroll_threshold"] = _number(options["scroll_threshold"], "scroll_threshold", 1, 100)
    root_id = options.get("root_id")
    if root_id is not None and (not isinstance(root_id, str) or not NAME.fullmatch(root_id)):
        raise AnimationError("root_id must be a valid SVG ID")
    return options


def _prepare_export(svg: str, animations: Sequence[Mapping[str, object]], playback: Mapping[str, object]) -> tuple[ET.Element, dict[str, object], dict[str, object]]:
    options = _playback_options(playback)
    result = animate_svg(svg, animations)
    if any(spec.get("repeat_count", 1) != 1 for spec in animations):
        raise AnimationError("use playback iterations instead of per-channel repeat_count for playback exports")
    options["duration_ms"] = max(float(spec.get("begin_ms", 0)) + float(spec.get("duration_ms", 1000)) for spec in animations)
    root = _parse_svg(str(result["animated_svg"]))
    if any(node.tag == _tag("script") for node in root.iter()):
        raise AnimationError("playback export requires SVG without existing scripts")
    root_id = options.pop("root_id", None) or root.get("id") or "glax-" + hashlib.sha256(svg.encode()).hexdigest()[:16]
    if not isinstance(root_id, str) or not NAME.fullmatch(root_id):
        raise AnimationError("root_id must be a valid SVG ID")
    root.set("id", root_id)
    _id_index(root)
    result["root_id"] = root_id
    return root, result, options


def export_svg(svg: str, animations: Sequence[Mapping[str, object]], playback: Mapping[str, object]) -> dict[str, object]:
    """Export a local JavaScript player that controls a native SVG timeline."""
    root, result, options = _prepare_export(svg, animations, playback)
    root_id = result["root_id"]
    script = files("glaxnimate_mcp").joinpath("player.js").read_text(encoding="utf-8")
    script = script.replace("__ROOT_ID__", json.dumps(root_id)).replace("__OPTIONS__", json.dumps(options))
    ET.SubElement(root, _tag("script"), {"type": "application/ecmascript"}).text = script
    result.update({
        "animated_svg": ET.tostring(root, encoding="unicode"),
        "format": "JavaScript animated SVG", "root_id": root_id,
        "player_api": ["play", "pause", "restart", "reverse", "reset", "seek", "setSpeed", "destroy"],
        "output_written": False,
    })
    return result
