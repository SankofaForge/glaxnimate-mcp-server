from __future__ import annotations

import unittest

from glaxnimate_mcp.svg import AnimationError, animate_svg, inspect_svg


SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <g id="character"><circle id="eye" cx="60" cy="60" r="10" /></g>
</svg>'''


class SvgAnimationTests(unittest.TestCase):
    def test_inspection_lists_addressable_elements(self) -> None:
        result = inspect_svg(SVG)

        self.assertEqual(result["animation_targets"], ["character", "eye"])
        self.assertEqual(result["element_count"], 3)

    def test_adds_translate_animation(self) -> None:
        result = animate_svg(
            SVG,
            [
                {
                    "target_id": "character",
                    "property": "translate",
                    "values": ["0 0", "30 0", "0 0"],
                    "duration_ms": 900,
                    "repeat_count": 2,
                }
            ],
        )

        self.assertIn("animateTransform", result["animated_svg"])
        self.assertIn('type="translate"', result["animated_svg"])
        self.assertIn('values="0 0;30 0;0 0"', result["animated_svg"])
        self.assertEqual(result["reduced_motion_svg"], SVG)

    def test_rejects_unknown_targets(self) -> None:
        with self.assertRaisesRegex(AnimationError, "does not exist"):
            animate_svg(
                SVG,
                [{"target_id": "missing", "property": "opacity", "values": ["0", "1"]}],
            )

    def test_rejects_external_entities(self) -> None:
        with self.assertRaisesRegex(AnimationError, "DOCTYPE"):
            inspect_svg('<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" />')
