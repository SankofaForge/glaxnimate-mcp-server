"""Generate native-player validation fixtures in an explicit Linux scratch path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from glaxnimate_mcp.mobile import export_mobile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('scratch', type=Path)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('mobile fixtures must be generated on the Linux verification host')
    destination = args.scratch.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect id="shape" x="10" y="10" width="30" height="30" fill="#ff0000"/></svg>'
    animations = [{'target_id': 'shape', 'property': 'translate', 'values': ['0 0', '40 0']}]
    outputs: dict[Path, str] = {}
    for platform in ('react-native', 'flutter'):
        result = export_mobile(svg, animations, platform)
        path = destination / ('lib' if platform == 'flutter' else 'react-native') / result['filename']
        outputs[path] = result['source']
    outputs[destination / 'pubspec.yaml'] = '''name: mobile_export_smoke
publish_to: none
environment:
  sdk: '>=3.6.0 <4.0.0'
dependencies:
  flutter:
    sdk: flutter
  lottie: ^3.3.2
dev_dependencies:
  flutter_test:
    sdk: flutter
'''
    outputs[destination / 'test' / 'widget_test.dart'] = '''import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lottie/lottie.dart';
import 'package:mobile_export_smoke/SvgAnimation.dart';

void main() {
  testWidgets('generated animation loads its composition', (tester) async {
    await tester.pumpWidget(const Directionality(
      textDirection: TextDirection.ltr,
      child: SvgAnimation(animate: false, repeat: false, width: 100, height: 100),
    ));
    await tester.pumpAndSettle();
    expect(find.byType(Lottie), findsOneWidget);
    expect(tester.takeException(), isNull);
    final player = tester.widget<Lottie>(find.byType(Lottie));
    expect(player.composition, isNotNull);
    expect(player.composition!.duration.inMilliseconds, 1000);
    expect(player.composition!.layers, isNotEmpty);
  });
}
'''
    for path in outputs:
        if path.exists():
            parser.error(f'fixture already exists: {path}')
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(json.dumps({'generated_files': [str(path.relative_to(destination)) for path in outputs]}))


if __name__ == '__main__':
    main()
