from __future__ import annotations

import base64
import struct
import unittest

from glaxnimate_mcp.lottie import _image_size, export_lottie
from glaxnimate_mcp.svg import AnimationError


def document(body: str, attributes: str = '') -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100" {attributes}>{body}</svg>'


def uri(kind: str, data: bytes) -> str:
    return f'data:image/{kind};base64,' + base64.b64encode(data).decode()


def paint(svg: str, kind: str = 'gf') -> dict[str, object]:
    items = export_lottie(svg, [])['lottie']['layers'][0]['shapes'][0]['it'][0]['it']
    return next(item for item in items if item['ty'] == kind)


PNG = uri('png', b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR' + struct.pack('>II', 4, 2))
SHAPE = '<rect id="shape" x="10" y="20" width="40" height="40" fill="url(#g)"/>'


def gradient(definition: str, shape: str = SHAPE) -> str:
    return document(f'<defs>{definition}</defs>{shape}')


class GradientTests(unittest.TestCase):
    def test_linear_bounding_box_and_stops(self) -> None:
        fill = paint(gradient('<linearGradient id="g" x2="50%"><stop offset="20%" stop-color="red"/><stop offset="0.1" stop-color="#00f" stop-opacity="2"/><stop offset="5" stop-color="#0f0" stop-opacity="0.5"/></linearGradient>'))
        self.assertEqual((fill['t'], fill['s']['k'], fill['e']['k']), (1, [10, 20], [30, 20]))
        self.assertEqual(fill['g']['p'], 3)
        self.assertEqual(fill['g']['k']['k'][:4], [0.2, 1, 0, 0])
        self.assertEqual(fill['g']['k']['k'][4], 0.2)
        self.assertEqual(fill['g']['k']['k'][-2:], [1, 0.5])
        self.assertEqual(fill['g']['k']['k'][-4:-2], [0.2, 1])
        self.assertEqual(fill['r'], 1)

    def test_single_opaque_stop_and_user_space(self) -> None:
        fill = paint(gradient('<linearGradient id="g" gradientUnits="userSpaceOnUse" x1="5" x2="50%" y2="25%"><stop stop-color="#fff"/></linearGradient>'))
        self.assertEqual(fill['g']['k']['k'], [0, 1, 1, 1, 1, 1, 1, 1])
        self.assertEqual((fill['s']['k'], fill['e']['k']), ([5, 0], [50, 25]))

    def test_radial_focus_and_stroke(self) -> None:
        stroke = paint(gradient('<radialGradient id="g" fx="50%" fy="25%"><stop stop-color="red"/></radialGradient>', '<circle id="shape" cx="50" cy="50" r="20" fill="none" stroke="url(#g)" stroke-width="3"/>'), 'gs')
        self.assertEqual((stroke['t'], stroke['s']['k'], stroke['e']['k']), (2, [50, 50], [70, 50]))
        self.assertAlmostEqual(stroke['h']['k'], 50)
        self.assertAlmostEqual(stroke['a']['k'], -90)
        self.assertEqual(stroke['w']['k'], 3)
        centered = paint(gradient('<radialGradient id="g" gradientUnits="userSpaceOnUse" r="50%"><stop stop-color="red"/></radialGradient>'))
        self.assertEqual((centered['s']['k'], centered['h']['k'], centered['a']['k']), ([50, 50], 0, 0))
        self.assertAlmostEqual(centered['e']['k'][0], 100)

    def test_gradient_rejections(self) -> None:
        cases = {
            'support geometry': '<linearGradient id="g" gradientTransform="rotate(9)"><stop/></linearGradient>',
            'known gradientUnits': '<linearGradient id="g" gradientUnits="bad"><stop/></linearGradient>',
            'spreadMethod': '<linearGradient id="g" spreadMethod="reflect"><stop/></linearGradient>',
            'must be stops': '<linearGradient id="g"><rect/></linearGradient>',
            'at least one stop': '<linearGradient id="g"/>',
            'square bounds': '<radialGradient id="g"><stop/></radialGradient>',
            'positive radius': '<radialGradient id="g" r="0"><stop/></radialGradient>',
            'inside the circle': '<radialGradient id="g" fx="100%"><stop/></radialGradient>',
        }
        shape = '<rect id="shape" width="40" height="20" fill="url(#g)"/>'
        for message, definition in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(AnimationError, message):
                export_lottie(gradient(definition, shape if message == 'square bounds' else SHAPE), [])
        with self.assertRaisesRegex(AnimationError, 'nonzero width'):
            export_lottie(gradient('<linearGradient id="g"><stop/></linearGradient>', '<line id="shape" x2="10" stroke="url(#g)"/>'), [])
        with self.assertRaisesRegex(AnimationError, 'static geometry'):
            export_lottie(gradient('<linearGradient id="g"><stop/></linearGradient>', '<path id="shape" d="M0 0H9V9Z" fill="url(#g)"/>'), [{'target_id': 'shape', 'property': 'path', 'values': ['M0 0H9V9Z', 'M0 0H5V5Z']}])
        for reference in ('url(#missing)', 'url(#shape)'):
            with self.subTest(reference=reference), self.assertRaisesRegex(AnimationError, 'identify a linear or radial'):
                export_lottie(document(f'<rect id="shape" width="4" height="4" fill="{reference}"/>'), [])
        with self.assertRaisesRegex(AnimationError, 'cannot apply'):
            export_lottie(gradient('<linearGradient id="g"><stop/></linearGradient>'), [{'target_id': 'shape', 'property': 'fill', 'values': ['red', 'blue']}])
        with self.assertRaisesRegex(AnimationError, 'rendered shapes'):
            export_lottie(gradient('<linearGradient id="g"><stop id="stop"/></linearGradient>'), [{'target_id': 'stop', 'property': 'opacity', 'values': [0, 1]}])


class ImageTests(unittest.TestCase):
    def test_image_headers(self) -> None:
        jpeg = b'\xff\xd8\xff\xe0' + struct.pack('>H', 4) + b'\0\0\xff\xc4' + struct.pack('>H', 2) + b'\xff\xc0' + struct.pack('>HBHH', 8, 8, 7, 6) + b'\0'
        riff = b'RIFF\0\0\0\0WEBP'
        cases = {
            PNG: (4, 2),
            uri('gif', b'GIF89a' + struct.pack('<HH', 3, 5)): (3, 5),
            uri('jpeg', jpeg): (6, 7),
            uri('webp', riff + b'VP8X' + bytes(8) + (8).to_bytes(3, 'little') + (9).to_bytes(3, 'little')): (9, 10),
            uri('webp', riff + b'VP8L' + bytes(4) + b'\x2f' + (10 | (11 << 14)).to_bytes(4, 'little') + bytes(5)): (11, 12),
            uri('webp', riff + b'VP8 ' + bytes(10) + struct.pack('<HH', 13 | 0xC000, 14)): (13, 14),
        }
        for value, size in cases.items():
            with self.subTest(size=size):
                self.assertEqual(_image_size(value), size)
        failures = {
            'data URIs': 'https://example.com/a.png',
            'valid base64': 'data:image/png;base64,abc',
            'dimensions': uri('png', b'not a png'),
        }
        failures |= {f'dimensions {index}': uri(kind, data) for index, (kind, data) in enumerate((
            ('gif', b'GIF89a' + struct.pack('<HH', 0, 5)), ('jpeg', b'\xff\xd8\xff\xe0'),
            ('webp', riff + b'ABCD' + bytes(14)), ('webp', b'RIFF')))}
        for message, value in failures.items():
            with self.subTest(message=message), self.assertRaisesRegex(AnimationError, message.split()[0]):
                _image_size(value)

    def test_image_layers_fit_and_parents(self) -> None:
        svg = document(f'<image id="photo" x="10" y="20" width="40" height="40" transform="translate(5 6) rotate(30)" opacity="0.5" xlink:href="{PNG}"/>')
        data = export_lottie(svg, [{'target_id': 'photo', 'property': 'scale', 'values': [1, 2], 'additive': 'sum'}])['lottie']
        self.assertEqual(data['assets'], [{'id': 'image_0', 'w': 4, 'h': 2, 'u': '', 'p': PNG, 'e': 1}])
        content, *parents = data['layers']
        self.assertEqual((content['ty'], content['refId'], content['nm']), (2, 'image_0', 'photo'))
        self.assertEqual(content['ks']['p']['k'], [10, 30])
        self.assertEqual(content['ks']['s']['k'], [1000, 1000])
        self.assertEqual(content['ks']['o']['k'], 50)
        self.assertEqual([layer['ty'] for layer in parents], [3, 3, 3])
        self.assertEqual(content['parent'], parents[-1]['ind'])
        self.assertEqual([layer.get('parent') for layer in parents], [None, parents[0]['ind'], parents[1]['ind']])
        self.assertEqual(parents[0]['ks']['p']['k'], [5, 6])
        self.assertEqual(parents[-1]['ks']['s']['a'], 1)
        for aspect, position, scale in (('none', [0, 0], [500, 1000]), ('xMinYMax meet', [0, 10], [500, 500]), ('xMaxYMin', [0, 0], [500, 500])):
            plain = document(f'<image width="20" height="20" preserveAspectRatio="{aspect}" href="{PNG}"/>')
            with self.subTest(aspect=aspect):
                layers = export_lottie(plain, [])['lottie']['layers']
                self.assertEqual(len(layers), 1)
                self.assertEqual((layers[0]['nm'], layers[0]['ks']['p']['k'], layers[0]['ks']['s']['k']), ('image', position, scale))
                self.assertNotIn('parent', layers[0])

    def test_image_rejections(self) -> None:
        cases = {
            'position, size': f'<image width="1" height="1" href="{PNG}" style="x"/>',
            'positive width': f'<image width="0" height="1" href="{PNG}"/>',
            'none or an alignment': f'<image width="1" height="1" href="{PNG}" preserveAspectRatio="xMidYMid slice"/>',
            'alignment with meet': f'<image width="1" height="1" href="{PNG}" preserveAspectRatio=""/>',
            'transforms and opacity': f'<image id="shape" width="1" height="1" href="{PNG}"/>',
            'direct children': f'<g><image width="1" height="1" href="{PNG}"/></g>',
        }
        for message, body in cases.items():
            animations = [{'target_id': 'shape', 'property': 'fill', 'values': ['red', 'blue']}] if 'opacity' in message else []
            with self.subTest(message=message), self.assertRaisesRegex(AnimationError, message):
                export_lottie(document(body), animations)


class MatteTests(unittest.TestCase):
    def test_clip_matte_order_and_transform(self) -> None:
        svg = document('<defs><clipPath id="c" transform="scale(2)" clip-rule="evenodd"><circle id="disc" r="5" fill="red" stroke="blue" opacity="0.2"/><rect width="3" height="3" clip-rule="nonzero"/></clipPath></defs>'
                       '<rect id="back" width="100" height="100"/><rect id="shape" width="50" height="50" transform="translate(3 4)" opacity="0.5" clip-path="url(#c)"/><rect id="front" width="5" height="5"/>', 'fill="blue" stroke="red"')
        tracks = [{'target_id': 'shape', 'property': 'translate', 'values': ['0 0', '9 9'], 'additive': 'sum'},
                  {'target_id': 'shape', 'property': 'opacity', 'values': [0, 1]},
                  {'target_id': 'disc', 'property': 'scale', 'values': [1, 2]}]
        layers = export_lottie(svg, tracks)['lottie']['layers']
        front, matte, content, back = layers
        self.assertEqual([layer['ty'] for layer in layers], [4, 4, 4, 4])
        self.assertEqual((matte['td'], content['tt'], content['nm']), (1, 1, 'shape'))
        self.assertEqual(front['shapes'][0]['nm'], 'front')
        self.assertEqual(back['shapes'][0]['nm'], 'back')
        self.assertEqual(content['shapes'][0]['it'][0]['it'][0]['it'][1]['c']['k'], [0, 0, 1])
        outer = matte['shapes'][0]
        self.assertEqual(outer['it'][-1]['p']['k'], [3, 4])
        self.assertEqual(outer['it'][0]['it'][-1]['p']['a'], 1)
        self.assertEqual(outer['it'][0]['it'][0]['it'][-1]['o']['k'], 100)
        clip = outer['it'][0]['it'][0]['it'][0]
        self.assertEqual(clip['it'][-1]['s']['k'], [200, 200])
        disc, square = clip['it'][0]['it'][1], clip['it'][0]['it'][0]
        self.assertEqual(disc['it'][-1]['s']['a'], 1)
        disc_paint = disc['it'][0]['it']
        self.assertEqual([item['ty'] for item in disc_paint], ['sh', 'fl', 'tr'])
        self.assertEqual((disc_paint[1]['c']['k'], disc_paint[1]['r'], disc_paint[2]['o']['k']), ([1, 1, 1], 2, 100))
        self.assertEqual(square['it'][1]['r'], 1)

    def test_mask_luma_matte_and_regions(self) -> None:
        for region in ('', 'x="-5" y="0" width="200" height="100"'):
            svg = document(f'<mask id="m" maskUnits="userSpaceOnUse" {region}><rect width="9" height="9"/></mask><rect width="9" height="9" mask="url(#m)"/>', 'fill="#808080"')
            with self.subTest(region=region):
                matte, content = export_lottie(svg, [])['lottie']['layers']
                self.assertEqual((matte['nm'], matte['td'], content['tt'], content['nm']), ('mask', 1, 3, 'artwork'))
                self.assertEqual(matte['shapes'][0]['it'][0]['it'][0]['it'][1]['c']['k'], [128 / 255] * 3)

    def test_matte_rejections(self) -> None:
        cases = {
            'reference a clipPath': '<rect width="1" height="1" clip-path="url(#missing)"/>',
            'reference a mask': '<clipPath id="c"/><rect width="1" height="1" mask="url(#c)"/>',
            'clipPathUnits': '<clipPath id="c" clipPathUnits="objectBoundingBox"/><rect width="1" height="1" clip-path="url(#c)"/>',
            'basic shapes': '<clipPath id="c"><text>x</text></clipPath><rect width="1" height="1" clip-path="url(#c)"/>',
            'maskUnits': '<mask id="m"/><rect width="1" height="1" mask="url(#m)"/>',
            'finite numbers': '<mask id="m" maskUnits="userSpaceOnUse" x="0"/><rect width="1" height="1" mask="url(#m)"/>',
            'cover the whole': '<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="50" height="100"/><rect width="1" height="1" mask="url(#m)"/>',
            'either clip-path or mask': '<rect width="1" height="1" clip-path="url(#c)" mask="url(#m)"/>',
            'without transform': '<rect width="1" height="1" mask="url(#m)"/>',
        }
        for message, body in cases.items():
            attributes = 'opacity="0.5"' if message == 'without transform' else ''
            with self.subTest(message=message), self.assertRaisesRegex(AnimationError, message):
                export_lottie(document(body, attributes), [])
        with self.assertRaisesRegex(AnimationError, 'rendered shapes'):
            export_lottie(document(f'<image width="1" height="1" href="{PNG}"/>', 'id="root"'), [{'target_id': 'root', 'property': 'opacity', 'values': [0, 1]}])
        with self.assertRaisesRegex(AnimationError, 'direct children'):
            export_lottie(document('<g><rect width="1" height="1" clip-path="url(#c)"/></g>'), [])


if __name__ == '__main__':
    unittest.main()
