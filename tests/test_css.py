from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from glaxnimate_mcp.css import export_css
from glaxnimate_mcp.svg import AnimationError

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><path id="shape" d="M0 0 L10 10"/></svg>'
BASE = {"target_id": "shape", "property": "opacity", "values": [0, 1]}


class CssTests(unittest.TestCase):
    def test_styles_and_keyframe_timing(self) -> None:
        result = export_css(SVG, [
            BASE | {"duration_ms": 500, "calc_mode": "spline", "key_splines": [[0.4, 0, 0.2, 1]]},
            BASE | {"property": "fill", "values": ["red", "blue"], "calc_mode": "discrete"},
        ], {"alternate": True, "iterations": 0})
        root = ET.fromstring(result["animated_svg"])
        style = root.find("{*}style").text
        self.assertIn("50%{opacity:1", style)
        self.assertIn("100%{opacity:1}", style)
        self.assertIn("cubic-bezier(0.4,0,0.2,1)", style)
        self.assertIn("steps(1,end)", style)
        self.assertIn("infinite alternate forwards", style)
        self.assertIn("prefers-reduced-motion:reduce", style)
        self.assertEqual(root.findall(".//{*}animate"), [])
        self.assertEqual(root.findall(".//{*}script"), [])
        self.assertEqual(result["reduced_motion_svg"], SVG)

    def test_transforms_lengths_and_path_values(self) -> None:
        specs = [
            ("translate", ["0 0", "10 20"], "translate(10px,20px)"),
            ("scale", [1, 2], "scale(2)"),
            ("rotate", [0, "45 10 20"], "translate(10px,20px) rotate(45deg) translate(-10px,-20px)"),
            ("skewX", [0, 20], "skewX(20deg)"),
            ("x", [0, 100], "100px"),
            ("y", ["0%", "100%"], "100%"),
            ("path", ["M0 0 L10 10", "M0 0 L20 20"], 'path("M0 0 L20 20")'),
        ]
        for property, values, expected in specs:
            with self.subTest(property=property):
                result = export_css(SVG, [BASE | {"property": property, "values": values, "additive": "sum"}], {})
                style = ET.fromstring(result["animated_svg"]).find("{*}style").text
                self.assertIn(expected, style)
        for values in (["bad", "2"], ["1 2 3 4", "2"], ["nan", "2"]):
            with self.subTest(values=values), self.assertRaises(AnimationError):
                export_css(SVG, [BASE | {"property": "scale", "values": values}], {})

    def test_hover_reverse_and_root_targets(self) -> None:
        for mode in ("freeze", "reset"):
            result = export_css(SVG, [BASE], {"trigger": "hover", "hover_out": mode, "direction": -1, "alternate": True})
            style = ET.fromstring(result["animated_svg"]).find("{*}style").text
            self.assertIn(":hover", style)
            self.assertIn("alternate-reverse", style)
            self.assertEqual(":not(:hover)" in style, mode == "reset")
        rooted = SVG.replace('<svg ', '<svg id="root" ')
        result = export_css(rooted, [BASE | {"target_id": "root"}], {"direction": -1})
        style = ET.fromstring(result["animated_svg"]).find("{*}style").text
        self.assertIn("][data-glax-track", style)
        self.assertIn(" reverse forwards", style)

    def test_reject_unsupported_css_semantics(self) -> None:
        for property in ("fill", "stroke", "stop-color", "x"):
            with self.subTest(property=property), self.assertRaisesRegex(AnimationError, "stylesheet syntax"):
                export_css(SVG, [BASE | {"property": property, "values": ["red}}body{background:red}/*", "blue"]}], {})
        for options in ({"trigger": "click"}, {"trigger": "hover", "hover_out": "reverse"}):
            with self.subTest(options=options), self.assertRaises(AnimationError):
                export_css(SVG, [BASE], options)
        for spec in (BASE | {"begin_ms": 1}, BASE | {"fill_mode": "remove"}, BASE | {"property": "points"}):
            with self.subTest(spec=spec), self.assertRaises(AnimationError):
                export_css(SVG, [spec], {})
