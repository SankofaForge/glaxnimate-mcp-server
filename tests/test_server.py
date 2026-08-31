from __future__ import annotations

import unittest
from unittest.mock import patch

from glaxnimate_mcp.server import (
    glaxnimate_animate_svg,
    glaxnimate_inspect_svg,
    main,
    mcp,
)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle id="dot" cx="50" cy="50" r="10" />
</svg>"""


class ServerTests(unittest.TestCase):
    def test_glaxnimate_inspect_svg_success(self) -> None:
        result = glaxnimate_inspect_svg(SVG)
        self.assertIn("animation_targets", result)
        self.assertEqual(result["animation_targets"], ["dot"])

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
