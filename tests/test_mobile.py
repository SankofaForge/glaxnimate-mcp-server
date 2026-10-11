from __future__ import annotations

import base64
import json
import re
import unittest

from glaxnimate_mcp.mobile import export_mobile
from glaxnimate_mcp.svg import AnimationError

SVG = '<svg width="100" height="100"><rect id="box" width="10" height="20"/></svg>'


class MobileTests(unittest.TestCase):
    def test_native_player_sources_embed_vector_data(self) -> None:
        for platform in ("react-native", "flutter"):
            with self.subTest(platform=platform):
                result = export_mobile(SVG, [], platform, "Logo")
                source = result["source"]
                if platform == "react-native":
                    data = json.loads(source.split("const animationData = ")[1].split(";\n")[0])
                    self.assertIn("function Logo(props)", source)
                    self.assertIn("...props", source)
                    self.assertEqual(result["dependencies"], ["lottie-react-native"])
                else:
                    encoded = re.search(r"base64Decode\('([^']*)'\)", source)[1]
                    data = json.loads(base64.b64decode(encoded))
                    self.assertIn("class Logo extends StatelessWidget", source)
                    self.assertIn("controller: controller", source)
                    self.assertEqual(result["dependencies"], ["lottie"])
                self.assertEqual(data, result["lottie"])
                self.assertFalse(result["output_written"])

    def test_invalid_platform_and_component_names(self) -> None:
        with self.assertRaises(AnimationError):
            export_mobile(SVG, [], "web")
        for name in (None, "", "lowercase", "Invalid.Name", "A" * 65):
            with self.subTest(name=name), self.assertRaises(AnimationError):
                export_mobile(SVG, [], "flutter", name)
