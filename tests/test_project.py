from __future__ import annotations

import json
import unittest
from copy import deepcopy

from glaxnimate_mcp.project import create_project, edit_project, inspect_project
from glaxnimate_mcp.svg import AnimationError


SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="first"/><circle id="second"/></svg>'
ANIMATION = {'target_id': 'first', 'property': 'opacity', 'values': [0, 1]}


class ProjectTests(unittest.TestCase):
    def test_create_and_restore_client_snapshot(self) -> None:
        created = create_project(SVG, duration_ms=2000, fps=24)
        snapshot = json.loads(created['json'])
        self.assertEqual(snapshot, created['project'])
        self.assertEqual(snapshot['version'], 1)
        self.assertEqual(snapshot['tracks'], [])
        self.assertEqual(snapshot['playback'], {})
        self.assertFalse(created['output_written'])
        changed = edit_project(snapshot, [{'action': 'add_track', 'id': 'fade', 'animation': ANIMATION}])
        restored = inspect_project(json.loads(created['json']))
        self.assertEqual(restored['tracks'], [])
        self.assertEqual(restored['animation_targets'], ['first', 'second'])
        self.assertEqual((restored['duration_ms'], restored['fps']), (2000, 24))
        self.assertFalse(restored['output_written'])
        self.assertEqual(changed['project']['tracks'][0]['animation'], ANIMATION)
        self.assertEqual(snapshot['tracks'], [])

    def test_atomic_track_edits_and_deep_copy(self) -> None:
        project = create_project(SVG)['project']
        operations = [
            {'action': 'add_track', 'id': 'fade', 'animation': ANIMATION},
            {'action': 'duplicate_track', 'id': 'fade', 'new_id': 'copy', 'target_id': 'second'},
            {'action': 'update_track', 'id': 'copy', 'animation': {'values': [1, 0.5, 0], 'key_times': [0, 0.25, 1]}},
            {'action': 'duplicate_track', 'id': 'fade', 'new_id': 'same_target'},
            {'action': 'remove_track', 'id': 'same_target'},
        ]
        original = deepcopy(operations)
        result = edit_project(project, operations)['project']
        fade, copy = result['tracks']
        self.assertEqual(fade['animation']['values'], [0, 1])
        self.assertEqual(copy['animation']['values'], [1, 0.5, 0])
        self.assertEqual(copy['animation']['key_times'], [0, 0.25, 1])
        self.assertEqual(copy['animation']['target_id'], 'second')
        self.assertEqual(project['tracks'], [])
        self.assertEqual(operations, original)
        copy['animation']['values'][0] = 0.75
        self.assertEqual(fade['animation']['values'], [0, 1])
        self.assertEqual(ANIMATION['values'], [0, 1])
        inspection = inspect_project(result)
        inspection['tracks'][0]['animation']['values'][0] = 0.5
        self.assertEqual(result['tracks'][0]['animation']['values'], [0, 1])
        empty = edit_project(result, [{'action': 'remove_track', 'id': 'fade'}, {'action': 'remove_track', 'id': 'copy'}])
        self.assertEqual(empty['project']['tracks'], [])

    def test_artwork_and_playback_settings(self) -> None:
        project = create_project(SVG)['project']
        playback = {'trigger': 'hover', 'direction': -1, 'alternate': True, 'iterations': 0, 'speed': 2, 'hover_out': 'reverse'}
        result = edit_project(project, [
            {'action': 'artwork', 'operations': [{'action': 'insert', 'element': {'type': 'path', 'id': 'new', 'attributes': {'d': 'M0 0L10 0'}}}]},
            {'action': 'settings', 'values': {'duration_ms': 2500, 'fps': 60, 'playback': playback}},
            {'action': 'add_track', 'id': 'late', 'animation': ANIMATION | {'target_id': 'new', 'begin_ms': 500, 'duration_ms': 2000}},
        ])['project']
        inspection = inspect_project(result)
        self.assertEqual(inspection['animation_targets'], ['first', 'second', 'new'])
        self.assertEqual((inspection['duration_ms'], inspection['fps']), (2500, 60))
        self.assertEqual(inspection['playback'], playback)
        result['playback']['speed'] = 3
        self.assertEqual(playback['speed'], 2)
        self.assertEqual(project['svg'], SVG)

    def test_invalid_project_schemas(self) -> None:
        project = create_project(SVG)['project']
        invalid = [None, [], {}, project | {'extra': 1}, project | {'version': 2},
                   project | {'tracks': [{'id': 'bad', 'animation': ANIMATION | {'values': [float('nan'), 1]}}]},
                   project | {'tracks': [{'id': 'bad', 'animation': ANIMATION | {'extra': object()}}]},
                   project | {'version': True}, project | {'version': 1.0},
                   project | {'playback': {'root_id': 'bad id'}},
                   {key: value for key, value in project.items() if key != 'svg'},
                   project | {'svg': 'invalid'}, project | {'fps': 0},
                   project | {'duration_ms': 0}, project | {'playback': {'trigger': 'invalid'}},
                   project | {'tracks': {}}, project | {'tracks': [None] * 101}]
        for tracks in ([None], [{'id': 'fade'}], [{'id': 1, 'animation': ANIMATION}],
                       [{'id': 'bad id', 'animation': ANIMATION}],
                       [{'id': 'fade', 'animation': ANIMATION}] * 2,
                       [{'id': 'fade', 'animation': None}],
                       [{'id': 'fade', 'animation': ANIMATION | {'target_id': 'missing'}}],
                       [{'id': 'fade', 'animation': ANIMATION | {'begin_ms': 1}}]):
            invalid.append(project | {'tracks': tracks})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(AnimationError):
                inspect_project(value)

    def test_invalid_operations_leave_original_unchanged(self) -> None:
        project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': ANIMATION}])['project']
        original = deepcopy(project)
        invalid = [None, [], {}, [None], [{'action': 'settings', 'values': {}}] * 101]
        for operation in (
            {'action': 'settings', 'values': None}, {'action': 'settings', 'values': {'svg': SVG}},
            {'action': 'settings', 'values': {'duration_ms': 1}},
            {'action': 'settings', 'values': {'playback': {'unsupported': True}}},
            {'action': 'remove_track', 'id': 'missing'}, {'action': 'unknown', 'id': 'fade'},
            {'action': 'update_track', 'id': 'fade', 'animation': None},
            {'action': 'update_track', 'id': 'fade', 'animation': {'values': [0]}},
            {'action': 'duplicate_track', 'id': 'fade', 'new_id': 'fade'},
            {'action': 'duplicate_track', 'id': 'fade', 'new_id': 'copy', 'target_id': 'missing'},
            {'action': 'artwork', 'operations': [{'action': 'remove', 'target_id': 'first'}]},
            {'action': 'add_track', 'id': 'bad', 'animation': None},
        ):
            invalid.append([{'action': 'settings', 'values': {'fps': 60}}, operation])
        for operations in invalid:
            with self.subTest(operations=operations), self.assertRaises(AnimationError):
                edit_project(project, operations)
            self.assertEqual(project, original)

    def test_non_json_animation_extras_are_rejected(self) -> None:
        project = create_project(SVG)['project']
        for value in (float('nan'), float('inf'), object()):
            with self.subTest(value=value), self.assertRaisesRegex(AnimationError, 'finite JSON'):
                edit_project(project, [{'action': 'add_track', 'id': 'fade', 'animation': ANIMATION | {'extra': value}}])
        self.assertEqual(project['tracks'], [])

    def test_keyframe_edits_preserve_precision_and_input(self) -> None:
        time = 0.123456789123
        project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': ANIMATION}])['project']
        original = deepcopy(project)
        inserted = edit_project(project, [
            {'action': 'set_keyframe', 'id': 'fade', 'time': time, 'value': 0.987654321123},
            {'action': 'set_keyframe', 'id': 'fade', 'time': 0, 'value': 0.25},
        ])['project']
        animation = inserted['tracks'][0]['animation']
        self.assertEqual(animation['key_times'], [0, time, 1])
        self.assertEqual(animation['values'], [0.25, 0.987654321123, 1])
        self.assertEqual(project, original)
        removed = edit_project(inserted, [{'action': 'remove_keyframe', 'id': 'fade', 'time': time}])['project']
        self.assertEqual(removed['tracks'][0]['animation']['key_times'], [0, 1])
        self.assertEqual(removed['tracks'][0]['animation']['values'], [0.25, 1])
        self.assertEqual(animation['key_times'], [0, time, 1])

    def test_interval_easing_and_existing_eased_keyframe(self) -> None:
        base = ANIMATION | {'values': [0, 0.5, 1]}
        project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': base}])['project']
        curve = [0.25, 0.1, 0.25, 1]
        edited = edit_project(project, [
            {'action': 'set_interval_easing', 'id': 'fade', 'index': 1, 'curve': curve},
            {'action': 'set_interval_easing', 'id': 'fade', 'index': 0, 'curve': [0.42, 0, 1, 1]},
            {'action': 'set_keyframe', 'id': 'fade', 'time': 0.5, 'value': 0.75},
        ])['project']
        animation = edited['tracks'][0]['animation']
        self.assertEqual(animation['calc_mode'], 'spline')
        self.assertEqual(animation['key_splines'], [[0.42, 0, 1, 1], curve])
        self.assertEqual(animation['values'], [0, 0.75, 1])
        curve[0] = 0.9
        self.assertEqual(animation['key_splines'][1][0], 0.25)
        for options in ({'easing': {'name': 'ease'}}, {'calc_mode': 'discrete'}):
            project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': base | options}])['project']
            result = edit_project(project, [{'action': 'set_keyframe', 'id': 'fade', 'time': 0.5, 'value': 0.9}])['project']
            self.assertEqual(result['tracks'][0]['animation']['values'], [0, 0.9, 1])
        discrete = edit_project(project, [{'action': 'set_keyframe', 'id': 'fade', 'time': 0.25, 'value': 0.1}, {'action': 'remove_keyframe', 'id': 'fade', 'time': 0.5}])['project']
        self.assertEqual(discrete['tracks'][0]['animation']['key_times'], [0, 0.25, 1])

    def test_invalid_keyframe_edits_are_atomic(self) -> None:
        base = ANIMATION | {'values': [0, 0.5, 1]}
        project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': base}])['project']
        original = deepcopy(project)
        operations = [
            {'action': 'remove_keyframe', 'time': 0}, {'action': 'remove_keyframe', 'time': 1},
            {'action': 'remove_keyframe', 'time': 0.25}, {'action': 'set_keyframe', 'time': -1, 'value': 0},
            {'action': 'set_keyframe', 'time': 0.5, 'value': True}, {'action': 'set_keyframe', 'time': 0.5, 'value': {}},
            {'action': 'set_keyframe', 'time': 0.5, 'value': '0;1'},
        ]
        operations.extend({'action': 'set_interval_easing', 'index': index, 'curve': [0, 0, 1, 1]} for index in (True, '0', -1, 2))
        operations.append({'action': 'set_interval_easing', 'index': 0, 'curve': [0, 0]})
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(AnimationError):
                edit_project(project, [{'action': 'settings', 'values': {'fps': 60}}, operation | {'id': 'fade'}])
            self.assertEqual(project, original)
        for options in ({'calc_mode': 'spline', 'key_splines': [[0, 0, 1, 1]] * 2}, {'easing': {'name': 'ease'}}):
            eased = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': base | options}])['project']
            for operation in ({'action': 'set_keyframe', 'time': 0.25, 'value': 0.2}, {'action': 'remove_keyframe', 'time': 0.5}):
                with self.subTest(options=options, operation=operation), self.assertRaisesRegex(AnimationError, 'complete values'):
                    edit_project(eased, [operation | {'id': 'fade'}])
        with self.assertRaisesRegex(AnimationError, 'global easing'):
            edit_project(eased, [{'action': 'set_interval_easing', 'id': 'fade', 'index': 0, 'curve': [0, 0, 1, 1]}])

    def test_keyframe_count_limit(self) -> None:
        from glaxnimate_mcp.svg import MAX_KEYFRAMES

        animation = ANIMATION | {'values': list(range(MAX_KEYFRAMES))}
        project = edit_project(create_project(SVG)['project'], [{'action': 'add_track', 'id': 'fade', 'animation': animation}])['project']
        with self.assertRaises(AnimationError):
            edit_project(project, [{'action': 'set_keyframe', 'id': 'fade', 'time': 0.00001, 'value': 1}])
        self.assertEqual(len(project['tracks'][0]['animation']['values']), MAX_KEYFRAMES)
