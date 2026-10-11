"""Native-player component exports for supported vector Lottie artwork."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping, Sequence

from .lottie import export_lottie
from .svg import AnimationError


def export_mobile(svg: str, animations: Sequence[Mapping[str, object]], platform: str, component_name: str = "SvgAnimation", fps: float = 30, duration_ms: float = 1000) -> dict[str, object]:
    """Generate component source using the platform's Lottie runtime."""
    if platform not in ("react-native", "flutter"):
        raise AnimationError("platform must be react-native or flutter")
    if not isinstance(component_name, str) or not re.fullmatch(r"[A-Z][A-Za-z0-9]{0,63}", component_name):
        raise AnimationError("component_name must start with an uppercase letter and contain at most 64 letters or digits")
    result = export_lottie(svg, animations, fps, duration_ms)
    if platform == "react-native":
        source = (
            "import React from 'react';\nimport LottieView from 'lottie-react-native';\n\n"
            f"const animationData = {result['json']};\n\n"
            f"export default function {component_name}(props) {{\n"
            "  return React.createElement(LottieView, {source: animationData, autoPlay: true, loop: true, ...props});\n}\n"
        )
        extension, dependency = "js", "lottie-react-native"
    else:
        data = base64.b64encode(result["json"].encode()).decode("ascii")
        source = (
            "import 'dart:convert';\nimport 'package:flutter/widgets.dart';\nimport 'package:lottie/lottie.dart';\n\n"
            f"final _animationBytes = base64Decode('{data}');\n\n"
            f"class {component_name} extends StatelessWidget {{\n"
            f"  const {component_name}({{super.key, this.controller, this.animate = true, this.repeat = true, this.width, this.height}});\n"
            "  final Animation<double>? controller;\n  final bool animate;\n  final bool repeat;\n"
            "  final double? width;\n  final double? height;\n\n"
            "  @override\n  Widget build(BuildContext context) {\n"
            "    return Lottie.memory(_animationBytes, controller: controller, animate: animate, repeat: repeat, width: width, height: height);\n"
            "  }\n}\n"
        )
        extension, dependency = "dart", "lottie"
    return {"source": source, "filename": f"{component_name}.{extension}", "platform": platform,
            "dependencies": [dependency], "lottie": result["lottie"], "output_written": False}
