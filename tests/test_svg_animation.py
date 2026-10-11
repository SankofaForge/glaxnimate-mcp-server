from __future__ import annotations

import unittest
from unittest.mock import patch

from glaxnimate_mcp import __file__ as pkg_file
from glaxnimate_mcp.svg import (
    MAX_ANIMATIONS,
    MAX_KEYFRAMES,
    MAX_SVG_BYTES,
    AnimationError,
    _id_index,
    _key_times,
    _number,
    _parse_svg,
    _values,
    animate_svg,
    inspect_svg,
)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 120 120">
  <g id="character"><circle id="eye" cx="60" cy="60" r="10" /></g>
</svg>"""


class SvgAnimationTests(unittest.TestCase):
    def test_motion_path(self) -> None:
        base = {"target_id": "eye", "property": "motion-path", "values": [0, 0.5, 1],
                "motion_path": "M0 0 Q50 100 100 0"}
        result = animate_svg(SVG, [base])
        self.assertIn('<animateMotion', result["animated_svg"])
        self.assertIn('keyPoints="0;0.5;1"', result["animated_svg"])
        self.assertIn('rotate="auto"', result["animated_svg"])
        result = animate_svg(SVG, [base | {"motion_rotate": 45}])
        self.assertIn('rotate="45"', result["animated_svg"])
        for options in ({"motion_path": None}, {"motion_path": " "},
                        {"motion_rotate": "invalid"}, {"values": [0, 2]}):
            with self.subTest(options=options), self.assertRaises(AnimationError):
                animate_svg(SVG, [base | options])

    def test_extended_timeline(self) -> None:
        from xml.etree import ElementTree as ET

        spec = {
            "target_id": "eye", "property": "fill", "values": ["red", "blue", "red"],
            "calc_mode": "spline", "key_splines": [[0.4, 0, 0.2, 1], [0, 0, 1, 1]],
            "repeat_count": "indefinite", "fill_mode": "remove",
        }
        result = animate_svg(SVG, [spec])
        animation = ET.fromstring(result["animated_svg"]).find(".//{*}animate")
        self.assertEqual(animation.attrib["keySplines"], "0.4 0 0.2 1;0 0 1 1")
        self.assertEqual(animation.attrib["repeatCount"], "indefinite")
        self.assertEqual(animation.attrib["fill"], "remove")
        self.assertEqual(result["reduced_motion_svg"], SVG)
        transform = animate_svg(SVG, [{
            "target_id": "eye", "property": "skewX", "values": [0, 20], "additive": "sum",
        }])
        self.assertIn('additive="sum"', transform["animated_svg"])
        self.assertIn('type="skewX"', transform["animated_svg"])
        discrete = animate_svg(SVG, [{
            "target_id": "eye", "property": "fill", "values": ["red", "blue"], "calc_mode": "discrete",
        }])
        self.assertIn('calcMode="discrete"', discrete["animated_svg"])

    def test_extended_timeline_rejects_invalid_options(self) -> None:
        base = {"target_id": "eye", "property": "translate", "values": [0, 1]}
        for options, message in [
            ({"property": []}, "property must"),
            ({"calc_mode": "unknown"}, "calc_mode must"),
            ({"fill_mode": "unknown"}, "fill_mode must"),
            ({"additive": "unknown"}, "additive must"),
            ({"calc_mode": "spline"}, "one curve per"),
            ({"calc_mode": "spline", "key_splines": []}, "one curve per"),
            ({"calc_mode": "spline", "key_splines": [None]}, "four numbers"),
            ({"calc_mode": "spline", "key_splines": [[0, 1]]}, "four numbers"),
            ({"calc_mode": "spline", "key_splines": [[0, 0, 1, 2]]}, "between 0 and 1"),
            ({"key_splines": [[0, 0, 1, 1]]}, "requires calc_mode spline"),
        ]:
            with self.subTest(options=options), self.assertRaisesRegex(AnimationError, message):
                animate_svg(SVG, [base | options])

    def test_package_init(self) -> None:
        self.assertTrue(pkg_file.endswith("__init__.py"))

    def test_inspection_lists_addressable_elements(self) -> None:
        result = inspect_svg(SVG)

        self.assertEqual(result["animation_targets"], ["character", "eye"])
        self.assertEqual(result["element_count"], 3)
        self.assertEqual(result["width"], "100")
        self.assertEqual(result["height"], "100")
        self.assertEqual(result["viewBox"], "0 0 120 120")
        self.assertEqual(result["addressable_elements"][0]["type"], "g")
        self.assertEqual(result["addressable_elements"][0]["children"], 1)

    def test_parse_svg_validation(self) -> None:
        with self.assertRaisesRegex(AnimationError, "must be a non-empty string"):
            _parse_svg("")
        with self.assertRaisesRegex(AnimationError, "must be a non-empty string"):
            _parse_svg("   ")
        with self.assertRaisesRegex(AnimationError, "must be a non-empty string"):
            _parse_svg(None)  # type: ignore[arg-type]

        oversized = "<svg>" + (" " * (MAX_SVG_BYTES + 1)) + "</svg>"
        with self.assertRaisesRegex(AnimationError, "exceeds the"):
            _parse_svg(oversized)

        with self.assertRaisesRegex(AnimationError, "DOCTYPE"):
            _parse_svg('<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" />')
        with self.assertRaisesRegex(AnimationError, "DOCTYPE or entity"):
            _parse_svg('<!ENTITY test "val"><svg xmlns="http://www.w3.org/2000/svg" />')

        with self.assertRaisesRegex(AnimationError, "invalid SVG XML"):
            _parse_svg("<svg><unclosed></svg>")

        with self.assertRaisesRegex(AnimationError, "document root must be an <svg> element"):
            _parse_svg('<g id="character"><circle id="eye" /></g>')

    def test_duplicate_id_rejection(self) -> None:
        duplicate_svg = """<svg xmlns="http://www.w3.org/2000/svg">
          <circle id="item" />
          <rect id="item" />
        </svg>"""
        with self.assertRaisesRegex(AnimationError, "duplicate SVG id: item"):
            inspect_svg(duplicate_svg)

    def test_number_validation(self) -> None:
        self.assertEqual(_number(10, "test", 0, 100), 10.0)
        self.assertEqual(_number(10.5, "test", 0, 100), 10.5)

        with self.assertRaisesRegex(AnimationError, "must be a number"):
            _number(True, "flag", 0, 1)
        with self.assertRaisesRegex(AnimationError, "must be a number"):
            _number("10", "str_val", 0, 100)

        with self.assertRaisesRegex(AnimationError, "must be between 0 and 100"):
            _number(-1, "range_test", 0, 100)
        with self.assertRaisesRegex(AnimationError, "must be between 0 and 100"):
            _number(101, "range_test", 0, 100)

    def test_values_validation(self) -> None:
        self.assertEqual(_values(["0 0", "10 0"]), ["0 0", "10 0"])

        with self.assertRaisesRegex(AnimationError, "must be an array of at least two values"):
            _values("0 0;10 0")
        with self.assertRaisesRegex(AnimationError, "must be an array of at least two values"):
            _values(b"0 0")
        with self.assertRaisesRegex(AnimationError, "must be an array of at least two values"):
            _values(123)

        with self.assertRaisesRegex(AnimationError, "must contain 2 to 512 keyframes"):
            _values(["0"])
        with self.assertRaisesRegex(AnimationError, "must contain 2 to 512 keyframes"):
            _values(["0"] * (MAX_KEYFRAMES + 1))

        with self.assertRaisesRegex(AnimationError, "must be non-empty plain values"):
            _values(["", "10"])
        with self.assertRaisesRegex(AnimationError, "must be non-empty plain values"):
            _values(["0;0", "10"])
        with self.assertRaisesRegex(AnimationError, "must be non-empty plain values"):
            _values(["<script>", "10"])
        with self.assertRaisesRegex(AnimationError, "must be non-empty plain values"):
            _values(["10>", "10"])

    def test_key_times_validation(self) -> None:
        self.assertEqual(_key_times(None, 2), "0;1")
        self.assertEqual(_key_times(None, 3), "0;0.5;1")
        self.assertEqual(_key_times([0, 0.5, 1], 3), "0;0.5;1")

        with self.assertRaisesRegex(AnimationError, "must have one entry for each value"):
            _key_times("0;1", 2)
        with self.assertRaisesRegex(AnimationError, "must have one entry for each value"):
            _key_times([0, 1], 3)

        with self.assertRaisesRegex(AnimationError, "must start at 0 and end at 1"):
            _key_times([0.1, 1], 2)
        with self.assertRaisesRegex(AnimationError, "must start at 0 and end at 1"):
            _key_times([0, 0.9], 2)

        with self.assertRaisesRegex(AnimationError, "must be strictly increasing"):
            _key_times([0, 0.5, 0.4, 1], 4)
        with self.assertRaisesRegex(AnimationError, "must be strictly increasing"):
            _key_times([0, 0.5, 0.5, 1], 4)

    def test_animation_transform_types(self) -> None:
        for prop in ["translate", "rotate", "scale"]:
            result = animate_svg(
                SVG,
                [{"target_id": "character", "property": prop, "values": ["0 0", "10 10"]}],
            )
            self.assertIn("animateTransform", result["animated_svg"])
            self.assertIn(f'type="{prop}"', result["animated_svg"])

    def test_animation_standard_properties(self) -> None:
        result = animate_svg(
            SVG,
            [
                {
                    "target_id": "eye",
                    "property": "opacity",
                    "values": ["1", "0.2", "1"],
                    "duration_ms": 500,
                    "begin_ms": 100,
                    "repeat_count": 5,
                    "key_times": [0, 0.5, 1],
                },
                {
                    "target_id": "eye",
                    "property": "stroke-dashoffset",
                    "values": ["100", "0"],
                },
                {
                    "target_id": "eye",
                    "property": "path",
                    "values": ["M0 0 L10 10", "M0 0 L20 20"],
                },
            ],
        )
        self.assertIn('attributeName="opacity"', result["animated_svg"])
        self.assertIn('attributeName="stroke-dashoffset"', result["animated_svg"])
        self.assertIn('attributeName="d"', result["animated_svg"])
        self.assertIn('dur="500ms"', result["animated_svg"])
        self.assertIn('begin="100ms"', result["animated_svg"])
        self.assertIn('repeatCount="5"', result["animated_svg"])
        self.assertEqual(result["animation_count"], 3)
        self.assertEqual(result["targets"], ["eye", "eye", "eye"])
        self.assertEqual(result["format"], "SMIL animated SVG")

    def test_animation_spec_validation(self) -> None:
        with self.assertRaisesRegex(AnimationError, "must be an array"):
            animate_svg(SVG, "invalid")  # type: ignore[arg-type]
        with self.assertRaisesRegex(AnimationError, "must contain 1 to 100 entries"):
            animate_svg(SVG, [])
        with self.assertRaisesRegex(AnimationError, "must contain 1 to 100 entries"):
            animate_svg(
                SVG,
                [{"target_id": "eye", "property": "opacity", "values": ["0", "1"]}]
                * (MAX_ANIMATIONS + 1),
            )

        with self.assertRaisesRegex(AnimationError, "each animation must be an object"):
            animate_svg(SVG, ["not-a-dict"])  # type: ignore[list-item]

        with self.assertRaisesRegex(AnimationError, "target_id must be a non-empty string"):
            animate_svg(SVG, [{"target_id": "", "property": "opacity", "values": ["0", "1"]}])
        with self.assertRaisesRegex(AnimationError, "target_id must be a non-empty string"):
            animate_svg(SVG, [{"property": "opacity", "values": ["0", "1"]}])

        with self.assertRaisesRegex(AnimationError, "property must be one of"):
            animate_svg(SVG, [{"target_id": "eye", "property": "color", "values": ["red", "blue"]}])

        with self.assertRaisesRegex(AnimationError, "animation target does not exist"):
            animate_svg(SVG, [{"target_id": "nonexistent", "property": "opacity", "values": ["0", "1"]}])
