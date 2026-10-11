from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from glaxnimate_mcp.sample import _mix, _rgb
from glaxnimate_mcp.static import export_static
from glaxnimate_mcp.svg import AnimationError

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect id="box" width="10" height="10" fill="red" transform="scale(2)"/><circle id="dot" r="2"/></svg>'


def track(property: str, values: list[object], target_id: str = "box", **options: object) -> dict[str, object]:
    return {"target_id": target_id, "property": property, "values": values, **options}


def frame(animations: list[dict[str, object]], time_ms: float, svg: str = SVG) -> dict[str, ET.Element]:
    result = export_static(svg, animations=animations, time_ms=time_ms)
    return {node.get("id"): node for node in ET.fromstring(result["svg"]).iter() if node.get("id")}


class SampleTests(unittest.TestCase):
    def test_timing_and_fill(self) -> None:
        cases = [
            ({}, 500, "5"), ({"begin_ms": 600}, 500, "0"), ({}, 1500, "10"),
            ({"fill_mode": "remove"}, 1500, "0"), ({"repeat_count": 2}, 1250, "2.5"),
            ({"repeat_count": 1.5}, 9000, "5"), ({"repeat_count": "indefinite"}, 10250, "2.5"),
        ]
        for options, time, expected in cases:
            with self.subTest(options=options, time=time):
                self.assertEqual(frame([track("x", [0, 10], **options)], time)["box"].get("x", "0"), expected)
        result = export_static(SVG, animations=[], time_ms=250)
        self.assertEqual(result["frame"], "250 ms")
        self.assertEqual(export_static(SVG)["frame"], "base artwork")

    def test_interpolation_modes(self) -> None:
        self.assertEqual(frame([track("x", [0, 10, 20], calc_mode="discrete")], 600)["box"].get("x"), "10")
        self.assertEqual(frame([track("x", [0, 10, 30], key_times=[0, 0.5, 1])], 750)["box"].get("x"), "20")
        eased = float(frame([track("x", [0, 100], calc_mode="spline", key_splines=[[0.42, 0, 1, 1]])], 500)["box"].get("x"))
        self.assertTrue(30 < eased < 33, eased)
        sampled = float(frame([track("x", [0, 100], easing={"name": "ease-out"})], 500)["box"].get("x"))
        self.assertTrue(68 < sampled < 69, sampled)
        self.assertEqual(frame([track("fill", ["red", "#00f"])], 500)["box"].get("fill"), "rgb(127.5, 0, 127.5)")
        self.assertEqual(frame([track("path", ["M0 0L10 0", "M0,0 L20,10"], target_id="dot")], 500, SVG.replace('<circle id="dot" r="2"/>', '<path id="dot" d="M0 0L10 0"/>'))["dot"].get("d"), "M0 0L15 5")

    def test_transforms_motion_and_priority(self) -> None:
        nodes = frame([track("rotate", ["0 5 5", "90 5 5"]), track("translate", ["0 0", "10 0"], additive="sum")], 500)
        self.assertEqual(nodes["box"].get("transform"), "rotate(45 5 5) translate(5 0)")
        self.assertEqual(frame([track("translate", ["0 0", "10 0"], additive="sum")], 500)["box"].get("transform"), "scale(2) translate(5 0)")
        moved = frame([track("motion-path", [0, 1], motion_path="M0 0H10V10", motion_rotate="auto")], 750)["box"].get("transform")
        self.assertEqual(moved, "translate(10 5) rotate(90) scale(2)")
        reverse = frame([track("motion-path", [0, 1], target_id="dot", motion_path="M0 0H10Z", motion_rotate="auto-reverse")], 250)["dot"].get("transform")
        self.assertEqual(reverse, "translate(5 0) rotate(180)")
        fixed = frame([track("motion-path", [0, 1], target_id="dot", motion_path="M0 0C0 10 10 10 10 0", motion_rotate=30)], 1000)["dot"].get("transform")
        self.assertTrue(fixed.startswith("translate(10 0) rotate(30)"), fixed)
        prioritized = frame([track("opacity", [0.5, 0.5], begin_ms=100), track("opacity", [0.2, 0.2])], 500)
        self.assertEqual(prioritized["box"].get("opacity"), "0.5")
        self.assertEqual(frame([track("opacity", [0.2, 0.2]), track("opacity", [0.7, 0.7])], 500)["box"].get("opacity"), "0.7")

    def test_colors_and_structure(self) -> None:
        self.assertEqual(_rgb(" Orange "), [255, 165, 0])
        self.assertEqual(_rgb("#abc"), [170, 187, 204])
        self.assertEqual(_rgb("rgb(1, 2.5, 3)"), [1, 2.5, 3])
        self.assertEqual(_mix("1e1 50%", "3e1 100%", 0.5, False), "20 75%")
        for first, second in (("M0 0", "M0 0L1 1"), ("1 2", "1,2 3"), ("M0 0", "L0 0")):
            with self.subTest(first=first, second=second), self.assertRaisesRegex(AnimationError, "same structure"):
                _mix(first, second, 0.5, False)
        with self.assertRaisesRegex(AnimationError, "sampled colors"):
            _mix("currentColor", "red", 0.5, True)

    def test_validation(self) -> None:
        for animations, message in (({}, "array"), ([track("x", [0, 1])] * 101, "array"), ([None], "object"),
                                    ([track("x", [0, 1], target_id="missing")], "does not exist"),
                                    ([track("motion-path", [0, 1], motion_path="M0")], "motion_path is invalid"),
                                    ([track("motion-path", [0, 1], motion_path="M5 5")], "positive length")):
            with self.subTest(message=message), self.assertRaisesRegex(AnimationError, message):
                export_static(SVG, animations=animations, time_ms=500)
        with self.assertRaisesRegex(AnimationError, "time_ms"):
            export_static(SVG, animations=[], time_ms=-1)


if __name__ == "__main__":
    unittest.main()
