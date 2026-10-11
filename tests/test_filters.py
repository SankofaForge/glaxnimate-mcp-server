from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from glaxnimate_mcp.filters import set_filters
from glaxnimate_mcp.svg import AnimationError, animate_svg

SVG = '<svg xmlns="http://www.w3.org/2000/svg" id="root"><rect id="shape" width="10" height="10"/></svg>'
SHADOW = {"blur": {"x": 4, "y": 2}, "offset": {"x": 1, "y": 2}, "color": {"r": 255, "g": 0, "b": 0, "a": 0.5}}


class FilterTests(unittest.TestCase):
    def test_ordered_chain_and_animation_targets(self) -> None:
        result = set_filters(SVG, "shape", [
            {"type": "blur", "value": {"x": 2, "y": 4}},
            {"type": "brightness", "value": 1.2},
            {"type": "contrast", "value": 2},
            {"type": "invert", "value": 0.5},
            {"type": "opacity", "value": 0.8},
        ])
        root = ET.fromstring(result["svg"])
        chain = root.find(".//{*}filter")
        self.assertEqual(chain[0].get("in"), "SourceGraphic")
        self.assertEqual(chain[1].get("in"), chain[0].get("result"))
        self.assertEqual(chain[1][0].get("slope"), "1.2")
        self.assertEqual(chain[2][0].get("intercept"), "-0.5")
        self.assertEqual(chain[3][0].get("tableValues"), "0.5 0.5")
        self.assertTrue(chain[4][0].tag.endswith("feFuncA"))
        animated = animate_svg(result["svg"], [{"target_id": chain[0].get("id"), "property": "stdDeviation", "values": ["0 0", "4 4"]}])
        self.assertIn('attributeName="stdDeviation"', animated["animated_svg"])
        second = set_filters(result["svg"], "shape", [{"type": "blur", "value": {"x": 1, "y": 1}}])
        self.assertEqual(len(ET.fromstring(second["svg"]).findall(".//{*}filter")), 1)
        self.assertEqual(second["filter_id"], result["filter_id"])

    def test_color_matrices(self) -> None:
        result = set_filters(SVG, "shape", [{"type": kind, "value": value} for kind, value in
            [("grayscale", 0.75), ("saturate", 2), ("hue-rotate", 90), ("sepia", 0.5)]])
        matrices = ET.fromstring(result["svg"]).findall(".//{*}feColorMatrix")
        self.assertEqual(matrices[0].attrib["values"], "0.25")
        self.assertEqual(matrices[1].attrib["values"], "2")
        self.assertEqual(matrices[2].attrib["type"], "hueRotate")
        self.assertEqual(len(matrices[3].attrib["values"].split()), 20)
        self.assertEqual(float(matrices[3].attrib["values"].split()[0]), 0.6965)

    def test_shadows(self) -> None:
        result = set_filters(SVG, "shape", [{"type": "drop-shadow", "value": SHADOW}, {"type": "inner-shadow", "value": SHADOW}])
        chain = ET.fromstring(result["svg"]).find(".//{*}filter")
        self.assertEqual(chain[0].get("flood-color"), "rgb(255,0,0)")
        self.assertEqual(chain[0].get("flood-opacity"), "0.5")
        self.assertEqual(chain[-1].get("operator"), "over")
        self.assertEqual(chain[-1].get("in2"), chain[0].get("result"))

    def test_invalid_effects_and_collisions(self) -> None:
        invalid = [None, [], [{}] * 21, [None], [{"type": "bad"}], [{"type": "blur", "value": 2}],
                   [{"type": "blur", "value": {}}], [{"type": "drop-shadow", "value": {}}],
                   [{"type": "drop-shadow", "value": {"blur": {"x": 1, "y": 1}}}],
                   [{"type": "opacity", "value": 2}]]
        for effects in invalid:
            with self.subTest(effects=effects), self.assertRaises(AnimationError):
                set_filters(SVG, "shape", effects)
        for target in ("missing", "root"):
            with self.subTest(target=target), self.assertRaises(AnimationError):
                set_filters(SVG, target, [{"type": "opacity", "value": 0.5}])
        result = set_filters(SVG, "shape", [{"type": "opacity", "value": 0.5}])
        collision = SVG.replace('</svg>', f'<circle id="{result["filter_id"]}"/></svg>')
        with self.assertRaisesRegex(AnimationError, "conflicts"):
            set_filters(collision, "shape", [{"type": "opacity", "value": 0.5}])
        wrong_owner = result["svg"].replace('data-glax-target="shape"', 'data-glax-target="other"')
        with self.assertRaisesRegex(AnimationError, "conflicts"):
            set_filters(wrong_owner, "shape", [{"type": "opacity", "value": 0.5}])
