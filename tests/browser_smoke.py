"""Check exported SMIL values in a browser at fixed timeline positions."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright

from glaxnimate_mcp.svg import animate_svg
from glaxnimate_mcp.export import export_svg
from glaxnimate_mcp.css import export_css
from glaxnimate_mcp.static import export_static


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="box" width="20" height="20" fill="red"/></svg>'
    result = animate_svg(svg, [
        {"target_id": "box", "property": "x", "values": [0, 100], "duration_ms": 1000,
         "calc_mode": "spline", "key_splines": [[0.42, 0, 1, 1]], "repeat_count": "indefinite"},
        {"target_id": "box", "property": "fill", "values": ["red", "blue"], "duration_ms": 1000},
    ])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.executable, headless=True)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(result["animated_svg"])
        sample = """time => {
            const svg = document.querySelector('svg');
            svg.pauseAnimations();
            svg.setCurrentTime(time);
            const box = document.getElementById('box');
            return {x: box.x.animVal.value, fill: getComputedStyle(box).fill};
        }"""
        start = page.evaluate(sample, 0)
        middle = page.evaluate(sample, 0.5)
        repeated = page.evaluate(sample, 1.5)
        assert start["x"] == 0, start
        assert 30 < middle["x"] < 33, middle
        assert middle["fill"] == "rgb(128, 0, 128)", middle
        assert abs(repeated["x"] - middle["x"]) < 0.01, repeated
        assert repeated["fill"] == "rgb(0, 0, 255)", repeated
        page.set_content(result["reduced_motion_svg"])
        assert page.locator("animate, animateTransform").count() == 0
        motion = animate_svg(svg, [{"target_id": "box", "property": "motion-path", "values": [0, 1],
                                  "motion_path": "M0 0 L100 0", "motion_rotate": 0}])
        page.set_content(motion["animated_svg"])
        x = page.evaluate("""() => {
            const svg = document.querySelector('svg'); svg.pauseAnimations(); svg.setCurrentTime(0.5);
            return document.getElementById('box').getCTM().e;
        }""")
        assert abs(x - 50) < 0.01, x
        motion = animate_svg(svg, [{"target_id": "box", "property": "motion-path", "values": [0, 1],
                                  "motion_path": "M0 0 L100 0", "motion_rotate": 0,
                                  "easing": {"name": "ease-out"}}])
        page.set_content(motion["animated_svg"])
        x = page.evaluate("""() => {
            const svg = document.querySelector('svg'); svg.pauseAnimations(); svg.setCurrentTime(0.5);
            return document.getElementById('box').getCTM().e;
        }""")
        assert 68 < x < 69, x
        for jump, expected in (("end", 25), ("start", 50), ("none", 100 / 3), ("both", 40)):
            stepped = animate_svg(svg, [{"target_id": "box", "property": "x", "values": [0, 100], "easing": {"type": "steps", "steps": 4, "jump": jump}}])
            page.set_content(stepped["animated_svg"])
            actual = page.evaluate(sample, 0.3)["x"]
            assert abs(actual - expected) < 0.001, (jump, actual)
        overshoot = animate_svg(svg, [{"target_id": "box", "property": "x", "values": [0, 100], "easing": {"name": "back-out"}}])
        page.set_content(overshoot["animated_svg"])
        assert page.evaluate(sample, 0.6)["x"] > 100
        animation = [{"target_id": "box", "property": "x", "values": [0, 100], "duration_ms": 1000}]
        css = export_css(svg, animation, {})
        page.set_content(css["animated_svg"])
        css_x = page.evaluate("""() => {
            const animation = document.getElementById('box').getAnimations()[0];
            animation.pause(); animation.currentTime = 500;
            return parseFloat(getComputedStyle(document.getElementById('box')).x);
        }""")
        assert css_x == 50, css_x
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("document.getElementById('box').getAnimations().length === 0")
        assert page.evaluate("getComputedStyle(document.getElementById('box')).x") == "0px"
        page.emulate_media(reduced_motion="no-preference")
        exported = export_svg(svg, animation, {"trigger": "programmatic", "root_id": "player"})
        page.set_content(exported["animated_svg"])
        state = page.evaluate("""() => {
            const svg = document.getElementById('player'); const player = svg.glaxnimatePlayer;
            player.seek(500);
            return {x: document.getElementById('box').x.animVal.value, playing: player.isPlaying, time: player.currentTime};
        }""")
        assert state == {"x": 50, "playing": False, "time": 500}, state
        page.evaluate("document.getElementById('player').glaxnimatePlayer.reverse()")
        page.wait_for_function("document.getElementById('player').glaxnimatePlayer.currentTime < 450")
        page.evaluate("document.getElementById('player').glaxnimatePlayer.pause()")
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("document.querySelectorAll('animate').length === 0")
        assert page.evaluate("document.getElementById('box').x.animVal.value") == 0
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_function("document.querySelectorAll('animate').length === 1")
        page.evaluate("document.getElementById('player').glaxnimatePlayer.destroy()")
        page.evaluate("""() => {
            let callback;
            window.requestAnimationFrame = fn => { callback = fn; return 1; };
            window.cancelAnimationFrame = () => { callback = null; };
            window.advance = time => { const fn = callback; callback = null; if (fn) fn(time); };
        }""")
        for direction in (1, -1):
            for alternate in (False, True):
                for iterations in (0, 1, 2, 3):
                    fixture = export_svg(svg, animation, {
                        "trigger": "programmatic", "root_id": "player", "direction": direction,
                        "alternate": alternate, "iterations": iterations,
                    })
                    page.set_content(fixture["animated_svg"])
                    state = page.evaluate("""() => {
                        const player = document.getElementById('player').glaxnimatePlayer;
                        player.play(); window.advance(0); window.advance(3500);
                        return {time:player.currentTime, playing:player.isPlaying};
                    }""")
                    if iterations == 0:
                        expected = 500
                    else:
                        final_direction = direction * (-1 if alternate and iterations % 2 == 0 else 1)
                        expected = 1000 if final_direction == 1 else 0
                    assert state == {"time": expected, "playing": iterations == 0}, (direction, alternate, iterations, state)
                    page.evaluate("document.getElementById('player').glaxnimatePlayer.destroy()")
        fixture = export_svg(svg, animation, {"trigger": "hover", "hover_out": "reverse", "root_id": "player"})
        page.set_content(fixture["animated_svg"])
        state = page.evaluate("""() => {
            const svg = document.getElementById('player'); const player = svg.glaxnimatePlayer;
            svg.dispatchEvent(new Event('mouseenter')); window.advance(0); window.advance(400);
            svg.dispatchEvent(new Event('mouseleave')); window.advance(400); window.advance(600);
            return player.currentTime;
        }""")
        assert state == 200, state
        page.evaluate("document.getElementById('player').glaxnimatePlayer.destroy()")
        artwork = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">'
                   '<rect id="box" width="20" height="20" fill="red"/><rect id="dot" width="5" height="5" transform="scale(2)"/>'
                   '<rect id="mover" width="4" height="4"/></svg>')
        tracks = [
            {"target_id": "box", "property": "x", "values": [0, 100], "calc_mode": "spline", "key_splines": [[0.42, 0, 0.58, 1]], "repeat_count": 2},
            {"target_id": "box", "property": "fill", "values": ["red", "#00f", "rgb(0, 255, 0)"]},
            {"target_id": "box", "property": "opacity", "values": [1, 0], "begin_ms": 300, "duration_ms": 500, "fill_mode": "remove"},
            {"target_id": "dot", "property": "rotate", "values": ["0 10 10", "180 30 10"]},
            {"target_id": "dot", "property": "translate", "values": ["0 0", "40 20"], "additive": "sum"},
            {"target_id": "mover", "property": "motion-path", "values": [0, 0.7, 1], "motion_path": "M10 10 C60 100 140 -50 190 120", "motion_rotate": "auto"},
        ]
        read = """() => Object.fromEntries(['box','dot','mover'].map(id => {
            const node = document.getElementById(id); const m = node.getCTM(); const style = getComputedStyle(node);
            return [id, [m.a, m.b, m.c, m.d, m.e, m.f, node.x.animVal.value, parseFloat(style.opacity), ...style.fill.match(/[0-9.]+/g).map(Number)]];
        }))"""
        animated = animate_svg(artwork, tracks)["animated_svg"]
        for time in (0.15, 0.45, 0.9, 1.6):
            page.set_content(animated)
            page.evaluate("time => { const svg = document.querySelector('svg'); svg.pauseAnimations(); svg.setCurrentTime(time); }", time)
            expected = page.evaluate(read)
            page.set_content(export_static(artwork, responsive=False, animations=tracks, time_ms=time * 1000)["svg"])
            actual = page.evaluate(read)
            tolerances = [0.02] * 4 + [0.6, 0.6, 0.6, 0.01, 1, 1, 1]
            for element in expected:
                assert len(actual[element]) == len(tolerances), actual[element]
                assert all(abs(a - b) <= limit for a, b, limit in zip(actual[element], expected[element], tolerances)), (time, element, actual[element], expected[element])
        assert not errors, errors
        browser.close()
    print("SMIL easing, color, looping, motion path, player controls, reduced motion, and sampled frames passed")


if __name__ == "__main__":
    main()
