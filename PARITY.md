# SVGator comparison

The requested scope is local agent authoring and exports. Cloud storage, collaboration, and hosted rendering services are excluded. Full parity remains incomplete.

## Evidence

REA 6.4.0 inspected an authorized SVGator v4.11.7 editor session on 2026-10-11. The scoped bundle capture parsed seven application/CDN scripts, with 788,919 AST nodes and no parse failures. The subsequent application graph exhausted parts of its semantic analysis budget. Static source relationships establish candidate behavior, not runtime equivalence. Raw captures and application source remain outside this repository.

The editor script SHA-256 is `0a198a4b31a500bf333e806fc9523136f2a9bca46145d05f413ab5e42bad1610`. Evidence offsets below are character offsets in decoded source. The inspection does not establish an exhaustive feature list.

| Area | Implemented | Remaining work | Reference evidence |
| --- | --- | --- | --- |
| Artwork | Structured shapes/groups/text, gradients, masks, clipping, embedded raster data, atomic editing and duplication; normalized static path inspection, point edits, segment splitting and removal, symmetric and aligned handle mirroring | Mirroring across a closed contour's start node, alignment/snapping helpers, asset library equivalents, imported SVG normalization | Constructors near 197909 |
| Boolean geometry | Four operations on static sibling shapes; transform conversion; first ID and paint retained | Animated geometry/property preservation; complex paint equivalence; references to removed IDs | 925666 to 930133 |
| Text | Supplied-font shaping and one horizontal run converted to outlines | Paragraph layout, bidirectional run segmentation, text-to-path replacement preserving artwork attributes and keyframes | Text converter near 171159 |
| Transforms | Translate, scale, rotate, skew, additive composition, eased motion paths; Lottie rotation pivots | Explicit SVGator position/origin naming and pivot equivalence against reference exports | Animator registry before 230443 |
| Paint | Fill/stroke/opacity, widths/dashes, gradient stop and coordinate animation in SVG; static linear and radial gradients in Lottie | Gradient transition equivalence; animated gradient stops and gradientTransform in Lottie | Animator registry before 230443 |
| Filters | Eleven ordered effects, stable primitive IDs for animation | Differential rendered comparison; CSS and vector filter export | 1089033 to 1089824 |
| Timeline | Portable editable tracks, keyframe set/remove, per-interval splines, copy/update/remove, snapshots, duration/FPS/playback settings | Structural edits of eased tracks, export-level fill equivalence, selection/editor workflows | 19590 to 21600 |
| Easing | SVG splines; numeric sampled cubic/overshoot/bounce/elastic; discrete step/jump modes | SVGator preset matching and error bounds; color/path easing; exact continuous easing in generated player | 48638 to 50093 |
| Interactions | Five triggers in JavaScript, hover exit and second-click modes, scroll threshold, player controls | All trigger/endpoint comparisons, SVGator API compatibility, event/callback contract | 410900 to 412200 |
| SVG export | SMIL, JavaScript, CSS; static base artwork or a sampled frame at any time, with responsive/fixed sizing and short-ID rewriting | Animated export sizing/ID modes, external/embedded asset controls, optimization | 409900 to 414500 |
| Lottie | Vector shape/group/paint/transform/opacity/compatible path export; static and animated rotation pivots; linear/radial gradient fills and strokes; embedded image layers with aspect fitting and parent transform chains; clip-path alpha mattes and luminance mask mattes | Fonts and filters; images, clips, and masks below the root's direct children; full geometry coverage; optimized JSON equivalence | Export definitions near 412000 |
| Mobile | React Native JavaScript and Flutter Dart components using native Lottie libraries | Native device checks; SVGator runtime and feature equivalence | Export definitions near 412000 |
| Media | Ten raster/video/sequence formats; fit/quality controls; global playback sampling | Format-specific fitting/quality equivalence, transparency checks, all playback/codec comparisons | Export definitions near 412700 to 413000 |

SVGator's source labels `transform.origin` as Position and `transform.translate` as Origin. This server uses SVG transform names. Copying property names between systems would invert those two meanings.

CSS export rejects click, scroll, programmatic, hover reverse, and hover continue. Scroll means playback when a viewport threshold is reached, not progress tied to scroll position. The reference Lottie UI forces forward playback and ignores alternation; those settings should not be assumed portable across formats.

## Verification

Local implementation checks passed on Linux ARM64: 123 unit tests, 100% line and branch coverage, real MCP stdio discovery/calls for 18 tools, Chromium SVG/CSS/player/step/overshoot samples, and ten Chromium/FFmpeg media formats. Sampled static frames matched Chromium's paused SMIL rendering at four times, covering spline easing, color keyframes, delayed and removed channels, pivot rotation with an additive translate, and a curved motion path with automatic rotation. The upstream Lottie SVG player rendered geometry, transform, color, and static/animated pivot samples. Its rasters of gradient, clip, mask, image, and moving-clip fixtures matched the source SVG with no differing pixels away from antialiased edges. Flutter analysis and one widget test passed in an earlier run; the mobile exporter did not change since then. React Native output compiled with its native packages external.

Native iOS/Android execution, complete cross-browser checks, Glaxnimate import, and differential SVGator export fixtures remain unverified. SVGator's Free plan blocks the animated SVG and Lottie exports that a differential comparison needs. Running MCP clients must restart the server to see the new `glaxnimate_export_static` and `glaxnimate_edit_path` options.
