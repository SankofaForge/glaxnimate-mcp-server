from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from glaxnimate_mcp.static import export_static
from glaxnimate_mcp.svg import AnimationError


class StaticTests(unittest.TestCase):
    def test_viewbox_inference_and_inline_style_rejection(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="12.5" height="8.25"><rect width="2" height="3"/></svg>'
        root = ET.fromstring(export_static(svg)["svg"])
        self.assertEqual(root.get("viewBox"), "0 0 12.5 8.25")
        self.assertNotIn("width", root.attrib)
        self.assertNotIn("height", root.attrib)
        with self.assertRaisesRegex(AnimationError, "positive numeric"):
            export_static('<svg width="12.5"/>')
        with self.assertRaisesRegex(AnimationError, "inline style"):
            export_static('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><g><rect style="animation:fade 1s"/></g></svg>')
        with self.assertRaisesRegex(AnimationError, "stylesheets"):
            export_static('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><style>rect { animation: fade 1s; }</style><rect/></svg>')

    def test_responsive_base_artwork_and_id_references(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="50"><title id="label">Art</title><defs><linearGradient id="paint"/></defs><rect id="box" stroke="url(\'#paint\')" aria-labelledby="label missing"><animate attributeName="x" values="0;100"/><set attributeName="opacity" to="0"/></rect><use id="copy" href="#box" xlink:href="#box"/><script>throw 1</script></svg>'
        result = export_static(svg, minify_ids=True)
        root = ET.fromstring(result["svg"])
        self.assertEqual(root.get("viewBox"), "0 0 100 50")
        self.assertNotIn("width", root.attrib)
        self.assertNotIn("height", root.attrib)
        mapping = result["id_map"]
        nodes = {node.get("id"): node for node in root.iter()}
        self.assertEqual(nodes[mapping["box"]].get("stroke"), "url(#" + mapping["paint"] + ")")
        self.assertEqual(nodes[mapping["box"]].get("aria-labelledby"), mapping["label"] + " missing")
        self.assertEqual(nodes[mapping["copy"]].get("href"), "#" + mapping["box"])
        self.assertEqual(nodes[mapping["copy"]].get("{http://www.w3.org/1999/xlink}href"), "#" + mapping["box"])
        self.assertEqual(root.findall(".//{*}animate"), [])
        self.assertEqual(root.findall(".//{*}script"), [])
        self.assertFalse(result["output_written"])
        fixed = export_static(svg, responsive=False)
        self.assertEqual(ET.fromstring(fixed["svg"]).get("width"), "100")
        self.assertEqual(fixed["id_map"], {})
        self.assertEqual(ET.fromstring(export_static('<svg viewBox="0 0 1 1"/>')["svg"]).get("viewBox"), "0 0 1 1")

    def test_reject_unsupported_static_export(self) -> None:
        for svg in ('<svg/>', '<svg width="0" height="1"/>', '<svg width="100%" height="1"/>', '<svg width="1" height="0"/>', '<svg><style/></svg>', '<svg style="animation:x"/>'):
            with self.subTest(svg=svg), self.assertRaises(AnimationError):
                export_static(svg)
        for options in ({"responsive": 1}, {"minify_ids": 1}):
            with self.subTest(options=options), self.assertRaises(AnimationError):
                export_static('<svg/>', **options)
