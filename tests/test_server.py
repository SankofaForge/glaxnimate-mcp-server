from __future__ import annotations

import unittest
from unittest.mock import patch

from glaxnimate_mcp.server import (
    glaxnimate_animate_svg,
    glaxnimate_capabilities,
    glaxnimate_combine_shapes,
    glaxnimate_export_mobile,
    glaxnimate_export_static,
    glaxnimate_create_svg,
    glaxnimate_create_project,
    glaxnimate_edit_project,
    glaxnimate_inspect_project,
    glaxnimate_text_to_path,
    glaxnimate_edit_svg,
    glaxnimate_edit_path,
    glaxnimate_export_svg,
    glaxnimate_export_media,
    glaxnimate_set_filters,
    glaxnimate_export_css,
    glaxnimate_export_lottie,
    glaxnimate_inspect_svg,
    main,
    mcp,
)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle id="dot" cx="50" cy="50" r="10" />
</svg>"""


class ServerTests(unittest.TestCase):
    def test_path_edit_tool(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><path id="line" d="M0 0L10 10"/></svg>'
        result = glaxnimate_edit_path(svg, "line", [{"action": "set_point", "command_index": 1, "point_index": 0, "x": 20, "y": 30}])
        self.assertEqual(result["commands"][1]["points"], [[20, 30]])
        self.assertFalse(result["output_written"])
        self.assertIn("error", glaxnimate_edit_path(svg, "missing", []))

    def test_static_export_tool(self) -> None:
        self.assertEqual(glaxnimate_export_static(SVG)["format"], "static SVG")
        self.assertIn("error", glaxnimate_export_static("bad"))
        sampled = glaxnimate_export_static(SVG, animations=[{"target_id": "dot", "property": "r", "values": [10, 20]}], time_ms=500)
        self.assertEqual(sampled["frame"], "500 ms")
        self.assertIn('r="15"', sampled["svg"])

    def test_mobile_tool(self) -> None:
        with patch("glaxnimate_mcp.server.export_mobile", return_value={"source": "component"}) as export:
            self.assertEqual(glaxnimate_export_mobile(SVG, [], "flutter"), {"source": "component"})
            export.assert_called_once_with(SVG, [], "flutter", "SvgAnimation", 30, 1000)
        self.assertIn("error", glaxnimate_export_mobile(SVG, [], "unknown"))

    def test_geometry_tool(self) -> None:
        with patch("glaxnimate_mcp.server.combine_shapes", return_value={"svg": SVG}) as combine:
            self.assertEqual(glaxnimate_combine_shapes(SVG, ["dot"], "union"), {"svg": SVG})
            combine.assert_called_once_with(SVG, ["dot"], "union")
        self.assertIn("error", glaxnimate_combine_shapes(SVG, [], "invalid"))

    def test_text_tool(self) -> None:
        with patch("glaxnimate_mcp.server.text_to_path", return_value={"d": "M0 0L1 1"}) as convert:
            self.assertEqual(glaxnimate_text_to_path("A", "font", 24, 10, 20, "rtl"), {"d": "M0 0L1 1"})
            convert.assert_called_once_with("A", "font", 24, 10, 20, "rtl")
        self.assertIn("error", glaxnimate_text_to_path("", "font"))

    def test_project_tools(self) -> None:
        created = glaxnimate_create_project(SVG, duration_ms=2000, fps=24)
        self.assertEqual(created["project"]["fps"], 24)
        self.assertIn("error", glaxnimate_create_project("invalid"))
        edited = glaxnimate_edit_project(created["project"], [{"action": "settings", "values": {"fps": 60}}])
        self.assertEqual(edited["project"]["fps"], 60)
        self.assertIn("error", glaxnimate_edit_project(created["project"], []))
        self.assertEqual(glaxnimate_inspect_project(edited["project"])["animation_targets"], ["dot"])
        self.assertIn("error", glaxnimate_inspect_project({}))

    def test_lottie_tool(self) -> None:
        svg = SVG.replace('viewBox="0 0 100 100"', 'width="100" height="100" viewBox="0 0 100 100"')
        self.assertEqual(glaxnimate_export_lottie(svg, [], fps=24, duration_ms=2000)["lottie"]["op"], 48)
        self.assertIn("error", glaxnimate_export_lottie("invalid", []))

    def test_css_tool(self) -> None:
        self.assertEqual(glaxnimate_export_css(SVG, [{"target_id": "dot", "property": "opacity", "values": [0, 1]}], {})["format"], "CSS animated SVG")
        self.assertIn("error", glaxnimate_export_css(SVG, [], {}))

    def test_filter_tool(self) -> None:
        self.assertIn("filter_id", glaxnimate_set_filters(SVG, "dot", [{"type": "opacity", "value": 0.5}]))
        self.assertIn("error", glaxnimate_set_filters(SVG, "missing", []))

    def test_media_tool(self) -> None:
        with patch("glaxnimate_mcp.server.render_media", return_value={"format": "png"}) as render:
            self.assertEqual(glaxnimate_export_media(SVG, [], "png"), {"format": "png"})
            render.assert_called_once_with(SVG, [], "png", 512, 512, 1000, 30, 0, "meet", 80, None)
        self.assertIn("error", glaxnimate_export_media(SVG, [], "unknown"))

    def test_authoring_tools(self) -> None:
        result = glaxnimate_create_svg(100, 100, [{"type": "circle", "id": "dot"}])
        self.assertIn("svg", result)
        self.assertFalse(result["output_written"])
        self.assertIn("error", glaxnimate_create_svg(0, 100, []))
        edited = glaxnimate_edit_svg(result["svg"], [{"action": "update", "target_id": "dot", "attributes": {"r": 10}}])
        self.assertIn('r="10"', edited["svg"])
        self.assertIn("error", glaxnimate_edit_svg(result["svg"], [{"action": "remove", "target_id": "absent"}]))

    def test_capabilities_describe_actual_formats(self) -> None:
        result = glaxnimate_capabilities()
        self.assertIn("fill", result["animation_properties"])
        self.assertEqual(result["export_formats"], ["SMIL animated SVG", "JavaScript animated SVG", "CSS animated SVG", "Lottie JSON", "static SVG"])
        self.assertIs(result["svgator_parity"], False)

    def test_export_tool(self) -> None:
        result = glaxnimate_export_svg(SVG, [{"target_id": "dot", "property": "opacity", "values": [0, 1]}], {})
        self.assertEqual(result["format"], "JavaScript animated SVG")
        self.assertIn("error", glaxnimate_export_svg(SVG, [], {}))

    def test_glaxnimate_inspect_svg_success(self) -> None:
        result = glaxnimate_inspect_svg(SVG)
        self.assertIn("animation_targets", result)
        self.assertEqual(result["animation_targets"], ["dot"])

    def test_glaxnimate_inspect_svg_dry_run(self) -> None:
        result = glaxnimate_inspect_svg(SVG, dry_run=True)
        self.assertEqual(result["animation_targets"], ["dot"])
        self.assertIs(result["dry_run"], True)
        self.assertIs(result["output_written"], False)

    def test_glaxnimate_inspect_svg_error(self) -> None:
        result = glaxnimate_inspect_svg("invalid xml")
        self.assertIn("error", result)
        self.assertIn("invalid SVG XML", result["error"])

    def test_glaxnimate_animate_svg_success(self) -> None:
        result = glaxnimate_animate_svg(
            SVG,
            [{"target_id": "dot", "property": "translate", "values": ["0 0", "10 0"]}],
        )
        self.assertIn("animated_svg", result)
        self.assertEqual(result["targets"], ["dot"])

    def test_glaxnimate_animate_svg_dry_run(self) -> None:
        result = glaxnimate_animate_svg(
            SVG,
            [{"target_id": "dot", "property": "translate", "values": ["0 0", "10 0"]}],
            dry_run=True,
        )
        self.assertIn("animated_svg", result)
        self.assertIn("<animateTransform", result["animated_svg"])
        self.assertIs(result["dry_run"], True)
        self.assertIs(result["output_written"], False)

    def test_glaxnimate_animate_svg_error(self) -> None:
        result = glaxnimate_animate_svg(
            SVG,
            [{"target_id": "missing", "property": "translate", "values": ["0 0", "10 0"]}],
        )
        self.assertIn("error", result)
        self.assertIn("does not exist", result["error"])

    def test_main(self) -> None:
        with patch.object(mcp, "run") as mock_run:
            main()
            mock_run.assert_called_once_with(transport="stdio")
