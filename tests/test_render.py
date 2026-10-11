from __future__ import annotations

import base64
import builtins
import io
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from glaxnimate_mcp.render import _sample_time, render_media
from glaxnimate_mcp.svg import AnimationError

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle id="dot" r="5"/></svg>'
ANIMATIONS = [{"target_id": "dot", "property": "cx", "values": [0, 10]}]


class RenderTests(unittest.TestCase):
    def test_validate_render_options(self) -> None:
        for options in [
            {"format": "bad"}, {"format": []}, {"width": True}, {"width": 0}, {"height": 1.5},
            {"fps": 61}, {"duration_ms": 0}, {"time_ms": -1},
            {"format": "gif", "width": 4096, "height": 4096, "duration_ms": 60000},
            {"format": "mp4", "width": 511},
            {"fit": "bad"}, {"quality": True}, {"quality": 0}, {"quality": 101},
        ]:
            with self.subTest(options=options), self.assertRaises(AnimationError):
                render_media(SVG, ANIMATIONS, **({"format": "png"} | options))

    def test_required_dependencies(self) -> None:
        with patch("glaxnimate_mcp.render.shutil.which", return_value=None):
            with self.assertRaisesRegex(AnimationError, "FFmpeg"):
                render_media(SVG, ANIMATIONS, "gif")
        original = builtins.__import__

        def import_without_playwright(name, *args, **kwargs):
            if name == "playwright.sync_api":
                raise ImportError("not installed")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_playwright):
            with self.assertRaisesRegex(AnimationError, "render extra"):
                render_media(SVG, ANIMATIONS, "png")

    def test_frame_times_encoding_and_cleanup(self) -> None:
        browser = MagicMock()
        page = browser.new_context.return_value.new_page.return_value
        rendered: list[Path] = []

        def screenshot(**options):
            path = Path(options["path"])
            path.write_bytes(b"png frame")
            rendered.append(path)

        def encode(command, **options):
            Path(command[-1]).write_bytes(b"encoded frames")

        page.screenshot.side_effect = screenshot
        with patch("playwright.sync_api.sync_playwright") as playwright, patch("glaxnimate_mcp.render.shutil.which", return_value="/bin/ffmpeg"), patch("glaxnimate_mcp.render.subprocess.run", side_effect=encode) as run:
            playwright.return_value.__enter__.return_value.chromium.launch.return_value = browser
            for format in ("png", "gif", "apng", "webp", "mp4", "webm", "mov", "avi", "mkv", "zip"):
                with self.subTest(format=format):
                    page.evaluate.reset_mock()
                    result = render_media(SVG, ANIMATIONS, format, 32, 32, 200, 10, 100)
                    expected = [100] if format == "png" else [100, 200]
                    self.assertEqual([call.args[1] for call in page.evaluate.call_args_list][1:], expected)
                    self.assertEqual(result["frame_count"], len(expected))
                    self.assertFalse(result["output_written"])
                    data = b"png frame" if format == "png" else b"encoded frames"
                    actual = base64.b64decode(result["data_base64"])
                    if format == "zip":
                        with zipfile.ZipFile(io.BytesIO(actual)) as archive:
                            self.assertEqual(archive.namelist(), ["frame-00000.png", "frame-00001.png"])
                            self.assertEqual(archive.read("frame-00001.png"), b"png frame")
                    else:
                        self.assertEqual(actual, data)
                    self.assertEqual(result["byte_count"], len(actual))
            self.assertEqual(run.call_count, 8)
            browser.new_context.assert_called_with(viewport={"width": 32, "height": 32}, java_script_enabled=False)
            route = MagicMock()
            browser.new_context.return_value.route.call_args.args[1](route)
            route.abort.assert_called_once()
            self.assertTrue(all(not path.exists() for path in rendered))
            self.assertEqual(browser.close.call_count, 10)

    def test_global_playback_frame_sampling(self) -> None:
        options = {"duration_ms": 1000, "speed": 2, "direction": -1, "alternate": True, "iterations": 2}
        self.assertEqual([_sample_time(time, options) for time in (0, 250, 500, 750, 1000, 1500)], [1000, 500, 0, 500, 1000, 1000])
        self.assertEqual(_sample_time(1500, options | {"alternate": False}), 0)
        self.assertEqual(_sample_time(1750, options | {"iterations": 0, "direction": 1}), 500)
        browser = MagicMock()
        page = browser.new_context.return_value.new_page.return_value
        page.screenshot.side_effect = lambda **options: Path(options["path"]).write_bytes(b"frame")
        with patch("playwright.sync_api.sync_playwright") as playwright:
            playwright.return_value.__enter__.return_value.chromium.launch.return_value = browser
            for fit in ("meet", "slice", "stretch"):
                with self.subTest(fit=fit):
                    render_media(SVG, ANIMATIONS, "png", time_ms=250, fit=fit, playback={"direction": -1, "speed": 2})
                    self.assertEqual(page.evaluate.call_args.args[1], 500)
                    content = page.set_content.call_args.args[0]
                    self.assertIn('preserveAspectRatio="' + ("none" if fit == "stretch" else "xMidYMid " + fit) + '"', content)

    def test_renderer_and_encoder_failures(self) -> None:
        from playwright.sync_api import Error

        browser = MagicMock()
        page = browser.new_context.return_value.new_page.return_value
        page.screenshot.side_effect = lambda **options: Path(options["path"]).write_bytes(b"data")
        with patch("playwright.sync_api.sync_playwright") as playwright, patch("glaxnimate_mcp.render.shutil.which", return_value="/bin/ffmpeg"):
            playwright.return_value.__enter__.return_value.chromium.launch.return_value = browser
            with patch("glaxnimate_mcp.render.MAX_MEDIA_BYTES", 1):
                with self.assertRaisesRegex(AnimationError, "20 million"):
                    render_media(SVG, ANIMATIONS, "png")
            with patch("glaxnimate_mcp.render.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)):
                with self.assertRaisesRegex(AnimationError, "export failed"):
                    render_media(SVG, ANIMATIONS, "gif")
            page.screenshot.side_effect = OSError("disk full")
            with self.assertRaisesRegex(AnimationError, "export failed"):
                render_media(SVG, ANIMATIONS, "png")
            page.screenshot.side_effect = Error("browser unavailable")
            with self.assertRaisesRegex(AnimationError, "export failed"):
                render_media(SVG, ANIMATIONS, "png")
