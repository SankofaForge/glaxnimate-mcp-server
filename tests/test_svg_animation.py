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

        with self.assertRaisesRegex(AnimationError, "must contain 2 to 24 keyframes"):
            _values(["0"])
        with self.assertRaisesRegex(AnimationError, "must contain 2 to 24 keyframes"):
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
