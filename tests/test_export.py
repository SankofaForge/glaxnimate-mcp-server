from __future__ import annotations

import json
import unittest
from xml.etree import ElementTree as ET

from glaxnimate_mcp.export import export_svg
from glaxnimate_mcp.svg import AnimationError


SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="shape" width="10" height="10"/></svg>'
ANIMATIONS = [{"target_id": "shape", "property": "x", "values": [0, 100], "duration_ms": 500, "begin_ms": 100}]


class ExportTests(unittest.TestCase):
    def test_standalone_player_export(self) -> None:
        result = export_svg(SVG, ANIMATIONS, {"trigger": "hover", "hover_out": "reverse", "iterations": 0})
        root = ET.fromstring(result["animated_svg"])
        self.assertEqual(root.get("id"), result["root_id"])
        script = root.find("{*}script").text
        self.assertNotIn("__OPTIONS__", script)
        options = json.loads(script.split("const options = ")[1].split(";", 1)[0])
        self.assertEqual(options["duration_ms"], 600)
        self.assertEqual(options["iterations"], 0)
        self.assertEqual(result["reduced_motion_svg"], SVG)
        self.assertFalse(result["output_written"])
        self.assertEqual(export_svg(SVG, ANIMATIONS, {})["root_id"], result["root_id"])

    def test_existing_and_explicit_root_ids(self) -> None:
        existing = SVG.replace('<svg ', '<svg id="existing" ')
        self.assertEqual(export_svg(existing, ANIMATIONS, {})["root_id"], "existing")
        self.assertEqual(export_svg(existing, ANIMATIONS, {"root_id": "explicit"})["root_id"], "explicit")
        with self.assertRaisesRegex(AnimationError, "valid SVG ID"):
            export_svg(SVG.replace('<svg ', '<svg id="bad root" '), ANIMATIONS, {})
        with self.assertRaisesRegex(AnimationError, "duplicate"):
            export_svg(SVG, ANIMATIONS, {"root_id": "shape"})

    def test_invalid_playback(self) -> None:
        for options in [
            None, [], {"unsupported": True}, {"trigger": "bad"},
            {"hover_out": "restart"}, {"click_again": "reset"},
            {"direction": True}, {"direction": 0}, {"alternate": 1},
            {"iterations": True}, {"iterations": 1.5}, {"iterations": -1},
            {"iterations": 1001}, {"speed": 0}, {"scroll_threshold": 101},
            {"root_id": "invalid id"}, {"root_id": 42},
        ]:
            with self.subTest(options=options), self.assertRaises(AnimationError):
                export_svg(SVG, ANIMATIONS, options)
        with self.assertRaisesRegex(AnimationError, "repeat_count"):
            export_svg(SVG, [ANIMATIONS[0] | {"repeat_count": "indefinite"}], {})
        with self.assertRaisesRegex(AnimationError, "existing scripts"):
            export_svg(SVG.replace('</svg>', '<script/></svg>'), ANIMATIONS, {})


if __name__ == "__main__":
    unittest.main()
