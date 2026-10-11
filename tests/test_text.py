from __future__ import annotations

import base64
import builtins
import io
import unittest
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from glaxnimate_mcp.lottie import _path
from glaxnimate_mcp.svg import AnimationError
from glaxnimate_mcp.text import text_to_path


def synthetic_font() -> str:
    builder = FontBuilder(1000, isTTF=True)
    names = ['.notdef', 'A', 'B', 'space']
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({65: 'A', 66: 'B', 32: 'space'})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != 'space':
            pen.moveTo((0, 0))
            pen.lineTo((400, 0))
            pen.lineTo((400, 700 if name == 'A' else 500))
            pen.lineTo((0, 700 if name == 'A' else 500))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (250 if name == 'space' else 600, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'OutlineFixture', 'styleName': 'Regular', 'uniqueFontIdentifier': 'OutlineFixture Regular', 'fullName': 'OutlineFixture Regular', 'psName': 'OutlineFixture-Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    output = io.BytesIO()
    builder.save(output)
    return base64.b64encode(output.getvalue()).decode('ascii')


class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font = synthetic_font()

    def test_outlines_baseline_spacing_and_advance(self) -> None:
        result = text_to_path('A B', self.font, font_size=100, x=10, y=80)
        paths = _path(result['d'])
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0]['v'], [[10, 80], [50, 80], [50, 10], [10, 10]])
        self.assertEqual(paths[1]['v'][0], [95, 80])
        self.assertEqual(result['advance'], {'x': 145, 'y': 0})
        self.assertEqual(result['glyph_count'], 3)
        self.assertEqual(result['direction'], 'ltr')
        self.assertFalse(result['output_written'])
        blank = text_to_path(' ', self.font, font_size=100)
        self.assertEqual(blank['d'], '')
        self.assertEqual(blank['advance']['x'], 25)

    def test_explicit_direction_changes_glyph_order(self) -> None:
        forward = text_to_path('AB', self.font, font_size=100, direction='ltr')
        reverse = text_to_path('AB', self.font, font_size=100, direction='rtl')
        self.assertEqual(forward['direction'], 'ltr')
        self.assertEqual(reverse['direction'], 'rtl')
        self.assertEqual(_path(forward['d'])[0]['v'][2], [40, -70])
        self.assertEqual(_path(reverse['d'])[0]['v'][2], [40, -50])
        self.assertEqual(reverse['advance'], forward['advance'])

    def test_invalid_text_and_options(self) -> None:
        for value in (None, '', 'A' * 1001, 'A\nB', 'A\rB'):
            with self.subTest(value=value), self.assertRaises(AnimationError):
                text_to_path(value, self.font)
        for options in ({'direction': 'vertical'}, {'font_size': 0}, {'x': float('nan')}, {'y': 1e7}):
            with self.subTest(options=options), self.assertRaises(AnimationError):
                text_to_path('A', self.font, **options)
        with self.assertRaisesRegex(AnimationError, 'required glyph'):
            text_to_path('Z', self.font)

    def test_invalid_fonts_and_size_limits(self) -> None:
        for value in (None, '', 'A' * 7_000_001, '@bad-base64', 'é', base64.b64encode(b'not a font').decode()):
            with self.subTest(value=str(value)[:30]), self.assertRaises(AnimationError):
                text_to_path('A', value)
        for decoded in (b'', b'a' * 5_000_001):
            with patch('glaxnimate_mcp.text.base64.b64decode', return_value=decoded):
                with self.assertRaisesRegex(AnimationError, 'font data'):
                    text_to_path('A', 'AAAA')
        with patch('glaxnimate_mcp.text.SVGPathPen.getCommands', return_value='M' * 1_000_001):
            with self.assertRaisesRegex(AnimationError, 'one-million-byte'):
                text_to_path('A', self.font)

    def test_missing_optional_dependency(self) -> None:
        original = builtins.__import__

        def importing(name: str, *args: object, **kwargs: object) -> object:
            if name == 'uharfbuzz':
                raise ImportError('font shaping dependency unavailable')
            return original(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=importing):
            with self.assertRaisesRegex(AnimationError, 'fonts extra'):
                text_to_path('A', self.font)
