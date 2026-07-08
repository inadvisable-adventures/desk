# Workspace SPA shell (COMPLETED, SUPERSEDED)

## Superseded

Per updated requirements (see `CLAUDE.md` and the revised
`design-docs/architecture.md`), the Vite-based Workspace SPA this plan
describes has been removed and replaced by a native Python/Qt Workspace
Canvas plus per-widget `ChromiumWidget` hosting. See
`plans/python-native-workspace-canvas.md` and TODO item 5. This file is kept
for historical record only; the `frontend/` directory it describes no
longer exists in the codebase.

## Summary

Build the pannable/zoomable canvas viewport described in
`design-docs/architecture.md`'s Workspace SPA component — with no widgets on
it yet (that's TODO 5+). This replaces the placeholder static `index.html`
from TODO 2 with a real (if currently empty) canvas: a full-viewport surface
that can be panned by drag and zoomed by scroll/pinch, implemented with CSS
transforms, and built/served as static assets by the Local Web Server. This
item also establishes the frontend build tooling the rest of the widget work
(TODO 5+) will reuse.

## Affected files

- `frontend/` (new directory, outside `src/`) — the Workspace SPA source,
  built independently of the Python package:
  - `frontend/package.json`, `frontend/vite.config.js` — plain JS + Vite,
    no framework (matches widgets themselves being plain HTML/JS/CSS, per
    the design doc's widget model).
  - `frontend/index.html` — entry page with a `#canvas` container.
  - `frontend/src/canvas.js` — pan/zoom canvas implementation: tracks an
    `{x, y, scale}` transform, applies it via CSS `transform` on an inner
    `#canvas-content` element, wires `wheel` (zoom, centered on cursor) and
    `pointerdown`/`pointermove`/`pointerup` (pan) handlers on the outer
    viewport element.
  - `frontend/src/main.js` — bootstraps the canvas on `DOMContentLoaded`.
  - `frontend/src/style.css` — full-viewport layout, hides overflow on the
    outer viewport.
- `src/desk/server/app.py` (edit) — point the `StaticFiles` mount at the
  Vite build output directory instead of the old `server/static/`
  placeholder.
- `src/desk/server/static/` (removed) — superseded by the Vite build output;
  the placeholder page's job (proving the server serves *something*) is now
  done by the real Workspace SPA.
- `.gitignore` (edit) — add `frontend/node_modules/` and the build output
  directory.
- `README.md` (edit) — note the frontend build step in Development setup.

## Implementation approach

1. Scaffold `frontend/` as a minimal Vite project (`vite` as the only
   dependency; no framework) with `frontend/src/canvas.js` implementing:
   - State: `{ panX: 0, panY: 0, scale: 1 }`, clamped to a reasonable zoom
     range (e.g. 0.1x–4x).
   - Zoom: `wheel` listener, adjusts `scale` multiplicatively based on
     `event.deltaY`, adjusts `panX/panY` so the point under the cursor stays
     fixed (standard "zoom to cursor" math).
   - Pan: `pointerdown` on the viewport starts a drag (only when not
     starting on a widget element — moot for now since there are no widgets
     yet, but the check is added so TODO 5 doesn't have to revisit this),
     `pointermove` while dragging updates `panX/panY`, `pointerup` ends it.
   - Applies `transform: translate(panX, panY) scale(scale)` to
     `#canvas-content` on every update (via `requestAnimationFrame` to
     coalesce rapid events).
2. Decide the build-output wiring: Vite builds `frontend/dist/`; configure
   `src/desk/server/app.py`'s `create_app()` to accept a `static_dir`
   parameter (defaulting to `frontend/dist` resolved relative to the repo
   root during development) instead of hardcoding the old
   `server/static/`.
3. Remove `src/desk/server/static/index.html` (and the directory, if
   empty) now that it's superseded.
4. Update `.gitignore` for `frontend/node_modules/` and `frontend/dist/`
   (build output is generated, not committed — consistent with not
   committing Python's own build artifacts).
5. Update `README.md`'s Development setup section: `cd frontend && npm
   install && npm run build` (or `npm run dev` for iterative frontend work
   against Vite's own dev server) before/alongside `python -m desk`.

## Verification

1. `npm install && npm run build` in `frontend/` succeeds and produces
   `frontend/dist/index.html` + assets.
2. `python -m desk` starts, and `curl`ing `/` (with token) returns the built
   Workspace SPA's `index.html` rather than the old placeholder.
3. Visual/interactive check (pan by dragging, zoom by scrolling) requires
   actually seeing the rendered page. As noted in `plans/desk-shell.md`,
   this environment's screenshot path hasn't reliably shown this app's
   window contents, so per `development-process.md` step 5 that specific
   check is expected to be skipped here and is worth confirming manually
   outside this environment. Where possible, canvas transform math will
   instead be sanity-checked directly (e.g. a short headless script driving
   `canvas.js`'s exported functions, if structured to allow that) rather
   than relying solely on the visual check.

### Status (verification notes)

- `npm install` (10 packages) and `npm run build` both succeeded, producing
  `frontend/dist/index.html` + hashed JS/CSS assets. `npm audit` flags a
  moderate/high advisory in `esbuild`/`vite@5.4.x`'s *dev server* (a
  same-origin-policy gap in `vite dev`, not in the built output); the fix
  requires a `vite@8` major bump. Left at `vite@5.4.21` (latest 5.x) for
  now since the advisory only affects `npm run dev` (not used by the
  shipped app, which only serves `vite build` output through Desk's own
  token-authed server) — worth revisiting when other TODO items give a
  natural reason to touch build tooling again.
- Ran `python -m desk` (headless, not the actual GUI window) and confirmed
  via `curl`/`urllib` with the per-launch token that `GET /` now returns
  the built Workspace SPA (contains `canvas-content` and the built JS
  bundle reference) and that a built asset (`GET
  /assets/index-*.css`) is served with status 200 — i.e. the server is
  correctly serving `frontend/dist/` instead of the old placeholder.
- Did not re-verify the visual pan/zoom interaction or the app's
  quit/shutdown behavior in this item — the latter was already verified in
  `plans/desk-shell.md` and nothing here changes that lifecycle; the
  former is the browser-visual check already noted as skipped in this
  environment.

## Key design decisions / tradeoffs

- **Plain JS + Vite, no framework.** Keeps the Workspace SPA's own stack as
  simple as the HTML/JS widgets it will host — there's no interaction
  complexity yet (state management, componentized views) that would justify
  a framework's overhead. If the canvas's widget-management logic grows
  complex enough to want one (see TODO 5+), that's a decision to revisit
  then, not preemptively now.
- **CSS-transform-based canvas, not `<canvas>`/WebGL.** Widgets need to be
  real DOM elements (they're HTML documents in iframes, per the widget
  model), so the pannable/zoomable surface has to be a DOM container with
  CSS transforms, not a `<canvas>` bitmap — a `<canvas>`/WebGL canvas
  couldn't host live iframes on it.
- **Vite as a separate `frontend/` project rather than folded into the
  Python packaging.** The frontend has its own dependency graph (npm) and
  build step (bundling/minifying JS) that doesn't belong in `pyproject
  .toml`; keeping it a sibling directory with its own `package.json` is the
  standard shape for a Python-backend + JS-frontend project, and matches
  widgets (also separately-authored HTML/JS/CSS bundles) rather than
  something Python needs to understand the internals of.
