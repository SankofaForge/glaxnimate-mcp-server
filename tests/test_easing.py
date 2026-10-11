from __future__ import annotations

import unittest
from copy import deepcopy
from xml.etree import ElementTree as ET

from glaxnimate_mcp.easing import PRESETS, _cubic, bake_animation
from glaxnimate_mcp.svg import AnimationError, MAX_KEYFRAMES, animate_svg


SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="shape"/></svg>'
BASE = {'target_id': 'shape', 'property': 'opacity', 'values': [0, 1]}


class EasingTests(unittest.TestCase):
    def test_exact_step_jump_modes(self) -> None:
        expected = {'end': [0, 0.25, 0.5, 0.75, 1], 'start': [0.25, 0.5, 0.75, 1, 1],
                    'none': [0, 1 / 3, 2 / 3, 1, 1], 'both': [0.2, 0.4, 0.6, 0.8, 1]}
        for jump, values in expected.items():
            with self.subTest(jump=jump):
                result = bake_animation(BASE | {'easing': {'type': 'steps', 'steps': 4, 'jump': jump}})
                self.assertEqual(result['calc_mode'], 'discrete')
                self.assertEqual(result['key_times'], [0, 0.25, 0.5, 0.75, 1])
                for actual, wanted in zip(result['values'], values):
                    self.assertAlmostEqual(float(actual), wanted)
        result = bake_animation(BASE | {'easing': {'type': 'steps', 'steps': 1}})
        self.assertEqual(result['values'], ['0', '1'])

    def test_multisegment_step_seams(self) -> None:
        for jump, expected in (('end', [0, 5, 10, 20, 30]), ('start', [5, 10, 20, 30, 30]),
                               ('none', [0, 10, 10, 30, 30]), ('both', [10 / 3, 20 / 3, 50 / 3, 70 / 3, 30])):
            with self.subTest(jump=jump):
                result = bake_animation(BASE | {'values': [0, 10, 30], 'key_times': [0, 0.25, 1],
                                               'easing': {'type': 'steps', 'steps': 2, 'jump': jump}})
                self.assertEqual(result['key_times'], [0, 0.125, 0.25, 0.625, 1])
                for actual, wanted in zip(result['values'], expected):
                    self.assertAlmostEqual(float(actual), wanted)

    def test_continuous_presets_cubic_and_overshoot(self) -> None:
        self.assertAlmostEqual(_cubic(0.5, [0, 0, 1, 1]), 0.5)
        for name in PRESETS:
            with self.subTest(name=name):
                result = bake_animation(BASE | {'easing': {'name': name, 'samples': 20}})
                self.assertEqual(result['calc_mode'], 'linear')
                self.assertEqual((result['values'][0], result['values'][-1]), ('0', '1'))
                self.assertEqual(len(result['values']), 21)
        back = bake_animation(BASE | {'easing': {'name': 'back-out', 'samples': 20}})
        self.assertGreater(max(map(float, back['values'])), 1)
        back_in = bake_animation(BASE | {'easing': {'name': 'back-in', 'samples': 20}})
        self.assertLess(min(map(float, back_in['values'])), 0)
        curve = bake_animation(BASE | {'easing': {'type': 'cubic', 'curve': [0.25, 0.1, 0.25, 1], 'samples': 4}})
        preset = bake_animation(BASE | {'easing': {'name': 'ease', 'samples': 4}})
        self.assertEqual(curve['values'], preset['values'])
        self.assertGreater(float(curve['values'][2]), 0.5)

    def test_bounce_elastic_and_vector_interpolation(self) -> None:
        for kind in ('bounce-out', 'elastic-out'):
            result = bake_animation(BASE | {'easing': {'type': kind, 'samples': 100}})
            self.assertEqual((result['values'][0], result['values'][-1]), ('0', '1'))
            values = list(map(float, result['values']))
            self.assertTrue(any(left > right for left, right in zip(values, values[1:])))
            if kind == 'elastic-out':
                self.assertGreater(max(values), 1)
        spec = BASE | {'property': 'translate', 'values': ['10,20', '30 60', '50 80'],
                       'key_times': [0, 0.25, 1], 'easing': {'samples': 2}}
        original = deepcopy(spec)
        result = bake_animation(spec)
        self.assertEqual(result['values'], ['10 20', '20 40', '30 60', '40 70', '50 80'])
        self.assertEqual(result['key_times'], [0, 0.125, 0.25, 0.625, 1])
        self.assertNotIn('easing', result)
        self.assertEqual(spec, original)

    def test_svg_integration_preserves_baked_timeline(self) -> None:
        for easing, mode in (({'type': 'steps', 'steps': 4}, 'discrete'), ({'name': 'ease-out', 'samples': 4}, 'linear')):
            spec = BASE | {'easing': easing}
            expected = bake_animation(spec)
            svg = animate_svg(SVG, [spec])['animated_svg']
            animation = ET.fromstring(svg).find('.//{http://www.w3.org/2000/svg}animate')
            self.assertIsNotNone(animation)
            self.assertEqual(animation.get('calcMode'), mode)
            self.assertEqual(animation.get('values').split(';'), expected['values'])
            self.assertEqual(list(map(float, animation.get('keyTimes').split(';'))), expected['key_times'])

    def test_keyframe_budget(self) -> None:
        result = bake_animation(BASE | {'values': list(range(100)), 'easing': {'samples': 511}})
        self.assertLessEqual(len(result['values']), MAX_KEYFRAMES)
        self.assertEqual(result['values'][-1], '99')
        self.assertEqual(result['key_times'][-1], 1)
        result = bake_animation(BASE | {'values': list(range(MAX_KEYFRAMES)), 'easing': {}})
        self.assertEqual(len(result['values']), MAX_KEYFRAMES)
        with self.assertRaisesRegex(AnimationError, 'keyframe limit'):
            bake_animation(BASE | {'values': list(range(10)), 'easing': {'type': 'steps', 'steps': 100}})

    def test_motion_path_easing_keeps_numeric_progress(self) -> None:
        spec = BASE | {'property': 'motion-path', 'motion_path': 'M0 0L80 0',
                       'motion_rotate': 0, 'easing': {'name': 'ease-out', 'samples': 4}}
        result = bake_animation(spec)
        self.assertTrue(all(isinstance(value, float) for value in result['values']))
        self.assertGreater(result['values'][2], 0.5)
        exported = ET.fromstring(animate_svg(SVG, [spec])['animated_svg'])
        animation = exported.find('.//{*}animateMotion')
        self.assertEqual(animation.get('path'), 'M0 0L80 0')
        self.assertEqual(len(animation.get('keyPoints').split(';')), 5)
        with self.assertRaisesRegex(AnimationError, 'one numeric progress'):
            bake_animation(spec | {'values': ['0 0', '1 1']})
        with self.assertRaisesRegex(AnimationError, 'between 0 and 1'):
            animate_svg(SVG, [spec | {'easing': {'name': 'back-out'}}])

    def test_validation_errors(self) -> None:
        invalid = [BASE | {'easing': None}, BASE | {'easing': {'unknown': True}},
                   BASE | {'easing': {}, 'calc_mode': 'discrete'}, BASE | {'easing': {}, 'key_splines': []},
                   BASE | {'easing': {}, 'values': ['0px', '1px']},
                   BASE | {'easing': {}, 'values': ['0 1', '1']},
                   BASE | {'easing': {}, 'values': ['nan', '1']}]
        for easing in ({'samples': True}, {'samples': 1}, {'samples': 512}, {'samples': 2.5},
                       {'type': 'steps', 'steps': True}, {'type': 'steps', 'steps': 0},
                       {'type': 'steps', 'steps': 101}, {'type': 'steps', 'steps': 1, 'jump': 'none'},
                       {'type': 'steps', 'steps': 2, 'jump': 'bad'}, {'name': 'unknown'},
                       {'type': 'cubic', 'curve': [0, 1]}, {'type': 'cubic', 'curve': [-1, 0, 1, 1]},
                       {'type': 'cubic', 'curve': [0, 11, 1, 1]}, {'type': 'unknown'}):
            invalid.append(BASE | {'easing': easing})
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(AnimationError):
                bake_animation(spec)
