"""Render generated vector Lottie with the upstream SVG player."""

from __future__ import annotations

import argparse
import base64
import struct
import zlib

from playwright.sync_api import sync_playwright

from glaxnimate_mcp.lottie import export_lottie
from glaxnimate_mcp.svg import animate_svg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    parser.add_argument("--player-script", required=True)
    args = parser.parse_args()
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect id="box" width="20" height="20" fill="red"/></svg>'
    result = export_lottie(svg, [
        {"target_id": "box", "property": "translate", "values": ["0 0", "80 0"]},
        {"target_id": "box", "property": "fill", "values": ["red", "blue"]},
    ], duration_ms=1100)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.executable, headless=True)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content('<div id="art" style="width:100px;height:100px"></div>')
        page.add_script_tag(path=args.player_script)
        page.evaluate("""data => {
            window.player = lottie.loadAnimation({container:document.getElementById('art'),renderer:'svg',loop:false,autoplay:false,animationData:data});
            window.loaded = false;
            window.player.addEventListener('DOMLoaded', () => { window.loaded = true; });
        }""", result["lottie"])
        page.wait_for_function("window.loaded")
        sample = """frame => {
            player.goToAndStop(frame,true);
            const path = document.querySelector('#art path');
            return {x:path.getCTM().e,fill:getComputedStyle(path).fill,width:path.getBBox().width};
        }"""
        start = page.evaluate(sample, 0)
        middle = page.evaluate(sample, 15)
        end = page.evaluate(sample, 30)
        assert start == {"x": 0, "fill": "rgb(255, 0, 0)", "width": 20}, start
        assert middle == {"x": 40, "fill": "rgb(127, 0, 127)", "width": 20}, middle
        assert end == {"x": 80, "fill": "rgb(0, 0, 255)", "width": 20}, end
        for static in (False, True):
            pivot_svg = svg.replace('fill="red"', 'fill="red" transform="rotate(90 10 20)"') if static else svg
            tracks = [] if static else [{"target_id": "box", "property": "rotate", "values": ["0 10 20", "90 30 40"]}]
            reference = pivot_svg if static else animate_svg(pivot_svg, tracks)["animated_svg"]
            vector = export_lottie(pivot_svg, tracks, duration_ms=1100)["lottie"]
            page.evaluate("player.destroy()")
            page.set_content('<div id="art" style="width:100px;height:100px"></div><div id="reference">' + reference + '</div>')
            page.evaluate("""data => {
                window.loaded = false;
                window.player = lottie.loadAnimation({container:document.getElementById('art'),renderer:'svg',loop:false,autoplay:false,animationData:data});
                player.addEventListener('DOMLoaded', () => { window.loaded = true; });
            }""", vector)
            page.wait_for_function("window.loaded")
            for frame in (0, 15, 30):
                matrices = page.evaluate("""frame => {
                    player.goToAndStop(frame,true);
                    const svg = document.querySelector('#reference svg');
                    svg.pauseAnimations(); svg.setCurrentTime(frame/30);
                    const actual = document.querySelector('#art path').getCTM();
                    const expected = document.querySelector('#reference rect').getCTM();
                    return ['a','b','c','d','e','f'].map(key => [actual[key],expected[key]]);
                }""", frame)
                assert all(abs(actual - expected) < 0.001 for actual, expected in matrices), (static, frame, matrices)
        moving = [{"target_id": "clipped", "property": "translate", "values": ["0 0", "30 10"]}]
        cases = [(name, reference, [], 0, reference) for name, reference in FIXTURES.items()]
        results: dict[str, int] = {}
        cases += [(f"moving clip {frame}", FIXTURES["clip"], moving, frame, FIXTURES["clip"].replace("translate(5 0)", f"translate({frame} {frame / 3:g})")) for frame in (15, 30)]
        for name, source, tracks, frame, reference in cases:
            vector = export_lottie(source, tracks, duration_ms=1100)["lottie"]
            page.evaluate("player.destroy()")
            page.set_content('<div id="art" style="width:100px;height:100px"></div>')
            page.evaluate(LOAD, vector)
            page.wait_for_function("window.loaded")
            page.evaluate("frame => player.goToAndStop(frame,true)", frame)
            actual = page.evaluate(RASTER, page.evaluate("new XMLSerializer().serializeToString(document.querySelector('#art svg'))"))
            expected = page.evaluate(RASTER, reference)
            results[name] = _interior_differences(actual, expected)
        print(results)
        assert not any(results.values()), results
        assert not errors, errors
        browser.close()
    print("Lottie SVG player geometry, transform, color, pivot, gradient, matte, and image samples passed")


def _interior_differences(actual: list[int], expected: list[int], size: int = 100, tolerance: int = 24) -> int:
    """Count mismatched pixels, ignoring antialiased edges in the reference raster."""
    def pixel(data: list[int], x: int, y: int) -> list[int]:
        return data[(y * size + x) * 4:(y * size + x) * 4 + 4]

    def distance(first: list[int], second: list[int]) -> int:
        return max(abs(a - b) for a, b in zip(first, second))

    count = 0
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            center = pixel(expected, x, y)
            edge = any(distance(center, pixel(expected, x + dx, y + dy)) > tolerance for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if not edge and distance(center, pixel(actual, x, y)) > tolerance:
                count += 1
    return count


def _png(width: int, height: int, pixels: list[tuple[int, int, int]]) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + bytes(channel for pixel in pixels[row * width:(row + 1) * width] for channel in pixel) for row in range(height))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _document(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">{body}</svg>'


FIXTURES = {
    "linear": _document('<defs><linearGradient id="g"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff" stop-opacity="0.5"/></linearGradient></defs><rect id="a" x="10" y="10" width="80" height="40" fill="url(#g)"/>'),
    "radial": _document('<defs><radialGradient id="g" gradientUnits="userSpaceOnUse" cx="50" cy="50" r="40" fx="62" fy="40"><stop offset="0.1" stop-color="#ffff00"/><stop offset="1" stop-color="#008000"/></radialGradient></defs><circle id="a" cx="50" cy="50" r="40" fill="url(#g)"/>'),
    "stroke": _document('<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000000"/><stop offset="1" stop-color="#ff0000"/></linearGradient></defs><rect id="a" x="20" y="20" width="60" height="60" fill="none" stroke="url(#g)" stroke-width="10"/>'),
    "clip": _document('<defs><clipPath id="c"><circle cx="50" cy="50" r="30"/></clipPath></defs><rect id="back" width="100" height="100" fill="#ffff00"/><rect id="clipped" x="10" y="10" width="80" height="80" fill="#0000ff" transform="translate(5 0)" clip-path="url(#c)"/>'),
    "mask": _document('<defs><mask id="m" maskUnits="userSpaceOnUse"><rect width="100" height="50" fill="#ffffff"/><rect y="50" width="100" height="50" fill="#808080"/></mask></defs><rect id="masked" width="100" height="100" fill="#ff0000" mask="url(#m)"/>'),
    "image": _document(f'<rect id="back" width="100" height="100" fill="#ffffff"/><image id="photo" x="10" y="20" width="80" height="60" href="{_png(2, 1, [(255, 0, 0), (0, 0, 255)])}"/>'),
}
LOAD = """data => {
    window.loaded = false;
    window.player = lottie.loadAnimation({container:document.getElementById('art'),renderer:'svg',loop:false,autoplay:false,animationData:data});
    player.addEventListener('DOMLoaded', () => { window.loaded = true; });
}"""
RASTER = """async markup => {
    const image = new Image();
    image.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(markup)));
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = 100; canvas.height = 100;
    const context = canvas.getContext('2d');
    context.drawImage(image, 0, 0, 100, 100);
    return Array.from(context.getImageData(0, 0, 100, 100).data);
}"""


if __name__ == "__main__":
    main()
