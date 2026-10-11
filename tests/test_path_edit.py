"""Checks for path normalization and atomic coordinate edits."""

from copy import deepcopy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from glaxnimate_mcp.path_edit import edit_path
from glaxnimate_mcp.svg import AnimationError


def artwork(data: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg"><g transform="translate(10 20)"><path id="p" fill="red" transform="scale(2)" d="{data}"/></g></svg>'


class PathEditTests(unittest.TestCase):
    def test_inspection_normalizes_relative_quadratic_arc_and_closed_paths(self) -> None:
        result = edit_path(artwork("m1 2 l3 4 q3 6 9 0 a10 10 0 0 1 10 10 z M50 50L60 60"), "p", [])
        commands = result["commands"]
        self.assertEqual(commands[0], {"command": "moveTo", "points": [[1, 2]]})
        self.assertEqual(commands[1], {"command": "lineTo", "points": [[4, 6]]})
        self.assertIn("curveTo", [item["command"] for item in commands])
        self.assertIn("closePath", [item["command"] for item in commands])
        self.assertEqual(commands[-1], {"command": "endPath", "points": []})
        self.assertEqual(result["coordinate_system"], "element-local")
        self.assertFalse(result["output_written"])

    def test_edits_preserve_attributes_and_input(self) -> None:
        svg = artwork("M0 0C1 2 3 4 5 6")
        operations = [{"action": "set_point", "command_index": 1, "point_index": 1, "x": 30, "y": -40}]
        original = deepcopy(operations)
        result = edit_path(svg, "p", operations)
        path = next(node for node in ET.fromstring(result["svg"]).iter() if node.get("id") == "p")
        self.assertEqual(path.get("transform"), "scale(2)")
        self.assertEqual(path.get("fill"), "red")
        self.assertEqual(result["commands"][1]["points"], [[1, 2], [30, -40], [5, 6]])
        self.assertEqual(operations, original)
        self.assertEqual(edit_path(svg, "p", [])["commands"][1]["points"][1], [3, 4])

    def test_invalid_targets_and_data(self) -> None:
        for svg, target in [(artwork("M0 0"), "missing"), (artwork("M0 0"), None), ('<svg><rect id="p"/></svg>', "p"), (artwork(""), "p"), (artwork("M0"), "p"), (artwork("garbage"), "p"), (artwork("M1e99 0"), "p")]:
            with self.subTest(svg=svg, target=target), self.assertRaises(AnimationError):
                edit_path(svg, target, [])

    def test_rejects_styles_and_animation(self) -> None:
        sources = [
            '<svg><style>path{d:path("M0 0")}</style><path id="p" d="M0 0"/></svg>',
            '<svg><path id="p" style="fill:red" d="M0 0"/></svg>',
            '<svg style="fill:red"><path id="p" d="M0 0"/></svg>',
            '<svg><path id="p" d="M0 0"><animate attributeName="d"/></path></svg>',
            '<svg><path id="p" d="M0 0"/><animate href="#p"/></svg>',
            '<svg><script/><path id="p" d="M0 0"/></svg>',
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(AnimationError):
                edit_path(source, "p", [])

    def test_invalid_edits_are_atomic(self) -> None:
        valid = {"action": "set_point", "command_index": 0, "point_index": 0, "x": 10, "y": 20}
        bad = [None, {}, valid | {"action": "delete"}, valid | {"extra": 1}]
        bad.extend(valid | {field: value} for field in ("command_index", "point_index") for value in (True, "0", -1, 20))
        bad.extend(valid | {"x": value} for value in (True, "1", float("nan"), float("inf"), 1e10))
        bad.append(valid | {"command_index": 1})
        svg = artwork("M0 0Z")
        for operation in bad:
            with self.subTest(operation=operation), self.assertRaises(AnimationError):
                edit_path(svg, "p", [valid, operation])
        self.assertEqual(edit_path(svg, "p", [])["commands"][0]["points"], [[0, 0]])
        for operations in (None, {}, [valid] * 101):
            with self.subTest(operations=operations), self.assertRaises(AnimationError):
                edit_path(svg, "p", operations)

    def test_command_limit(self) -> None:
        with patch("glaxnimate_mcp.path_edit.MAX_COMMANDS", 1), self.assertRaisesRegex(AnimationError, "command limit"):
            edit_path(artwork("M0 0L1 1"), "p", [])
        with patch("glaxnimate_mcp.path_edit.MAX_COMMANDS", 3), self.assertRaisesRegex(AnimationError, "command limit"):
            edit_path(artwork("M0 0L1 1"), "p", [{"action": "split_segment", "command_index": 1, "t": 0.5}])

    def test_split_and_remove_segments(self) -> None:
        line = edit_path(artwork("M0 0L10 20"), "p", [{"action": "split_segment", "command_index": 1, "t": 0.25}])["commands"]
        self.assertEqual([item["points"] for item in line[1:3]], [[[2.5, 5]], [[10, 20]]])
        curve = edit_path(artwork("M0 0C0 10 10 10 10 0"), "p", [{"action": "split_segment", "command_index": 1, "t": 0.5}])["commands"]
        self.assertEqual(curve[1], {"command": "curveTo", "points": [[0, 5], [2.5, 7.5], [5, 7.5]]})
        self.assertEqual(curve[2], {"command": "curveTo", "points": [[7.5, 7.5], [10, 5], [10, 0]]})
        result = edit_path(artwork("M0 0L1 1L2 0"), "p", [{"action": "split_segment", "command_index": 2, "t": 0.5}, {"action": "remove_command", "command_index": 1}])
        self.assertEqual([item["points"] for item in result["commands"][1:3]], [[[1.5, 0.5]], [[2, 0]]])
        self.assertIn('d="M0.0 0.0 1.5 0.5 2.0 0.0"', result["svg"])
        closed = [item["command"] for item in edit_path(artwork("M0 0L1 1Z"), "p", [])["commands"]].index("closePath")
        for operation in ({"action": "split_segment", "command_index": 0, "t": 0.5}, {"action": "remove_command", "command_index": closed},
                          {"action": "split_segment", "command_index": 1, "t": 0}, {"action": "split_segment", "command_index": 1, "t": 1},
                          {"action": "split_segment", "command_index": 1, "t": "half"}, {"action": "split_segment", "command_index": 1, "t": 0.5, "mirror": "symmetric"},
                          {"action": "remove_command", "command_index": 1, "t": 0.5}):
            with self.subTest(operation=operation), self.assertRaises(AnimationError):
                edit_path(artwork("M0 0L1 1Z"), "p", [operation])

    def test_mirrored_handles(self) -> None:
        svg = artwork("M0 0C0 10 10 10 10 0C10 -10 20 -10 20 0")

        def edit(command_index: int, point_index: int, x: float, y: float, mirror: object) -> list[dict[str, object]]:
            return edit_path(svg, "p", [{"action": "set_point", "command_index": command_index, "point_index": point_index, "x": x, "y": y, "mirror": mirror}])["commands"]

        self.assertEqual(edit(1, 1, 5, 10, "symmetric")[2]["points"][0], [15, -10])
        aligned = edit(2, 0, 15, -5, "aligned")[1]["points"][1]
        self.assertAlmostEqual(aligned[0], 10 - 50 ** 0.5)
        self.assertAlmostEqual(aligned[1], 50 ** 0.5)
        self.assertEqual(edit(2, 0, 10, 0, "aligned")[1]["points"][1], [10, 10])
        for arguments in ((1, 1, 0, 0, "bad"), (1, 2, 0, 0, "symmetric"), (2, 1, 0, 0, "symmetric"), (1, 0, 0, 0, "aligned")):
            with self.subTest(arguments=arguments), self.assertRaises(AnimationError):
                edit(*arguments)
        with self.assertRaisesRegex(AnimationError, "curveTo control point"):
            edit_path(artwork("M0 0L1 1"), "p", [{"action": "set_point", "command_index": 1, "point_index": 0, "x": 0, "y": 0, "mirror": "symmetric"}])


if __name__ == "__main__":
    unittest.main()
