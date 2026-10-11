"""Verify local exports with real Chromium and FFmpeg."""

from __future__ import annotations

import base64
import json
import io
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from glaxnimate_mcp.render import render_media


def main() -> None:
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle id="dot" cx="16" cy="32" r="8" fill="red"/></svg>'
    animations = [{"target_id": "dot", "property": "cx", "values": [16, 48], "duration_ms": 300}]
    first = render_media(svg, animations, "png", 64, 64, 300, 10, 0)
    middle = render_media(svg, animations, "png", 64, 64, 300, 10, 150)
    assert first["data_base64"] != middle["data_base64"], "rendered animation must change position"
    reverse = render_media(svg, animations, "png", 64, 64, 300, 10, 150, playback={"direction": -1})
    assert reverse["data_base64"] == middle["data_base64"], "reverse midpoint must match forward midpoint"
    with tempfile.TemporaryDirectory(prefix="glaxnimate-media-check-") as directory:
        for format in ("png", "gif", "apng", "webp", "mp4", "webm", "mov", "avi", "mkv", "zip"):
            result = render_media(svg, animations, format, 64, 64, 300, 10)
            data = base64.b64decode(result["data_base64"], validate=True)
            assert len(data) == result["byte_count"] > 0
            if format == "zip":
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert archive.namelist() == [f"frame-{index:05d}.png" for index in range(3)]
                    assert archive.read("frame-00000.png") != archive.read("frame-00002.png")
                continue
            if format == "webp":
                assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
                assert b"ANIM" in data and data.count(b"ANMF") == 3
                continue
            path = Path(directory) / f"sample.{format}"
            path.write_bytes(data)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            assert (stream["width"], stream["height"]) == (64, 64), stream
            assert int(stream["nb_read_frames"]) == (1 if format == "png" else 3), stream
    print("Ten raster/video/sequence formats and reverse sampling passed")


if __name__ == "__main__":
    main()
