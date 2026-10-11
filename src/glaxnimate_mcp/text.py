"""Shape supplied font data and convert a text run to SVG outlines."""

from __future__ import annotations

import base64
import binascii
import io

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont, TTLibError

from .svg import AnimationError, _number


def text_to_path(text: str, font_base64: str, font_size: float = 16, x: float = 0, y: float = 0, direction: str = "auto") -> dict[str, object]:
    """Shape one horizontal text run. Return outlines without reading local font files."""
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or "\n" in text or "\r" in text:
        raise AnimationError("text must contain 1 to 1000 characters on one line")
    if direction not in ("auto", "ltr", "rtl"):
        raise AnimationError("direction must be auto, ltr, or rtl")
    font_size = _number(font_size, "font_size", 0.1, 10_000)
    x = _number(x, "x", -1e6, 1e6)
    y = _number(y, "y", -1e6, 1e6)
    if not isinstance(font_base64, str) or not 1 <= len(font_base64) <= 7_000_000:
        raise AnimationError("font_base64 must contain at most 7 million characters")
    try:
        data = base64.b64decode(font_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise AnimationError("font_base64 must contain valid base64") from error
    if not 1 <= len(data) <= 5_000_000:
        raise AnimationError("font data must contain 1 to 5 million bytes")
    try:
        import uharfbuzz as hb
    except ImportError as error:
        raise AnimationError("install the fonts extra to convert text to outlines") from error
    try:
        with TTFont(io.BytesIO(data)) as font:
            face = hb.Face(data)
            shaped_font = hb.Font(face)
            shaped_font.scale = (face.upem, face.upem)
            buffer = hb.Buffer()
            buffer.add_str(text)
            buffer.guess_segment_properties()
            if direction != "auto":
                buffer.direction = direction
            hb.shape(shaped_font, buffer)
            glyphs = font.getGlyphSet()
            names = font.getGlyphOrder()
            pen = SVGPathPen(glyphs)
            scale = font_size / face.upem
            cursor_x, cursor_y = x, y
            for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
                if info.codepoint == 0:
                    raise AnimationError("the supplied font does not contain a required glyph")
                glyphs[names[info.codepoint]].draw(TransformPen(pen, (scale, 0, 0, -scale,
                    cursor_x + position.x_offset * scale, cursor_y - position.y_offset * scale)))
                cursor_x += position.x_advance * scale
                cursor_y -= position.y_advance * scale
            path = pen.getCommands()
            if len(path.encode()) > 1_000_000:
                raise AnimationError("text outlines exceed the one-million-byte limit")
            return {"d": path, "advance": {"x": cursor_x - x, "y": cursor_y - y},
                    "glyph_count": len(buffer.glyph_infos), "direction": buffer.direction,
                    "output_written": False}
    except (TTLibError, KeyError, IndexError, ValueError, ZeroDivisionError) as error:
        if isinstance(error, AnimationError):
            raise
        raise AnimationError("the supplied font cannot produce text outlines") from error
