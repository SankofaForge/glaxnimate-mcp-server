# Project journal

## 2026-10-11: SVGator agent-tool parity

The requested target is this MCP server, not the native Glaxnimate desktop application. The user reports explicit permission from SVGator for the investigation. Cloud collaboration and hosted project management are outside the requested scope.

Keep the two existing tool contracts compatible. Add capability discovery so callers can distinguish implemented features from the remaining work. Use SVGator's public schema and REA evidence to define parity. Do not claim that generating valid SVG establishes equivalent rendered behavior.

The initial change extends SMIL properties and timing without new dependencies. Cubic splines use the SVG coordinate range of 0 through 1. Overshoot easing needs a different representation and remains incomplete. Transform composition is explicit to preserve existing replace behavior.

Validation now includes Python 3.12 with warnings treated as errors: 89 tests passed with 100% line and branch coverage. Real MCP stdio discovery and artwork/project/export calls passed for 16 tools. Chromium verified SMIL, CSS, steps, overshoot, motion paths, player timing, reverse, and live reduced motion. Ten media formats passed real Chromium/FFmpeg checks. Lottie geometry/transform/color samples passed in the upstream SVG player. Flutter analysis and one widget test passed; React Native source compiled with native dependencies external. These checks do not establish differential SVGator parity or native device behavior.

REA 6.4.0 connected to the authorized browser session. Its first bundle analysis parsed zero scripts because the application loads scripts from a separate CDN. That capture is not implementation evidence. The subsequent capture includes the application and SVGator CDN origins only. Raw captures stay outside this repository because they can contain account data and application source.

The server remains stateless. Editable project data uses a versioned JSON schema; clients retain save/load and undo/redo snapshots. Atomic edits validate artwork references and timelines before returning a new snapshot. FontTools handles vector parsing and outlines. Optional HarfBuzz handles text shaping, Skia PathOps handles Boolean geometry, and Chromium/FFmpeg handle media rendering. Supplied SVG is not an embedding sanitizer; rendering disables scripts and network access.

Continuous overshoot/bounce/elastic easing is sampled to portable numeric keyframes, with a 512-keyframe limit. Discrete jump modes use explicit keyframe boundaries. The approximation is reported as such. Boolean operations currently require static sibling shapes; animated geometry preservation remains incomplete.

The reference inspection found a naming mismatch: SVGator transform.origin means Position and transform.translate means Origin. The public tool contract keeps SVG transform names and does not claim direct property compatibility. Mobile exports use maintained platform Lottie libraries instead of reproducing SVGator's generated runtime. Vector export rejects unsupported content rather than dropping it.

Lottie keeps one shape layer unless the root has an image, clip-path, or mask child. Those children each get their own layer, because Lottie expresses images as image layers and clipping as track mattes; runs of ordinary siblings stay grouped in shape layers to preserve stacking order. Restricting them to direct root children avoids reconstructing group transforms through layer parenting. Image transforms use parent null layers, and image placement uses intrinsic size read from the embedded file header, so lottie-web's own aspect handling never applies. Masks must use userSpaceOnUse units and a region that covers the viewport, because Lottie has no mask region. Raster comparisons ignore pixels on antialiased edges in the reference, since lottie-web draws circles as Bezier approximations.

Sampled static frames are computed in Python rather than read back from a browser, so the export needs no rendering dependency. Priority follows SMIL: later begin times win, then array order. Motion paths are flattened at 256 steps per curve; Chromium comparisons stay within 0.02 on rotation terms and 0.6 px on position.

The current feature inventory and gaps are in PARITY.md. Remaining work includes snapping and closed-contour handle mirroring, Lottie fonts/filters and nested mattes, exact easing and player API comparisons, export controls/optimization, native device behavior, and differential fixtures. Raw authorized research captures stay outside the repository.

## 2026-10-23: Reject Any annotations and deprecated APIs #decision

Ruff ANN401 now checks `src` and `tests`, and pytest treats Python DeprecationWarning as an error. The pinned Ruff command runs in CI without changing project dependencies.
