# Glaxnimate-compatible SVG animation MCP

This local MCP server creates, edits, animates, and exports SVG artwork through agent tools. It uses SVG primitives and local rendering backends. It does not control the native Glaxnimate application or guarantee that Glaxnimate imports every exported animation.

The SVGator comparison is ongoing. [PARITY.md](PARITY.md) records implemented features, restrictions, and remaining work. `glaxnimate_capabilities` reports `svgator_parity: false` until the required comparisons pass.

## Tools

| Tool | Purpose |
| --- | --- |
| `glaxnimate_capabilities` | Discover properties, limits, and formats |
| `glaxnimate_create_svg` | Create shapes, groups, text, gradients, masks, clipping, filters, and embedded raster images |
| `glaxnimate_edit_svg` | Insert, update, remove, move, duplicate, or resize artwork |
| `glaxnimate_inspect_svg` | List artwork IDs and structure |
| `glaxnimate_edit_path` | Inspect normalized path commands, move points, split segments, and remove nodes |
| `glaxnimate_animate_svg` | Add SMIL keyframes, easing, and motion paths |
| `glaxnimate_set_filters` | Create an ordered chain of eleven filter types |
| `glaxnimate_create_project` | Create portable artwork and timeline data |
| `glaxnimate_edit_project` | Edit artwork, tracks, keyframes, timing, and playback in one transaction |
| `glaxnimate_inspect_project` | Validate saved project data and inspect its timeline |
| `glaxnimate_text_to_path` | Shape supplied font data and return text outlines |
| `glaxnimate_combine_shapes` | Union, subtract, intersect, or exclude static sibling shapes |
| `glaxnimate_export_svg` | Export a standalone JavaScript SVG player |
| `glaxnimate_export_static` | Export base artwork or one sampled frame, with responsive sizing and optional short IDs |
| `glaxnimate_export_css` | Export supported channels as CSS keyframes |
| `glaxnimate_export_lottie` | Export supported artwork as vector Lottie JSON |
| `glaxnimate_export_mobile` | Generate a React Native component or Flutter widget using a Lottie player |
| `glaxnimate_export_media` | Render PNG, GIF, APNG, WebP, MP4, WebM, MOV, AVI, MKV, or a ZIP of PNG frames |

Tools return data; they do not save deliverable files or contact SVGator. Project tools return versioned JSON. Clients can store snapshots for save/load and undo/redo. Existing inspect and animation tools retain their `dry_run` option.

SVG edits preserve IDs. Duplicate prefixes subtree IDs and rewrites local references. Removing artwork that an animation track uses makes a project transaction fail unless the same transaction removes or retargets that track.

Path editing returns absolute commands in the element's coordinate system. Arcs and quadratic curves become cubic curves. `set_point` changes a command endpoint or control point by index; IDs, transforms, and paint stay intact. Pass `mirror: "symmetric"` or `mirror: "aligned"` with a curve handle to keep the node smooth: symmetric mirrors the opposite handle exactly, and aligned keeps its length but makes it collinear. `split_segment` inserts a node at parameter `t` without changing the shape. `remove_command` deletes a line or curve along with its end node. Operations run in order, so each index refers to the commands left by earlier operations. This tool currently requires artwork without stylesheets, scripts, or native animation elements.

Project edits include `set_keyframe`, `remove_keyframe`, and `set_interval_easing`. Keyframe `time` is normalized from 0 to 1 within its track. Setting an existing time changes its value; other times insert a keyframe. Removal preserves the endpoints. Insertion and removal require linear or discrete tracks without global easing. For eased tracks, replace the complete timeline through `update_track`. Existing keyframe values can still be updated individually.

Animations accept `calc_mode` (`linear`, `discrete`, or `spline`). Spline interpolation requires one `key_splines` entry per interval: `[x1, y1, x2, y2]`, with all coordinates between 0 and 1. SMIL splines cannot express overshoot curves with coordinates outside that range.

Set `repeat_count` to `"indefinite"` for a continuous SMIL loop. Set `fill_mode` to `"remove"` to restore the base value after playback, or use the default `"freeze"`. Transform animations accept `additive: "sum"` to compose with the underlying transform. The default remains `"replace"`.

Numeric channels can use `easing: {"type":"preset","name":"back-out"}` or a cubic curve with overshoot. Continuous easing is a piecewise linear approximation with 60 samples per interval by default, capped at 512 keyframes per channel. `easing: {"type":"steps","steps":4,"jump":"end"}` produces discrete keyframes. Jump modes are `start`, `end`, `none`, and `both`. These easing options currently require numeric values without units; they do not interpolate colors or path coordinates.

JavaScript playback supports load, hover, click, scroll into view, and programmatic triggers. Options include direction, alternation, iterations, speed, hover exit, and second-click behavior. Access the player as `document.getElementById(root_id).glaxnimatePlayer`. Its API includes `play`, `pause`, `restart`, `reverse`, `reset`, `seek` in milliseconds, `setSpeed`, and `destroy`. Inline copies need distinct root IDs. The API is not a drop-in SVGator Player API replacement.

CSS export supports load or hover with freeze/reset behavior. It requires channels to start at zero, freeze at completion, and repeat once; global playback settings handle iterations. It rejects unsupported channels or triggers. JavaScript and CSS exports honor reduced motion. Native mobile components leave interactions and reduced motion to their host application.

Lottie and mobile exports support shapes, groups, transforms, opacity, strokes, compatible path morphs, and static or animated rotation pivots. Rotation values accept an angle or `angle x y`. Fills and strokes can be solid colors or static linear and radial gradients, including stop opacity and radial focal points. Embedded PNG, JPEG, GIF, and WebP images become image layers; transforms on an image become parent null layers. `clip-path` and luminance `mask` become track mattes. Images, clips, and masks have to be direct children of the root `<svg>`, because each one needs its own layer. The exporter rejects fonts, filters, patterns, gradient transforms, animated gradient stops, and unsupported attributes rather than dropping them. Text outlines can be inserted as paths before export. Mobile output uses `lottie-react-native` or Flutter's `lottie` package; it is not SVGator's generated runtime.

Static SVG export returns base artwork by default. Pass `animations` and `time_ms` to export a single frame instead: each channel is evaluated with SMIL timing (begin, repeats, fill mode, discrete, linear, and spline interpolation, additive transforms, and motion paths) and written into plain attributes. It removes native animation elements and scripts and rejects stylesheets and inline styles. Responsive output retains a viewBox and removes fixed dimensions. Optional short IDs update local href, URL, and accessibility references. This export is not an embedding sanitizer.

All local exports work without a SVGator account or subscription. SVGator access is only used for authorized reference research and comparisons.

`glaxnimate_animate_svg` returns both an animated SVG and the original SVG for reduced-motion handling. Use the static version when the host page detects `prefers-reduced-motion: reduce`.

Supplied SVG is not sanitized for embedding in an untrusted page. Local raster/video rendering disables scripts and network requests, uses a temporary directory, and returns base64 bytes. A render is limited to 500 million sampled pixels and 20 MB of encoded output. Optional playback settings apply direction, speed, iteration, and alternation to sampled frames. Interactive triggers do not affect offline sampling.

## Install

This project requires Python 3.11 or newer. From a checkout of the repository, create a virtual environment and install the package:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Optional backends:

```bash
python -m pip install '.[render,fonts,geometry]'
python -m playwright install chromium
```

Animated media needs FFmpeg on `PATH`. PNG and ZIP sequences only need Chromium. `GLAXNIMATE_CHROMIUM_PATH` selects an existing Chromium executable. Font outlines need the `fonts` extra and caller-supplied base64 TTF/OTF bytes. Boolean geometry needs the `geometry` extra.

Configure your MCP client to launch `glaxnimate-mcp` over stdio. For clients that accept a JSON configuration, the command is:

```json
{
  "command": "glaxnimate-mcp"
}
```

## Verification

Run the unit tests from the repository root:

```bash
python -m pip install '.[test]'
pytest -W error
```

The test suite requires 100% line and branch coverage. Additional checks are `tests/transport_smoke.py`, `tests/browser_smoke.py`, `tests/media_smoke.py`, `tests/lottie_smoke.py`, and `tests/mobile_smoke.py`. Browser checks require an explicit Chromium executable. Lottie rendering also requires an upstream `lottie-web` player script. Mobile fixture generation requires an explicit Linux scratch directory and refuses to overwrite existing fixtures.

## License

[MIT](LICENSE)
