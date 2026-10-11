from __future__ import annotations

import builtins
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from fontTools.pens.areaPen import AreaPen
from fontTools.svgLib.path import parse_path

from glaxnimate_mcp.geometry import _matrix, combine_shapes
from glaxnimate_mcp.svg import AnimationError

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="a" width="10" height="10" fill="red"/><rect id="b" x="5" width="10" height="10"/></svg>'


class GeometryTests(unittest.TestCase):
    def test_svg_transform_composition(self) -> None:
        for raw, expected in (("translate(10 20) scale(2 3)", (12, 23)), ("matrix(2 0 0 3 10 20)", (12, 23)), ("translate(5)", (6, 1)), ("scale(2)", (2, 2)), ("rotate(90)", (-1, 1)), ("rotate(90 1 1)", (1, 1)), ("skewX(45)", (2, 1)), ("skewY(45)", (1, 2))):
            with self.subTest(raw=raw):
                actual = _matrix(raw).transformPoint((1, 1))
                self.assertAlmostEqual(actual[0], expected[0])
                self.assertAlmostEqual(actual[1], expected[1])
        for raw in ("unknown(2)", "scale()", "translate(1 2 3)", "scale(nan)"):
            with self.subTest(raw=raw), self.assertRaises(AnimationError):
                _matrix(raw)

    def test_boolean_areas_and_paint(self) -> None:
        for operation, area in (("union", 150), ("subtract", 50), ("intersect", 50), ("exclude", 100)):
            with self.subTest(operation=operation):
                result = combine_shapes(SVG, ["a", "b"], operation)
                root = ET.fromstring(result["svg"])
                self.assertEqual(len(root), 1)
                self.assertEqual(root[0].get("id"), "a")
                self.assertEqual(root[0].get("fill"), "red")
                self.assertEqual(root[0].tag, "{http://www.w3.org/2000/svg}path")
                self.assertNotIn("width", root[0].attrib)
                pen = AreaPen(None)
                parse_path(root[0].get("d"), pen)
                self.assertAlmostEqual(abs(pen.value), area)
                self.assertEqual(result["removed_ids"], ["b"])
                self.assertFalse(result["output_written"])
        transformed = SVG.replace('id="a"', 'id="a" transform="scale(2)" fill-rule="evenodd"')
        result = combine_shapes(transformed, ["a"], "union")
        pen = AreaPen(None)
        parse_path(ET.fromstring(result["svg"])[0].get("d"), pen)
        self.assertAlmostEqual(abs(pen.value), 400)

    def test_empty_intersection(self) -> None:
        result = combine_shapes(SVG.replace('x="5"', 'x="20"'), ["a", "b"], "intersect")
        self.assertEqual(ET.fromstring(result["svg"])[0].get("d"), "")
        holed = '<svg><g fill-rule="evenodd"><path id="p" d="M0 0H100V100H0Z M25 25H75V75H25Z"/></g></svg>'
        result = combine_shapes(holed, ["p"], "union")
        pen = AreaPen(None)
        parse_path(ET.fromstring(result["svg"])[0][0].get("d"), pen)
        self.assertAlmostEqual(abs(pen.value), 7500)
        for attribute in ('stroke="black"', 'filter="url(#f)"', 'mask="url(#m)"', 'clip-path="url(#c)"', 'fill="url(#g)"'):
            with self.subTest(attribute=attribute), self.assertRaisesRegex(AnimationError, "cannot preserve"):
                combine_shapes(f'<svg><g {attribute}><rect id="r" width="10" height="10" transform="scale(2)"/></g></svg>', ["r"], "union")

    def test_validation(self) -> None:
        for ids, operation in (([], "union"), (["a"], "bad"), (["a"], "subtract"), ("a", "union"), ([1], "union"), (["a", "a"], "union"), (["missing"], "union"), (["a"] * 101, "union")):
            with self.subTest(ids=ids, operation=operation), self.assertRaises(AnimationError):
                combine_shapes(SVG, ids, operation)
        invalid = [
            SVG.replace('id="a"', 'id="a" style="fill:red"'),
            SVG.replace('<rect id="a" width="10" height="10" fill="red"/>', '<rect id="a" width="10" height="10"><animate/></rect>'),
            SVG.replace('<rect id="b"', '<g><rect id="b"').replace('</svg>', '</g></svg>'),
            '<svg id="a"/>', '<svg><g id="a"/></svg>',
        ]
        for svg in invalid:
            with self.subTest(svg=svg), self.assertRaises(AnimationError):
                combine_shapes(svg, ["a", "b"] if "b" in svg else ["a"], "union")

    def test_optional_backend_and_conversion_error(self) -> None:
        original = builtins.__import__

        def without_pathops(name, *args, **kwargs):
            if name == "pathops":
                raise ImportError("not installed")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_pathops):
            with self.assertRaisesRegex(AnimationError, "geometry extra"):
                combine_shapes(SVG, ["a"], "union")
        with patch("glaxnimate_mcp.geometry.SVGPath.fromstring", side_effect=AssertionError):
            with self.assertRaisesRegex(AnimationError, "conversion failed"):
                combine_shapes(SVG, ["a"], "union")
