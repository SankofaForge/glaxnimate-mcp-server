# Glaxnimate-compatible SVG animation MCP

This local MCP server inspects SVG artwork and adds SMIL keyframes to elements with stable IDs. It is designed for an LLM workflow: generate structured SVG, inspect its groups, add motion, then open the result in Glaxnimate or use it directly on the web.

Glaxnimate has a headless Python API in its source tree, but the published Python package is currently Windows-only. This server therefore uses portable SVG animation primitives instead of pretending to control a Glaxnimate installation that is not available. The generated SVG files remain editable in Glaxnimate.

## Tools

- `glaxnimate_inspect_svg` lists SVG IDs and the elements they refer to.
- `glaxnimate_animate_svg` adds SMIL animation for translation, rotation, scale, opacity, path morphs, and stroke-dashoffset.

`glaxnimate_animate_svg` returns both an animated SVG and the original SVG for reduced-motion handling. Use the static version when the host page detects `prefers-reduced-motion: reduce`.

## Local runtime

The configured clients launch this server on `ampere-dev` over SSH. That keeps Python dependencies and generated environment files off the Mac while making the same MCP tools available in Claude Code, Antigravity, and Codex.

## Verification

Run the unit tests through the VM wrapper:

```bash
verify-on-vm /absolute/path/to/glaxnimate-mcp-server "PYTHONPATH=src python -m unittest discover -s tests -v"
```

## License

[MIT](LICENSE)
