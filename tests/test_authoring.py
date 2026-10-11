from __future__ import annotations

import unittest
import base64
from copy import deepcopy
from xml.etree import ElementTree as ET

from glaxnimate_mcp.authoring import create_svg, edit_svg
from glaxnimate_mcp.svg import AnimationError


SVG = '<svg xmlns="http://www.w3.org/2000/svg" id="root"><g id="a"><rect id="r"/><text id="t">old</text></g><g id="b"/></svg>'
NS = '{http://www.w3.org/2000/svg}'


def index(svg: str) -> dict[str, ET.Element]:
    return {node.get('id'): node for node in ET.fromstring(svg).iter() if node.get('id')}


class AuthoringTests(unittest.TestCase):
    def test_embedded_images_and_finite_attributes(self) -> None:
        for mime, data in (("png", b"\x89PNG\r\n\x1a\nfixture"), ("jpeg", b"\xff\xd8\xfffixture"), ("gif", b"GIF89afixture"), ("webp", b"RIFF\x00\x00\x00\x00WEBPfixture")):
            with self.subTest(mime=mime):
                href = f"data:image/{mime};base64," + base64.b64encode(data).decode()
                result = create_svg(100, 100, [{"type": "image", "id": "photo", "attributes": {"href": href}}])
                self.assertEqual(index(result["svg"])["photo"].get("href"), href)
        for href in ("data:image/png;base64,A", "data:image/png;base64," + base64.b64encode(b"bad").decode(), "data:image/webp;base64," + base64.b64encode(b"RIFFbad").decode(), "data:image/png;base64," + "A" * 1_000_001):
            with self.subTest(href=href[:30]), self.assertRaises(AnimationError):
                create_svg(100, 100, [{"type": "image", "id": "photo", "attributes": {"href": href}}])
        with self.assertRaises(AnimationError):
            create_svg(100, 100, [{"type": "rect", "id": "box", "attributes": {"x": float("nan")}}])

    def test_duplicate_preserves_local_references_and_stacking(self) -> None:
        source = SVG.replace('<rect id="r"/>', '<defs><linearGradient id="paint"/></defs><rect id="r" fill="url(#paint)"/><use id="local" href="#r"/><use id="external" href="#b"/>')
        result = edit_svg(source, [{"action": "duplicate", "target_id": "a", "id_prefix": "copy-"}])
        nodes = index(result["svg"])
        self.assertEqual([node.get("id") for node in nodes["root"]], ["a", "copy-a", "b"])
        self.assertEqual(nodes["copy-r"].get("fill"), "url(#copy-paint)")
        self.assertEqual(nodes["copy-local"].get("href"), "#copy-r")
        self.assertEqual(nodes["copy-external"].get("href"), "#b")
        self.assertEqual(nodes["r"].get("fill"), "url(#paint)")
        for prefix in (None, "bad prefix", ""):
            with self.subTest(prefix=prefix), self.assertRaises(AnimationError):
                edit_svg(SVG, [{"action": "duplicate", "target_id": "a", "id_prefix": prefix}])
        with self.assertRaisesRegex(AnimationError, "duplicate SVG id"):
            edit_svg(SVG, [{"action": "duplicate", "target_id": "a", "id_prefix": "copy-"}] * 2)

    def test_resize_and_attribute_removal(self) -> None:
        source = SVG.replace('<svg ', '<svg viewBox="0 0 100 100" ')
        result = edit_svg(source, [{"action": "resize", "width": 200, "height": 300}])
        root = ET.fromstring(result["svg"])
        self.assertEqual(root.get("viewBox"), "0 0 100 100")
        self.assertEqual((root.get("width"), root.get("height")), ("200", "300"))
        updated = edit_svg(source, [{"action": "update", "target_id": "root", "attributes": {"viewBox": "10 20 300 400"}}])
        self.assertEqual(ET.fromstring(updated["svg"]).get("viewBox"), "10 20 300 400")
        result = edit_svg(SVG, [{"action": "update", "target_id": "r", "attributes": {"fill": "red", "r": 2}, "remove_attributes": ["fill", "missing"]}])
        self.assertNotIn("fill", index(result["svg"])["r"].attrib)
        for removed in (None, "fill", [1], ["bad name"], ["id"]):
            with self.subTest(removed=removed), self.assertRaises(AnimationError):
                edit_svg(SVG, [{"action": "update", "target_id": "r", "remove_attributes": removed}])

    def test_create_artwork_and_escape_xml(self) -> None:
        elements = [
            {'type': 'defs', 'id': 'defs', 'children': [
                {'type': 'linearGradient', 'id': 'gradient', 'children': [
                    {'type': 'stop', 'id': 'start', 'attributes': {'offset': 0, 'stop-color': '#fff'}},
                    {'type': 'stop', 'id': 'end', 'attributes': {'offset': 1, 'stop-color': '#000'}},
                ]},
                {'type': 'mask', 'id': 'mask', 'children': [
                    {'type': 'circle', 'id': 'cutout', 'attributes': {'r': 4.5}},
                ]},
                {'type': 'filter', 'id': 'blur', 'children': [
                    {'type': 'feGaussianBlur', 'id': 'kernel', 'attributes': {'stdDeviation': 2}},
                ]},
            ]},
            {'type': 'rect', 'id': 'shape', 'attributes': {
                'fill': 'url(#gradient)', 'mask': 'url(#mask)', 'filter': 'url(#blur)',
            }},
            {'type': 'text', 'id': 'label', 'text': '<hello> & "world"',
             'attributes': {'aria-label': '<tag> & "quote"'}},
            {'type': 'use', 'id': 'copy', 'attributes': {'href': '#shape'}},
        ]
        original = deepcopy(elements)
        result = create_svg(200, 100.5, elements)
        root = ET.fromstring(result['svg'])
        nodes = index(result['svg'])
        self.assertEqual(root.attrib, {'width': '200', 'height': '100.5', 'viewBox': '0 0 200 100.5'})
        self.assertEqual(nodes['shape'].get('fill'), 'url(#gradient)')
        self.assertEqual(nodes['kernel'].tag, NS + 'feGaussianBlur')
        self.assertEqual(nodes['label'].text, '<hello> & "world"')
        self.assertEqual(nodes['label'].get('aria-label'), '<tag> & "quote"')
        self.assertEqual(nodes['copy'].get('href'), '#shape')
        self.assertFalse(result['output_written'])
        self.assertEqual(elements, original)
        self.assertEqual(len(ET.fromstring(create_svg(1, 1, [])['svg'])), 0)

    def test_invalid_elements_and_attributes(self) -> None:
        base = {'type': 'rect', 'id': 'shape'}
        bad_elements = [None, [], {}, base | {'type': 1}, base | {'type': 'script'},
                        base | {'id': None}, base | {'id': 'has space'},
                        base | {'attributes': []}, base | {'text': 'no'},
                        base | {'type': 'text', 'text': 1},
                        base | {'children': {}}, base | {'children': [base] * 101}]
        for attributes in ({1: 'x'}, {'bad:name': 'x'}, {'onload': 'x'}, {'OnClick': 'x'},
                           {'style': 'x'}, {'xmlns': 'x'}, {'fill': None}, {'fill': True},
                           {'href': 'https://example.com'}, {'id': 'other'}):
            bad_elements.append(base | {'attributes': attributes})
        for element in bad_elements:
            with self.subTest(element=element), self.assertRaises(AnimationError):
                create_svg(10, 10, [element])
        for elements in (None, (), [base] * 101):
            with self.subTest(elements=elements), self.assertRaises(AnimationError):
                create_svg(10, 10, elements)
        for width, height in ((True, 1), (0, 1), (1, 100001), (float('nan'), 1)):
            with self.subTest(width=width, height=height), self.assertRaises(AnimationError):
                create_svg(width, height, [])
        with self.assertRaisesRegex(AnimationError, 'duplicate SVG id'):
            create_svg(1, 1, [base, base])

    def test_nesting_limit(self) -> None:
        element = {'type': 'g', 'id': 'leaf'}
        for depth in range(32):
            element = {'type': 'g', 'id': f'g{depth}', 'children': [element]}
        self.assertIn('leaf', create_svg(1, 1, [element])['svg'])
        with self.assertRaisesRegex(AnimationError, 'nesting'):
            create_svg(1, 1, [{'type': 'g', 'id': 'extra', 'children': [element]}])

    def test_ordered_edits_and_input_preservation(self) -> None:
        operations = [
            {'action': 'insert', 'element': {'type': 'g', 'id': 'new'}},
            {'action': 'insert', 'parent_id': 'new', 'element': {'type': 'circle', 'id': 'c'}},
            {'action': 'update', 'target_id': 'c', 'attributes': {'r': 9}},
            {'action': 'update', 'target_id': 't', 'text': '<new> & text'},
            {'action': 'move', 'target_id': 'r', 'parent_id': 'new', 'index': 0},
            {'action': 'move', 'target_id': 't'},
            {'action': 'remove', 'target_id': 'a'},
        ]
        original = deepcopy(operations)
        result = edit_svg(SVG, operations)
        nodes = index(result['svg'])
        self.assertEqual([node.get('id') for node in nodes['new']], ['r', 'c'])
        self.assertEqual([node.get('id') for node in nodes['root']], ['b', 'new', 't'])
        self.assertEqual(nodes['c'].get('r'), '9')
        self.assertEqual(nodes['t'].text, '<new> & text')
        self.assertNotIn('a', nodes)
        self.assertFalse(result['output_written'])
        self.assertEqual(operations, original)
        self.assertEqual(index(SVG)['t'].text, 'old')

    def test_move_within_parent(self) -> None:
        result = edit_svg(SVG, [{'action': 'move', 'target_id': 'r', 'parent_id': 'a'}])
        self.assertEqual([node.get('id') for node in index(result['svg'])['a']], ['t', 'r'])

    def test_invalid_edits(self) -> None:
        operations = [None, [], {}, [None]]
        operations.extend([[operation] for operation in [
            {'action': 'insert', 'parent_id': 'missing', 'element': {}},
            {'action': 'insert', 'element': {'type': 'rect', 'id': 'r'}},
            {'action': 'update', 'target_id': 'missing'},
            {'action': 'remove', 'target_id': 'root'},
            {'action': 'update', 'target_id': 'r', 'attributes': {'id': 'changed'}},
            {'action': 'update', 'target_id': 'r', 'text': 'invalid'},
            {'action': 'update', 'target_id': 't', 'text': None},
            {'action': 'unknown', 'target_id': 'r'},
        ]])
        operations.append([{'action': 'update', 'target_id': 'r'}] * 101)
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(AnimationError):
                edit_svg(SVG, operation)
        for destination in ('missing', 'a', 'r'):
            with self.subTest(destination=destination), self.assertRaises(AnimationError):
                edit_svg(SVG, [{'action': 'move', 'target_id': 'a', 'parent_id': destination}])
        for position in (True, '0', -1, 1):
            with self.subTest(position=position), self.assertRaises(AnimationError):
                edit_svg(SVG, [{'action': 'move', 'target_id': 'r', 'parent_id': 'b', 'index': position}])

    def test_failed_batch_has_no_partial_effect(self) -> None:
        operations = [
            {'action': 'update', 'target_id': 't', 'text': 'changed'},
            {'action': 'remove', 'target_id': 'missing'},
        ]
        original = deepcopy(operations)
        with self.assertRaises(AnimationError):
            edit_svg(SVG, operations)
        self.assertEqual(operations, original)
        self.assertEqual(index(SVG)['t'].text, 'old')
        result = edit_svg(SVG, [{'action': 'update', 'target_id': 'r'}])
        self.assertEqual(index(result['svg'])['t'].text, 'old')
