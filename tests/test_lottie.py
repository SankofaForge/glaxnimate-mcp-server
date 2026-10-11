from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from glaxnimate_mcp.lottie import _color, _numeric, _path, _transform_value, export_lottie
from glaxnimate_mcp.svg import AnimationError


def document(body: str, attributes: str = '') -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" {attributes}>{body}</svg>'


def channel(property: str, values: list[object], **options: object) -> dict[str, object]:
    return {'target_id': 'shape', 'property': property, 'values': values, **options}


def groups(result: dict[str, object]) -> list[dict[str, object]]:
    return result['lottie']['layers'][0]['shapes'][0]['it']


RECT = document('<rect id="shape" width="10" height="20"/>')


class LottieTests(unittest.TestCase):
    def test_path_contours_and_tangents(self) -> None:
        paths = _path('M0 0 L10 0 M20 20 C25 20 30 25 30 30 Z')
        self.assertEqual(paths[0], {'v': [[0, 0], [10, 0]], 'i': [[0, 0], [0, 0]], 'o': [[0, 0], [0, 0]], 'c': False})
        self.assertTrue(paths[1]['c'])
        self.assertEqual(paths[1]['o'][0], [5, 0])
        self.assertEqual(paths[1]['i'][1], [0, -5])
        closed = _path('M0 0 C10 0 10 10 0 0 Z')[0]
        self.assertEqual(closed['v'], [[0, 0]])
        self.assertEqual(closed['i'], [[10, 10]])
        self.assertTrue(_path('M0 0 Z')[0]['c'])
        quadratic = _path('M0 0 Q3 6 6 0')[0]
        self.assertEqual(quadratic['o'][0], [2, 4])
        self.assertEqual(quadratic['i'][1], [-2, 4])
        for value in ('', 'Mnot-a-path'):
            with self.subTest(value=value), self.assertRaises(AnimationError):
                _path(value)

    def test_static_stacking_and_inherited_style(self) -> None:
        svg = document('<title>Art</title><desc>Description</desc><metadata/><g id="group" fill="#abc" stroke="red" stroke-linecap="round" stroke-linejoin="bevel" fill-rule="evenodd"><rect id="back" width="4" height="5"/><circle id="front" r="2" fill="none"/></g>')
        result = export_lottie(svg, [], fps=24, duration_ms=2000)
        data = result['lottie']
        self.assertEqual(json.loads(result['json']), data)
        self.assertEqual((data['fr'], data['op'], data['w'], data['h']), (24, 48, 100, 100))
        self.assertFalse(result['output_written'])
        children = groups(result)[0]['it']
        self.assertEqual([item['nm'] for item in children[:-1]], ['front', 'back'])
        front, back = children[:2]
        self.assertEqual([item['ty'] for item in front['it']], ['sh', 'st', 'tr'])
        fill = next(item for item in back['it'] if item['ty'] == 'fl')
        stroke = next(item for item in back['it'] if item['ty'] == 'st')
        self.assertEqual(fill['c']['k'], [170 / 255, 187 / 255, 204 / 255])
        self.assertEqual(fill['r'], 2)
        self.assertEqual((stroke['lc'], stroke['lj']), (2, 3))
        self.assertEqual(export_lottie('<svg/>', [])['lottie']['w'], 512)

    def test_shape_geometry(self) -> None:
        for shape in ('<rect width="4" height="5"/>', '<circle r="2"/>', '<ellipse rx="2" ry="3"/>',
                      '<line x2="4" y2="5"/>', '<polyline points="0,0 4,5 8,0"/>',
                      '<polygon points="0,0 4,5 8,0"/>', '<path d="M0 0L4 5"/>'):
            with self.subTest(shape=shape):
                self.assertEqual(groups(export_lottie(document(shape), []))[0]['it'][0]['ty'], 'sh')

    def test_animated_paint_timing(self) -> None:
        result = export_lottie(RECT, [channel('fill', ['#fff', '#000'], begin_ms=100,
                                            duration_ms=900, calc_mode='spline', key_splines=[[0.2, 0.3, 0.7, 0.8]])])
        fill = groups(result)[0]['it'][1]['c']
        self.assertEqual(fill['a'], 1)
        self.assertEqual(fill['k'][0], {'t': 0, 's': [0, 0, 0], 'h': 1})
        self.assertEqual(fill['k'][1]['t'], 3)
        self.assertEqual(fill['k'][1]['o'], {'x': [0.2], 'y': [0.3]})
        result = export_lottie(RECT, [channel('opacity', [0, 1], begin_ms=100, duration_ms=900, calc_mode='discrete')])
        opacity = groups(result)[0]['it'][-1]['o']
        self.assertEqual(opacity['k'][0]['s'], [100])
        self.assertTrue(all(key['h'] == 1 for key in opacity['k']))
        svg = document('<rect id="shape" width="10" height="10" stroke="blue"/>')
        result = export_lottie(svg, [channel('stroke', ['red', 'green']), channel('fill-opacity', [0, 1]),
                                    channel('stroke-opacity', [0, 1]), channel('stroke-width', [1, 3])])
        paint = groups(result)[0]['it']
        self.assertEqual(paint[1]['o']['k'][-1]['s'], [100])
        self.assertEqual(paint[2]['w']['k'][-1]['s'], [3])

    def test_transform_replacement_and_addition(self) -> None:
        svg = document('<rect id="shape" width="10" height="10" transform="translate(3,4) scale(2) skewY(5)"/>')
        static = groups(export_lottie(svg, []))[0]
        self.assertEqual(static['it'][-1]['p']['k'], [3, 4])
        self.assertEqual(static['it'][0]['it'][-1]['s']['k'], [200, 200])
        self.assertEqual(static['it'][0]['it'][0]['it'][-1]['sa']['k'], 90)
        replaced = groups(export_lottie(svg, [channel('rotate', [0, 90])]))[0]
        self.assertEqual(replaced['it'][-1]['r']['a'], 1)
        self.assertEqual(replaced['it'][0]['nm'], 'shape')
        added = groups(export_lottie(svg, [channel('skewY', [0, 10], additive='sum')]))[0]
        self.assertEqual(added['it'][-1]['p']['k'], [3, 4])
        self.assertEqual(_transform_value('translate', '2'), [2, 0])
        self.assertEqual(_transform_value('scale', '2,3'), [200, 300])
        self.assertEqual(_transform_value('skewX', '10'), -10)
        with self.assertRaisesRegex(AnimationError, 'delayed replacing'):
            export_lottie(svg, [channel('rotate', [0, 90], begin_ms=500, duration_ms=500)])
        with self.assertRaises(AnimationError):
            _transform_value('rotate', '1 2')

    def test_rotation_pivots(self) -> None:
        for value, pivot in (('90', [0, 0]), ('90 10 20', [10, 20])):
            svg = document(f'<rect id="shape" width="10" height="20" transform="rotate({value})"/>')
            transform = groups(export_lottie(svg, []))[0]['it'][-1]
            self.assertEqual(transform['r']['k'], 90)
            self.assertEqual(transform['a']['k'], pivot)
            self.assertEqual(transform['p']['k'], pivot)
        result = export_lottie(RECT, [channel('rotate', ['0 10 20', '90 30 40'])])
        transform = groups(result)[0]['it'][-1]
        self.assertEqual(transform['a'], transform['p'])
        self.assertEqual(transform['a']['k'][0]['s'], [10, 20])
        self.assertEqual(transform['a']['k'][-1]['s'], [30, 40])
        self.assertEqual(transform['r']['k'][-1]['s'], [90])

    def test_path_morphs(self) -> None:
        svg = document('<path id="shape" d="M0 0L10 0"/>')
        result = export_lottie(svg, [channel('path', ['M0 0L10 0', 'M0 0L20 20'])])
        shape = groups(result)[0]['it'][0]['ks']
        self.assertEqual(shape['a'], 1)
        self.assertEqual(shape['k'][-1]['s'][0]['v'][-1], [20, 20])
        for value in ('M0 0L10 0L20 0', 'M0 0L10 0Z', 'M0 0L10 0M20 20L30 30'):
            with self.subTest(value=value), self.assertRaises(AnimationError):
                export_lottie(svg, [channel('path', ['M0 0L10 0', value])])
        with self.assertRaisesRegex(AnimationError, 'requires a path'):
            export_lottie(RECT, [channel('path', ['M0 0L10 0', 'M0 0L20 0'])])

    def test_validation_errors(self) -> None:
        for animations in (None, {}, [None], [channel('opacity', [0, 1])] * 101,
                           [channel('opacity', [0, 1])] * 2,
                           [channel('opacity', [0, 1], target_id='missing')],
                           [channel('x', [0, 1])], [channel('opacity', [0, 1], repeat_count=2)],
                           [channel('opacity', [0, 1], fill_mode='remove')],
                           [channel('opacity', [0, 1], duration_ms=2000)],
                           [channel('stroke', ['red', 'blue'])]):
            with self.subTest(animations=animations), self.assertRaises(AnimationError):
                export_lottie(RECT, animations)
        for body in ('<text>unsupported</text>', '<rect width="4" height="5" style="fill:red"/>',
                     '<rect width="4" height="5"><title>child</title></rect>', '<path/>',
                     '<rect width="bad" height="5"/>', '<rect width="4" height="5" fill-rule="bad"/>',
                     '<rect width="4" height="5" stroke="red" stroke-linecap="bad"/>',
                     '<rect width="4" height="5" stroke="red" stroke-linejoin="bad"/>',
                     '<rect width="4" height="5" transform="matrix(1 0 0 1 0 0)"/>'):
            with self.subTest(body=body), self.assertRaises(AnimationError):
                export_lottie(document(body), [])
        with self.assertRaises(AnimationError):
            export_lottie(document('', 'viewBox="1 0 100 100"'), [])
        with self.assertRaises(AnimationError):
            export_lottie(document('<g id="shape"/>'), [channel('fill', ['red', 'blue'])])
        for value in (None, '1px', float('inf')):
            with self.subTest(value=value), self.assertRaises(AnimationError):
                _numeric(value)
        with self.assertRaises(AnimationError):
            _color('url(#gradient)')
        with patch('glaxnimate_mcp.lottie.SVGPath.fromstring', side_effect=AssertionError):
            with self.assertRaisesRegex(AnimationError, 'invalid SVG geometry'):
                export_lottie(RECT, [])
