"""Bounded local frame rendering and media encoding."""

from __future__ import annotations

import base64
import math
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from .export import _prepare_export
from .svg import AnimationError, _number, animate_svg

MEDIA_TYPES = {
    "png": "image/png", "gif": "image/gif", "apng": "image/apng",
    "webp": "image/webp", "mp4": "video/mp4", "webm": "video/webm",
    "mov": "video/quicktime", "avi": "video/x-msvideo", "mkv": "video/x-matroska",
    "zip": "application/zip",
}
MAX_MEDIA_BYTES = 20_000_000


def _sample_time(elapsed: float, options: Mapping[str, object]) -> float:
    duration = float(options["duration_ms"])
    elapsed *= float(options["speed"])
    iterations = int(options["iterations"])
    cycle, position = divmod(elapsed, duration)
    if iterations and cycle >= iterations:
        cycle, position = iterations - 1, duration
    direction = int(options["direction"]) * (-1 if options["alternate"] and int(cycle) % 2 else 1)
    return position if direction == 1 else duration - position


def render_media(
    svg: str, animations: Sequence[Mapping[str, object]], format: str,
    width: int = 512, height: int = 512, duration_ms: float = 1000,
    fps: int = 30, time_ms: float = 0, fit: str = "meet", quality: int = 80,
    playback: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Render native SMIL at fixed times. Return encoded bytes without saving a deliverable."""
    if not isinstance(format, str) or format not in MEDIA_TYPES:
        raise AnimationError("format must be png, gif, apng, webp, mp4, webm, mov, avi, mkv, or zip")
    if fit not in ("meet", "slice", "stretch"):
        raise AnimationError("fit must be meet, slice, or stretch")
    if isinstance(quality, bool) or not isinstance(quality, int) or not 1 <= quality <= 100:
        raise AnimationError("quality must be an integer from 1 to 100")
    for name, value, upper in (("width", width, 4096), ("height", height, 4096), ("fps", fps, 60)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
            raise AnimationError(f"{name} must be an integer from 1 to {upper}")
    duration_ms = _number(duration_ms, "duration_ms", 1, 60_000)
    time_ms = _number(time_ms, "time_ms", 0, 600_000)
    frame_count = 1 if format == "png" else math.ceil(duration_ms * fps / 1000)
    if frame_count * width * height > 500_000_000:
        raise AnimationError("render exceeds the 500-million-pixel frame budget")
    if format in ("mp4", "avi", "mkv") and (width % 2 or height % 2):
        raise AnimationError("mp4, avi, and mkv require even width and height")
    animated = animate_svg(svg, animations)["animated_svg"]
    timeline = None
    if playback is not None:
        root, _, timeline = _prepare_export(svg, animations, playback)
        root.set("preserveAspectRatio", "none" if fit == "stretch" else "xMidYMid " + fit)
        from xml.etree import ElementTree as ET
        animated = ET.tostring(root, encoding="unicode")
    ffmpeg = shutil.which("ffmpeg")
    if format not in ("png", "zip") and ffmpeg is None:
        raise AnimationError("FFmpeg is required for animated raster and video exports")
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as error:
        raise AnimationError("install the render extra to enable local media exports") from error
    try:
        with tempfile.TemporaryDirectory(prefix="glaxnimate-render-") as directory:
            scratch = Path(directory)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, executable_path=os.environ.get("GLAXNIMATE_CHROMIUM_PATH"),
                )
                try:
                    context = browser.new_context(viewport={"width": width, "height": height}, java_script_enabled=False)
                    context.route("**/*", lambda route: route.abort())
                    page = context.new_page()
                    page.set_default_timeout(30_000)
                    page.set_content(
                        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'
                        '<style>html,body{margin:0;width:100%;height:100%;overflow:hidden}svg{width:100%;height:100%}</style>'
                        + str(animated), wait_until="load",
                    )
                    page.evaluate("""fit => document.querySelector('svg').setAttribute('preserveAspectRatio', fit === 'stretch' ? 'none' : 'xMidYMid ' + fit)""", fit)
                    for index in range(frame_count):
                        position = time_ms + index * 1000 / fps
                        if timeline is not None:
                            position = _sample_time(position, timeline)
                        page.evaluate("""time => {
                            const svg = document.querySelector('svg');
                            svg.pauseAnimations(); svg.setCurrentTime(time / 1000);
                        }""", position)
                        page.screenshot(path=str(scratch / f"frame-{index:05d}.png"), omit_background=True, animations="allow")
                finally:
                    browser.close()
            output = scratch / "frame-00000.png"
            if format == "zip":
                output = scratch / "frames.zip"
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for index in range(frame_count):
                        name = f"frame-{index:05d}.png"
                        archive.write(scratch / name, name)
            elif format != "png":
                output = scratch / f"animation.{format}"
                codecs = {
                    "mp4": ["-c:v", "libx264", "-crf", str(round(51 * (100 - quality) / 100)), "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
                    "avi": ["-c:v", "libx264", "-crf", str(round(51 * (100 - quality) / 100)), "-pix_fmt", "yuv420p"],
                    "mkv": ["-c:v", "mpeg4", "-q:v", str(max(1, round(31 * (100 - quality) / 100))), "-pix_fmt", "yuv420p"],
                    "mov": ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le"],
                    "webm": ["-c:v", "libvpx-vp9", "-crf", str(round(63 * (100 - quality) / 100)), "-b:v", "0", "-pix_fmt", "yuva420p"],
                    "gif": ["-filter_complex", "[0:v]split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse", "-loop", "0"],
                    "apng": ["-f", "apng", "-plays", "0"],
                    "webp": ["-c:v", "libwebp_anim", "-quality", str(quality), "-loop", "0"],
                }
                subprocess.run(
                    [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
                     "-i", str(scratch / "frame-%05d.png"), *codecs[format], str(output)],
                    check=True, capture_output=True, timeout=120,
                )
            if not 1 <= output.stat().st_size <= MAX_MEDIA_BYTES:
                raise AnimationError("encoded media must contain 1 to 20 million bytes")
            data = output.read_bytes()
    except (OSError, subprocess.SubprocessError, PlaywrightError) as error:
        raise AnimationError("local media export failed") from error
    return {"format": format, "mime_type": MEDIA_TYPES[format], "data_base64": base64.b64encode(data).decode("ascii"),
            "byte_count": len(data), "frame_count": frame_count, "width": width, "height": height,
            "fps": fps, "output_written": False}
