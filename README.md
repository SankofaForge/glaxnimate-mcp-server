# Glaxnimate-compatible SVG animation MCP

This local MCP server inspects SVG artwork and adds SMIL keyframes to elements with stable IDs. It is designed for an LLM workflow: generate structured SVG, inspect its groups, add motion, then open the result in Glaxnimate or use it directly on the web.

Glaxnimate has a headless Python API in its source tree, but the published Python package is currently Windows-only. This server therefore uses portable SVG animation primitives instead of pretending to control a Glaxnimate installation that is not available. The generated SVG files remain editable in Glaxnimate.

## Tools

- `glaxnimate_inspect_svg` lists SVG IDs and the elements they refer to.
- `glaxnimate_animate_svg` adds SMIL animation for translation, rotation, scale, opacity, path morphs, and stroke-dashoffset.

`glaxnimate_animate_svg` returns both an animated SVG and the original SVG for reduced-motion handling. Use the static version when the host page detects `prefers-reduced-motion: reduce`.

## Install

This project requires Python 3.11 or newer. From a checkout of the repository, create a virtual environment and install the package:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Configure your MCP client to launch `glaxnimate-mcp` over stdio. For clients that accept a JSON configuration, the command is:

```json
{
  "command": "glaxnimate-mcp"
}
```

## Verification

Run the unit tests from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
