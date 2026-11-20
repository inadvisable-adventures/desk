# TempUI DSL: DefineWidget

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
covers the `DefineWidget` keyword, invoking a widget it defines,
promoting one to the Desk, and the Bridge API your widget's own JS can
call.

For introducing a brand-new *kind* of widget to the current Desk —
entirely in-browser (HTML/CSS/JS, rendered in an embedded browser
view), **never Python** — without touching the project's own
`widgets/` directory. Once defined, the new kind gets its own new
tempui DSL keyword that a *separate*, later tempui file can use to
place an instance of it (see "Invoking a defined widget" below) — this
is how the tempui DSL itself gets extended at runtime.

**A `DefineWidget` file only registers the new widget *kind* — it does
not, by itself, place an instance of it on the canvas, whether the
keyword is brand-new or you're only redefining an already-registered
one (e.g. re-saving one to fix a mistake).** Always use a separate,
keyword-only tempui file afterward to actually see it (see "Invoking a
defined widget" below) — the same two-step dance every use of a
`DefineWidget` keyword requires, with no auto-placed exception.

**When to propose a widget yourself.** If a task's correct answer
depends on a human's subjective visual judgment -- cropping or selecting
a region in an image, confirming that a placement/composite/layout looks
right, disambiguating something a fixed heuristic cannot reliably
isolate -- that is a signal to propose a small, disposable `DefineWidget`
for the user to *show* you the answer (drag a box, click a point, toggle
an option, watch a live preview), even when their request did not ask for
one. Looking at something once and dragging a box beats a chat
back-and-forth of describing pixel coordinates in words, and beats
grinding on a fully automated heuristic for an inherently fuzzy target.
This composes with automation rather than replacing it: a cheap heuristic
can seed a sensible default inside the widget (so it does not open to an
empty or arbitrary selection), and the widget's own job stays narrowed to
*selecting* -- e.g. writing the confirmed rectangles to a small JSON file
-- while an ordinary script reads that file and does the actual work
(cropping, resizing, pasting, re-encoding at full resolution). The widget
only needs to be a competent picker, not an editor. Propose it first
rather than silently building it, unless the user already asked for one.

Lines are **tab**-separated (like `LightningRound`), since a label may
contain spaces:

- `DefineWidget<TAB>keyword<TAB>label` — **must be the first line**.
  `keyword` becomes both the new DSL keyword used to invoke this widget
  kind (see below) and its internal widget id — pick something
  CamelCase-ish with no spaces, matching the shape of this DSL's own
  built-in keywords (`LightningRound`, `OpenMarkdown`, ...). `label` is
  the human-friendly name shown in the widget's titlebar and anywhere
  else it's listed — never a UUID or the raw `keyword`.
- `Size<TAB>width<TAB>height` — optional. The new widget kind's default
  placement size in pixels.
- `Capability<TAB>name` — optional, repeatable. Grants this widget kind
  a Bridge API capability (`workspace`, `fs`, `widgets`, `events`, ...)
  — same coarse, resource-level strings a real `widgets/<id>/widget.json`
  manifest's own `capabilities` list uses. Without this, your widget's
  JS can only call the always-available `self.*` calls (see "The Desk
  Bridge API" below) — anything else (including `events.*`) fails with
  a 403 unless you declare the matching capability here. One
  capability, `media`, isn't a Bridge API call at all -- it gates
  whether the browser grants this widget's page `getUserMedia()`
  (mic/camera) access; see "Media (mic/camera) access" below.
- `StateSchema<TAB>key<TAB>type_expr` — optional, repeatable (TODO
  af7898b). Declares a validated schema for one `desk.state.*` key --
  `type_expr` is a TypeScript type expression string (see "Shared,
  project-scoped state" below for the supported subset and what
  declaring a schema actually does). Requires the `state` capability
  too, the same as any other `desk.state.*` access.
- `Html<TAB>base64-chunk` — the widget's entire implementation: **one
  self-contained HTML document** (inline `<style>`/`<script>` cover
  CSS/JS — there's no separate CSS/JS file), **base64-encoded**. Split
  across as many `Html` lines as needed (each is just a chunk,
  concatenated in file order before decoding) — a single line doesn't
  have to hold the whole file. At least one `Html` line is required.

Example:

```
DefineWidget	KanbanBoard	Kanban Board
Size	600	400
Capability	workspace
Html	PGh0bWw+PGJvZHk+PGgxPkthbmJhbjwvaDE+PC9ib2R5PjwvaHRtbD4=
```

A `keyword` that collides with one of this DSL's own built-in keywords
(`Question`, `LightningRound`, `DefineWidget`, ...) or an existing
widget id is refused (logged, not an error) — pick something else.

## Authoring from real source (TypeScript + a build script)

Hand-writing a `DefineWidget` file's inline `<script>` as plain JS with
markup assembled via `innerHTML` works, but it's a poor fit for a project
whose own conventions ask for more (e.g. strict-mode TypeScript,
`<template>`/`<slot>` instead of string-built HTML — see this project's
own `CLAUDE.md` if it has such rules). Author once from real source, then
mechanically repackage it into the format above with
`.desk_temp/build_widget.py` (generated here the same way this doc set
itself is, kept fresh automatically rather than seeded once) any time
it changes — never hand-edit the generated `DefineWidget` file itself.

Per widget, a source directory at `.desk_temp/widgets/<name>/` —
deliberately **not** under the project's own top-level `widgets/`, since
*that* directory is scanned by Desk's own widget discovery, which expects
every `widget.json` there to have a `kind` of `"python"` or `"html"`;
this directory's `widget.json` has a different shape and would break
that scan if placed there instead. `.desk_temp` is already
Desk-specific/gitignored support territory (see `TEMP_UI_DIRNAME`
elsewhere in this doc), which is exactly the right home for a
not-yet-promoted widget's source too. Four files:

- `<name>.ts` — the widget's logic as a custom element (`class Foo
  extends HTMLElement`), in normal strict TypeScript. No knowledge of
  base64/tempui/Desk belongs in this file at all — it just clones a
  `<template>`'s `.content` into a shadow root; the only Desk-specific
  surface it touches is the Bridge API below, guarded by `if
  (window.desk)` so the file still works opened as a plain page.
- `widget.html` — the eventual self-contained document, with a
  `<template id="<name>-template">` holding the real markup and a scoped
  `<style>`, a `<script>` whose entire content is the one-line marker
  comment `/* BUILD:COMPILED_JS */`, and the `<name-tag></name-tag>`
  element instantiation.
- `tsconfig.json` — whatever strictness the project wants; must set
  `compilerOptions.outDir`. **Set it to `.build`** — the same directory
  a promoted, source-backed widget is rebuilt into (see "Promoting a
  defined widget to the Desk" below); `tsc`'s own raw compiled `.js`
  output there and the final packaged `index.html` coexist in that one
  directory just fine. Any other value still works while un-promoted
  (`build_widget.py` reads whatever you set), but promotion will offer
  to rewrite it to `.build` for you, and until you accept that (or set
  it yourself), it's a second, gitignore-uncovered build directory
  alongside `.build` — the existing `desk_widgets/**/.build/`
  gitignore-entry prompt only ever covers `.build` itself. For a widget
  split across more than one
  `.ts` file (e.g. a shared base class alongside the widget's own
  subclass), also set a top-level `"files"` array listing them in
  the order they must be concatenated in — base classes before the
  subclasses that `extends` them. These files compile as global
  scripts (no `import`/`export`), so load order matters exactly like
  script tags on a page; `build_widget.py` respects this array when
  present instead of an alphabetical directory sort, which cannot be
  relied on to put a base class first. A `tsconfig.json` with no
  `"files"` key (the common, single-file case) is unaffected.
- `widget.json` — `{"keyword", "label", "width", "height"}`, exactly the
  fields a `DefineWidget`/`Size` line above needs, plus an optional
  `"capabilities": [...]` (a list of the same coarse, resource-level
  strings a real `widgets/<id>/widget.json`'s own `capabilities` list
  already uses -- `workspace`, `fs`, `widgets`, `events`, `media`, ...)
  — the build script emits one `Capability<TAB>name` line per entry, so
  `widget.json` is the one place a defined widget's capabilities need
  to be declared, the same way a real `kind: "python"`/`"html"`
  widget's manifest already works. Omit it entirely for a widget that
  needs none (the default). Also accepts an optional `"state_schema":
  {"<key>": "<type expression>", ...}` (TODO af7898b) declaring which
  `desk.state.*` keys this widget kind's schema covers -- the build
  script emits one `StateSchema<TAB>key<TAB>type_expr` line per entry,
  the same real widget.json field a `kind: "python"`/`"html"` widget
  declares one in. See "Shared, project-scoped state" below.

Then `python3 .desk_temp/build_widget.py .desk_temp/widgets/<name>`
compiles it (`tsc -p <dir>`), concatenates the compiled JS, substitutes
it into `widget.html`'s marker, base64-encodes the result, and writes a
fresh `DefineWidget` tempui file under `.desk_temp/` — printing the
path it wrote. That file also records a `SourcePath` line naming
`<name>`'s directory (TODO 13f4ad5) — Desk uses this durable record to
find the real source directory later, rather than guessing it back
from the `DefineWidget` line's own `keyword`, which is almost never
the same string as this (kebab-case) directory name.

Once promoted (see "Promoting a defined widget to the Desk" below), the
source directory moves to `desk_widgets/<name>/` at the project root —
a permanent, non-gitignored location, matching the promoted
definition's own move into the `.desk` file. **Do not** re-run
`build_widget.py` against it for further edits — that produces a
`DefineWidget` tempui file, and a promoted widget's `.desk` file entry
is no longer sourced from tempui files at all, so nothing would ever
pick it up. Instead, just edit the files under `desk_widgets/<name>/`
directly (`<name>.ts`, `widget.html`, ...) and save — Desk watches
that directory itself and marks every already-placed instance
`[STALE]`, exactly like a still-`.desk_temp`-sourced `DefineWidget`'s
own live edits already do; click it to rebuild (`tsc`, same as before)
and reload. This covers the widget's directory **and** any file its
`tsconfig.json` `"files"` array lists from outside it (e.g. a shared
`../_shared/x.ts`): one edit to a shared file marks *every* promoted
widget that lists it `[STALE]` (a widget whose `tsconfig.json` you edit
to add a shared file starts following it immediately). A *file* outside
the directory is only followed if it's listed in `"files"` -- an
unlisted sibling in the shared directory is ignored. The rebuild also re-reads `widget.json`'s `"capabilities"`
and `"state_schema"` into the widget's stored definition, so changing
them there works the same way (a newly *added* capability asks the user
to confirm; never hand-edit the `.desk` file to change them).

## Debugging a widget's own rendering/geometry visually

When what a user sees and where your code *thinks* something is
disagree (a canvas widget whose hover/click only lands when the pointer
is "down and to the left" of the feature), don't iterate on guesses —
each plausible fix costs a build/`[STALE]`/reload round and can leave the
symptom untouched. Make the internal state visible and compare it in
one screenshot instead. The four pieces below are a reusable pattern:

1. **A build marker in the widget's own UI.** One `const BUILD_MARKER =
   N` bumped on every edit and rendered as plain text. It removes "is
   this actually the new code?" as a variable before anything else is
   debugged — a promoted widget's edit → `[STALE]` click → rebuild cycle
   has enough steps that a stale reload is easy to make and easy to
   mistake for a real symptom.
2. **A toggleable debug layer that records the real outcomes of the
   code path under test**, plotted at the exact values that path used —
   e.g. every actual hit-test call (not a swept grid of synthetic
   probes), green dot for a hit, red for a miss, at the exact coordinates
   handed to `isPointInPath`. Because it sits downstream of the same
   inputs, the visualization cannot introduce a discrepancy of its own.
3. **Ground-truth markers computed by the same function you are
   verifying.** Record *which* feature each hit matched, then draw a
   labeled crosshair at that feature's true center using the very
   projection function (`toScreen()` or equivalent) that renders it. One
   screenshot now shows both answers drawn on top of each other: where
   the feature is (render path) versus where clicking it registers
   (hit-test path). Crosshairs on the polygons but dots displaced from
   them, growing with distance from the origin, means a transform/scale
   mismatch specific to hit-testing, not rendering.
4. **Close the loop yourself with `desk_screenshot_widget` /
   `desk_reveal_widget`** rather than asking the user to describe what
   they see in words ("it's offset down and to the left"): take the
   screenshot, read pixel positions off it, and compare. Pass
   `max_width` to keep the image small. Still ask the user for the one
   thing you cannot do — there is currently no way for an agent to
   synthesize a pointer/keyboard event against a placed widget, so a
   human has to move the mouse before each screenshot is informative.

Worked example of what this found: a canvas map whose hit-testing was
offset by an amount that varied non-proportionally with both the
widget's internal zoom and Desk's own canvas zoom. Two hypothesis-driven
fixes (measuring the wrong element's bounding box; a stale
`devicePixelRatio`) were real improvements but missed. The trace layer
with ground-truth crosshairs found the cause in one round:
`CanvasRenderingContext2D.isPointInPath()`'s query point is not reliably
subject to the current transformation matrix the way `fill()`/`stroke()`
are, so testing under the `devicePixelRatio`-scaled drawing transform
compared mismatched coordinate spaces. Running the hit-test under an
identity transform (matching the raw CSS-pixel numbers the `Path2D`s are
built from) fixed it. Remove the marker/overlay (or leave them behind a
toggle) once the bug is closed.

## Reusable UI components

`.desk_temp/shared-components/` holds a small library of ready-made,
dependency-free UI components for exactly this kind of real-source
authoring — check here before building something non-trivial from
scratch, whether that's a UI control (a color picker) or a whole
widget's file lifecycle (a title-to-path, auto-load/auto-save document
editor). Refreshed automatically alongside the rest of `.desk_temp`,
same as `build_widget.py` above — never a stale one-time copy. Each
component lives in its own subdirectory with its own `README.md`
explaining what it does and how to use it — either import its file
directly, or copy+paste+modify it into your own widget file, whichever
suits the component. Importing a base class a widget's own file
`extends` needs its own `tsconfig.json` `"files"` entry ahead of the
widget's own file (see "Authoring from real source" above) so
`build_widget.py` concatenates it first.

### Using a component: `"components"` in `widget.json`

For a real-source widget (`.desk_temp/widgets/<name>/` or promoted
`desk_widgets/<name>/`), the easy way is one line in its `widget.json`:

```json
{ "keyword": "...", "label": "...", "width": 400, "height": 300,
  "components": ["desk-select", "drop-cap-text"] }
```

The build (Desk's own, and `build_widget.py`) then compiles each
component's `<name>.ts` **ahead of** your own files (so your classes may
extend a component's, and `tsconfig.json` `"files"` need not list it) and
injects the component's `template.html` as a top-level sibling right after
`<body>` -- exactly where the element's `document.getElementById(...)`
lookup needs it. No copying a `<template>` out of another widget. To put
the templates somewhere else, add a `<!-- BUILD:COMPONENT_TEMPLATES -->`
line to `widget.html`. A template your `widget.html` already contains
(the old hand-pasted way) is left alone, not duplicated, so existing
widgets keep working; delete your copy and your `"files"` entry when you
migrate.

**Two libraries.** A component is a directory `<name>/` holding
`<name>.ts` and, optionally, `template.html` (plus a `README.md`):

- **Desk-wide** (static): Desk's own `shared-components/`, mirrored at
  `.desk_temp/shared-components/`. Immutable from a project -- it changes
  only when Desk's source does.
- **Per-project** (mutable): `desk_widgets/_shared/components/<name>/` in
  *your* project. Author components here for reuse across this project's
  widgets; edit freely. Saving a file of a component a promoted widget
  lists marks that widget `[STALE]`, like any shared source (a
  `widget.json` edit re-arms the watch).

A bare name resolves to the **project** library's copy if it has one,
else the desk-wide one -- so a copy you keep in the project (e.g. one
vendored from Desk's library, below) wins, and a component a later Desk
adds can never change what an existing project builds. Write `desk:<name>`
or `project:<name>` to pin a side (`project:` fails the build, rather than
falling back, if the copy is missing). An unknown name fails the build
with the places it looked. The build writes `.build/tsconfig.components.json` (an
`extends` of your `tsconfig.json`) and compiles into `.build/js/`; the
`outDir` in your own tsconfig is not used for such a widget.

**Seeing what's available.** The **Components** widget (a built-in; place
it from the widget menu) lists both libraries -- each component's README
summary, files, whether it ships a template, and which of this project's
widgets use it -- and can open its README/source or copy its `"components"`
entry. Agents get the same catalog from the `desk_list_shared_components`
MCP tool.

**Deploying a project: vendor the components.** A real-source widget is
rebuilt from source whenever Desk opens the project, so the *opening Desk's*
`shared-components/` is part of its build input -- fine on your machine, but
a project opened under a different Desk (or one whose library later changes)
no longer builds from what is in the repository alone. To make a widget
self-contained, copy the desk-wide components it uses into the project:
call the `desk_vendor_widget_components(source_path)` MCP tool (e.g.
`desk_widgets/my-widget`), or use the Components widget's **Copy to project
library** button on a component. The tool copies each desk-wide component
into `desk_widgets/_shared/components/<name>/` and rewrites the widget's
`"components"` entries to `project:<name>`, so the build reads only project
files -- and fails loudly, instead of silently falling back to Desk's copy,
if one goes missing. Idempotent; a project copy that differs from Desk's is
never overwritten unless you pass `overwrite`. Commit
`desk_widgets/_shared/components/` with the widget. What still must exist
wherever the project is opened: Desk itself and `tsc` on `PATH`.

**Authoring a component** (the contract the build relies on): the
template is a top-level `<template id="<name>-template">` that the
element looks up with `document.getElementById` in its constructor;
write the class in global mode (no import/export); and make attributes,
not just properties, the way to configure it, so it works when a widget
builds markup as an HTML *string* (`innerHTML`) -- a property can only
be set on a live element afterwards. Put a `README.md` next to it saying
what it is for.

**Don't use a native `<select>` (or any other control that opens an
OS-level popup) in a `kind: "html"`/`DefineWidget` widget.** Your page
is embedded in the zoomable, pannable canvas, and a native `<select>`
opens its list as a separate popup positioned from untransformed screen
coordinates -- with the canvas away from identity zoom/pan the list
renders detached from the control (the HTML twin of the Qt `QComboBox`
problem). Use `shared-components/desk-select` (`<desk-select>`) instead:
a drop-in replacement whose dropdown is ordinary page content, so it
rides along with the canvas transform. Same exposure, same advice: avoid
`<input type="date"|"time"|"month"|"week"|"datetime-local"|"color">`,
`<input list=...>`, and the browser context menu under the canvas. See
`shared-components/desk-select/README.md`.

**Custom elements and `<template>` cloning.** A `<template>`'s content
is inert: an element cloned out of it (`template.content.firstElementChild
.cloneNode(true)`) is *not* upgraded to its custom-element class until it
is connected to the live document -- and `customElements.upgrade(clone)`
does **not** change that (the clone still belongs to the template's inert
document, which has no custom-element registry). So `clone.value = x` on
an un-upgraded custom element silently creates a plain own property that
can shadow the class's real accessor once it upgrades, with no error.
`<desk-select>` guards against this itself, but a custom element you write
will not unless it re-applies such properties on connect. To get an
already-upgraded element, build it with `document.createElement("tag-name")`
or clone with `document.importNode(template.content.firstElementChild,
true)` (which adopts it into the live document, upgrading it); or set
properties only after inserting the clone.

If your widget is actually several wired-together components (a
multi-pane layout, an event-wiring table between them, shared
app-level state) rather than one self-contained custom element,
`.desk_temp/app_dsl/` is a separate, real (if smaller-scoped so far)
tool for exactly that -- see `app_dsl/README.md` (same directory) for
the DSL format. It supports two output modes: `--mode=module` (real ES
modules, for a standalone build outside Desk) and `--mode=global`
(plain global scripts, no `import`/`export` at all -- for feeding into
this `build_widget.py` pipeline above, the same concatenation
convention "Authoring from real source" already uses for a multi-file
`DefineWidget` source). `--mode=global` requires your component/
handler source to also avoid module syntax -- see `app_dsl/README.md`
for the full constraint.

## Invoking a defined widget

A separate tempui file whose **entire first line is just the
keyword**, nothing else, places one instance of that widget kind —
centered in the current view, same as every other tempui-placed
widget:

```
KanbanBoard
```

There's no per-instance content or label here — a defined widget's
titlebar always shows its *type's* own `label` from the `DefineWidget`
line above. If you need different-looking instances, define separate
widget kinds with separate keywords.

A widget placed this way **can only ever be placed via tempui** — it
never appears in the canvas's right-click "Add widget" menu, unlike
every ordinary widget in `widgets/`. (An agent can also place an instance
directly with the `desk_place_widget` MCP tool, which takes the keyword as
`widget_id` and returns the new `instance_id` to chain into
`desk_screenshot_widget` — no notification click needed.)

## Promoting a defined widget to the Desk

Every placed instance of a `DefineWidget`-defined widget shows a
`[TEMPUI]` button in its titlebar. Clicking it offers to **promote**
the widget: on confirm, its definition is saved permanently into the
current `.desk` file (surviving even if this `DefineWidget` file is
later deleted) and the original `DefineWidget` file here is removed —
the `.desk` file becomes the sole remaining source of truth. If the
widget was authored from real source (see "Authoring from real source"
above), its `.desk_temp/widgets/<name>/` source directory moves to
`desk_widgets/<name>/` at the project root at the same time, for the
same reason — a promoted widget is now a permanent part of the
project, so its source shouldn't keep living in `.desk_temp` either.
Invocation (see above) keeps working exactly the same afterward,
promoted or not.

A source-backed promoted widget (TODO 13f4ad5) does **not** keep a
baked copy of its compiled HTML in the `.desk` file — instead Desk
rebuilds it fresh from `desk_widgets/<name>/` into a gitignored
`desk_widgets/<name>/.build/` cache every time it registers this
widget (startup, Desk switch, or right after promotion itself), the
same compile-and-package step `build_widget.py` runs by hand. This
means `tsc` (and anything else that widget's own build needs) must be
available wherever a Desk containing it is subsequently opened, not
just on the machine it was authored/promoted on — see
`tempui-breaking-changes.md`. A hand-authored, inline-only
`DefineWidget` (no source directory) is unaffected: there's nothing to
rebuild from, so it keeps today's baked-`html_b64` behavior.

**Shared files a widget's `tsconfig.json` lists from outside its own
directory** (a shared base class or DSL module in a sibling directory,
`shared-components/...`) are handled at promotion too, since their
relative paths would otherwise break the moment the widget's directory
moves. Promotion reads `"files"`; a file under `.desk_temp/widgets/`
(and not inside another widget's own directory) is moved once to the
same relative place under `desk_widgets/` (so a shared
`.desk_temp/widgets/_shared/x.ts` becomes `desk_widgets/_shared/x.ts`,
and a second widget promoted later just finds it already there); a file
already at its final location, or the regenerated
`.desk_temp/shared-components/` mirror, stays put. The widget's own
`tsconfig.json` `"files"` entries are then rewritten to resolve from its
new directory, and Desk shows what it moved and rewrote. Any other
not-yet-promoted widget whose `tsconfig.json` listed a moved file is
offered the choice to be promoted too, have its `tsconfig.json` fixed,
or be left alone (a left-alone widget's next rebuild will fail until its
path is fixed). A different file with the same name already at the
destination is never overwritten -- Desk reports it and leaves the
widget pointing at the original. Only `"files"` is read, not `include`.

**The widget's own build output is normalized too.** If its
`tsconfig.json` `compilerOptions.outDir` doesn't already say `.build`,
promotion offers to rewrite it to match (the same directory Desk
itself rebuilds the widget into, above) -- accept it, or set `.build`
yourself from the start (see "Authoring from real source"), and there's
only ever one build directory to gitignore, already covered by the
`desk_widgets/**/.build/` entry. Either way, promotion also clears out
whatever that directory currently holds, without asking -- it moved
along with the rest of the widget's source and can only be a stale
compile from before the move, which the very next rebuild regenerates
from scratch.

## The Desk Bridge API — what your widget's own JS can call

A `DefineWidget` widget's HTML document runs inside a real embedded
browser page with one extra thing every other web page doesn't have:
`window.desk`, a small JS client automatically injected before your
own code runs. It's how your widget talks back to Desk itself —
notably, **it's the recommended way to persist your widget's own
state across a Desk reload**: `window.desk.self.getLocalStorage()`
/`.setLocalStorage()`'s data lives inside the project's own `.desk`
file, so it travels with the project (copy/share the `.desk` file and
your widget's saved state comes with it). Each instance's page *does*
also get its own real, persistent browser storage now (cookies,
`localStorage`, `IndexedDB` — a separate profile per widget instance,
under `.desk_temp/`), so it's no longer true that nothing else
persists — but that storage is tied to this specific project checkout
(not portable the way the `.desk` file is) and is deleted outright the
moment the widget instance is permanently removed from the canvas.
Prefer `getLocalStorage`/`setLocalStorage` for anything you actually
want to keep.

All calls are `async` (they return a `Promise`):

- `desk.self.getLocalStorage()` → `{ data }` — call this once, early,
  when your widget's page loads, to restore whatever you last saved.
  `data` is `{}` for a brand-new instance with nothing saved yet.
- `desk.self.setLocalStorage(data)` → `{ ok: true }` — call this
  whenever your widget's own state changes (on every meaningful
  interaction, or debounced if that's too chatty for your case) —
  `data` must be JSON-serializable. This is **pull-based on Desk's
  side**: whatever you last pushed here is what actually gets written
  to the `.desk` file, at the *next* time the Desk itself is saved
  (not immediately on every call) — call it eagerly and often, don't
  wait for some separate "save" signal that doesn't exist.
- `desk.self.getManifest()` → your own widget's manifest (id, name,
  capabilities, default size, content hash, and the current Desk's own
  `directory` — the last two exist specifically so you can tell which
  version of your widget's code is currently registered, and construct
  a correct project-relative path yourself if you ever need to, without
  declaring the `fs` capability just to find out where you are).
- `desk.self.setSubtitle(text)` → `{ ok: true }` — puts your own
  instance's state into its own titlebar, next to its kind's static
  label (e.g. `"My Widget — some-document.md"`). Every instance of
  your widget's kind otherwise shows the identical label, so this is
  how one particular instance shows *which* thing it's currently
  pointed at. Call it again whenever that changes; pass `null` (or an
  empty string) to clear it back to the bare label. Not persisted —
  call it again after restoring your own state (e.g. right after
  `getLocalStorage`) on every fresh page load, the same way you'd
  re-render your own content.
- `desk.self.getOpenedFile()` → `{ path }` (TODO 83427f4) — the file
  path your instance was opened for, if any — e.g. it's the registered
  `view`/`edit` handler for a file type in the File Type Registry
  (`desk.filetypes.set`), and the user double-clicked a matching file
  in Project Files, or a viewer widget's own Edit button opened you
  against a specific file. `path` is `null` for an instance placed any
  other way (a blank canvas placement, a tempui file with no target
  path, ...) — check for `null` rather than assuming a path is always
  present. Call it once, early, on page load (the same "call this once
  early" shape as `getLocalStorage`) — this is a one-shot fact about
  how *this* instance was created, not something that changes later
  the way `setSubtitle`'s own text can.

If you're porting an existing web app/component into a `DefineWidget`
widget, it likely already has its own persistence mechanism (custom
events, a global variable, `localStorage`, whatever the original
project used) — that mechanism does **not** work here (see above: it
won't survive a reload) and porting the widget does not rewire it for
you. You need to explicitly replace it with calls to
`desk.self.getLocalStorage`/`setLocalStorage` above; don't assume the
old approach just keeps working because the rest of the port succeeded.

A few more calls exist for widgets that need them (all require
declaring the matching capability in your own manifest, unlike the
`self.*` calls above, which need none). **If what you actually want is
"tell other widgets something happened," reach for `desk.events.*`
first** — every other call in this list is scoped to your own widget or
to one other widget you already know the id of, but `events` is the one
built for genuine cross-widget signaling:

- `desk.events.subscribe(names)` / `.unsubscribe(names)` /
  `.publish(name, payload)` / `.onMessage(callback)` (capability
  `events`) — send and receive named messages to/from other widgets.
  See "Sending and receiving named messages" below. An agent can also
  raise one of these events itself with the `desk_raise_event` MCP tool,
  and wait for one with `desk_wait_for_event` from a background sub-agent
  (`tempui-agent-events.md`).
- `desk.log.append(name, entries)` / `.line(name, s)` (capability `log`)
  -- fire-and-forget, time-stamped strings into a named log that an
  agent reads back by time range with the `desk_query_widget_log` MCP
  tool. Not a message channel to other widgets (that is `events`); a
  record for an agent. See `tempui-widget-logs.md`.
- `desk.workspace.getState()` (capability `workspace`) — the current
  Desk's live widget layout: one entry per placed instance (widget id,
  instance id, position/size, `state`, `locked`, `placed_content_hash`)
  plus `stale` (TODO f0da2e9) — `true` when that instance is showing
  the titlebar `[STALE]` badge (its placed content no longer matches
  what's currently registered/on disk, so it's still running its own
  pre-edit code) — check it before trusting a just-edited widget's
  behavior, the same signal a human would otherwise have to notice on
  the canvas themselves.
- `desk.state.get(key)` / `.set(key, value, edit)` / `.getHistory(key,
  limit)` (capability `state`) — a shared, project-scoped key/value
  store any widget can read or write. See "Shared, project-scoped
  state" below.
- `desk.fs.readFile(path)` / `desk.fs.writeFile(path, contents)`
  (capability `fs`) — read/write an arbitrary file on disk. A relative
  `path` resolves against the current Desk's own directory (not any
  particular process's working directory); an absolute path is used as
  -is. `writeFile` creates any missing parent directories first (like
  `mkdir -p`) — a widget author never needs to separately ensure a
  target directory exists before writing into it. This is
  same-directory file I/O, not a way to signal another widget — see the
  `events` callout above if that's what you're after.
- `desk.documents.open(path)` / `.read(handle, {offset, length})` /
  `.close(handle)` (capability `documents`) — virtualized raw byte-range
  reads of large or binary files, cached Desk-side (`.desk_temp/
  documents_cache/`, invalidated when the file changes). `open` returns a
  handle without reading the file; `read` returns `{data: base64, eof}`
  (binary-safe; `length` is clamped to 8 MiB per call); relative paths
  resolve against the current Desk's directory like `desk.fs.*`. Use this
  instead of base64-ing a whole file through a transform just to show part
  of it (e.g. page one of a large PDF).
- `desk.widgets.list()` / `.open(widgetId, opts)` / `.close(instanceId)`
  (capability `widgets`) — inspect/manage placed widget instances.
- `desk.introspect.snapshot(targetInstanceId)` (capability
  `introspect`) — get a DOM tree snapshot and console log of *another*
  widget instance. See "Inspecting another widget" below.
- `desk.filetypes.get()` / `.set(entries)` (capability `filetypes`) —
  read/edit the file type registry (which widget(s) can view, edit,
  git-diff, consume, or produce which file type, by extension and/or
  MIME type).
  `get()` also subscribes you to future edits, delivered as a
  `"desk.file_type_registry.updated"` message via `desk.events
  .onMessage` (declare the `events` capability too if you want to
  receive it) — one call does both "read" and "start watching," not
  two separate ones.
- `desk.editor.openOrScrap(path)` (capability `editor`) — open an
  appropriate editor for `path` (falling back to the built-in text
  Editor for a genuinely text file with no registered editor), or
  place an explanatory Scratch note if nothing can open it — the same
  service a `kind: "python"` widget reaches via `current_context
  .get_editor_or_scrap_opener()`. A relative `path` resolves against
  the current Desk's own directory, same as `desk.fs.*`.
- `desk.popups.show(title, message, buttons, default)` (capability
  `popups`) — shows a desk-internal popup (a small `WidgetFrame` placed
  on the canvas, not a real OS window) with `message` and one button
  per label in `buttons`; blocks until the Desk user clicks one (or
  returns `null` if dismissed via its close button/Escape). `default`
  (optional) names which button is the pre-selected/Enter-triggered
  one. The same service a `kind: "python"` widget reaches via
  `current_context.get_popup_opener()`. **Use this, not the browser's
  own `alert()`/`confirm()`/`prompt()`**, for any alert or confirmation
  your widget shows — those are real, separate OS-level dialogs with no
  connection to Desk's own canvas chrome (wrong styling, no
  zoom/pan-aware positioning, and blocking in a way that can behave
  surprisingly inside an embedded `ChromiumWidget`).
- `desk.hmsvc.list()` / `.logs(name, limit)` / `.start(name)` /
  `.stop(name)` / `.restart(name)` (capability `hmsvc`) — manage the
  project's Desk-hosted microservices (`desk_hmsvc/<name>/`). They
  resolve to objects, never bare arrays: `list()` → `{ services: [...] }`,
  `logs()` → `{ lines: [...] }`, `start/stop/restart()` → `{ ok, message }`.
  If you only need a service's URL, read `desk.state` instead (no `hmsvc`
  capability needed; see `tempui-hmsvc.md`). This is
  *management only*: `list()` gives each running service's current
  `url` (a new port every launch) and your widget then calls `fetch()`
  against it itself, so the service must send its own CORS headers. See
  `tempui-hmsvc.md` for the whole story.
- `desk.transforms.run(transformId, input, config)` (capability
  `transforms`) — runs a transform (a separate entity from a widget:
  converts data of one named type into another, e.g. a Mermaid
  diagram's source into SVG) and returns `{ output, error }` (exactly
  one is non-`null`). `config` is optional, only meaningful to a
  transform that declares `has_config: true`. The same service a
  `kind: "python"` widget reaches via
  `current_context.get_transform_runner_blocking()`.
- `desk.installedJobs.run(name, configPath)` (capability
  `installed_jobs`) — runs an already-Installed Job (see
  [tempui-installed-jobs.md](./tempui-installed-jobs.md)) by name,
  same as the agent-facing `desk_run_installed_job` MCP tool — no
  approval prompt either way, since a declared capability is itself
  the trust boundary here (the same way it already is for every other
  call in this list). `configPath` is optional (`null`/omitted if not
  given); returns `{ ok, stdout, stderr, traceback }`. **Bounded to
  120 seconds**, unlike the MCP tool's unbounded wait — this is a
  synchronous HTTP request/response and can't wait forever; a job
  expected to genuinely run longer belongs on the agent/MCP path
  instead (the run itself isn't cancelled by the timeout, only this
  call's own wait for its result is).

- `desk.agents.launch(instructions, opts)` (capability `launch_agent`) —
  places a fresh Claude (Desk) session whose first turn carries
  `instructions`, e.g. a "chat about this result" button handing a
  question and answer to a new agent to discuss. `instructions` is a
  non-empty string (the text is handed to the session as a file it reads
  first, so long text is fine); `opts` is optional `{ x, y }` scene
  coordinates — omitted, the session appears just right of the calling
  widget. Returns `{ instance_id }` of the new session (fire-and-forget:
  nothing is routed back to your widget). The agent can act on the
  user's project, so declare `launch_agent` only for a widget that
  really launches one, and say in its UI that it will. A missing or
  empty `instructions` is an HTTP 400/422. (`desk.widgets.open` does
  **not** take instructions — extra keys there are ignored.)

- `desk.recorder.status()` / `.start(feature, opts)` / `.stop(feature)` /
  `.sources()` (capability `recorder`) — control **DeskRecorder.app**, the
  stand-alone recorder Desk starts for you (install it with
  `scripts/build_desk_recorder_app.sh`; without it these calls are an HTTP
  400 saying so). `feature` is `"transcribe"` (microphone → the transcript
  pool, below), `"screen"` (video of the whole screen or one window) or
  `"camera"` (video); each runs independently and macOS asks for its
  permission the first time it is started. `opts`: `{ target }` for screen
  (`"screen"`, the default, or `"window:" + encodeURIComponent(title)`),
  `{ device }` for camera (`"default"` or `encodeURIComponent(name)`; both
  names come from `sources()` → `{ sources: { window, screen, camera } }`),
  and `{ wait }` seconds to wait for the outcome (a first-time permission
  prompt can take a while; the default does not wait). `start`/`stop` resolve
  to that feature's status `{ feature, state, detail, path, dropped,
  session }`; `state` is `idle`, `starting`, `running`, `stopping`, `error`
  (see `detail`), `denied` (macOS permission refused; Screen Recording takes
  effect only after DeskRecorder is quit and reopened) or `disconnected`.
  `status()` → `{ connected, app, heartbeat_age_seconds, stale, features }`
  with all three features. **This records the user's microphone, screen or
  camera**: declare `recorder` only for a widget whose job is that, and show
  when it is recording.
- `desk.transcripts.list()` / `.read(session, opts)` (capability
  `transcripts`) — read the shared **transcript pool** that transcription
  writes, so any number of widgets can show or use what was said. `list()` →
  `{ sessions: [{ session, size, modified_ms }] }`, oldest first. `read` →
  `{ segments, next_offset }`; a segment is `{ session, seq, start_ms,
  end_ms, text, final }` (times are epoch ms, the same clock as
  `desk.log`). `{ collapsed: true }` returns the whole session with the
  latest version of each `seq`; otherwise it returns only the records after
  `{ offset }`, so tail by passing back the previous `next_offset` — a
  segment you see again with the same `seq` (a provisional one that became
  final) **replaces** the earlier one. Finished segments are also appended to
  the widget log named `transcript`, which an agent reads with
  `desk_query_widget_log`; agents can also use `desk_read_transcript`, and
  `desk_recorder_status` / `desk_recorder_control` (which record the
  user's microphone, screen or camera: only when asked to). Python widgets
  can use `desk.transcript_pool` directly.

The calls above are almost always all a `DefineWidget` widget actually
needs.

## Media (mic/camera) access

If your widget's own JS calls `navigator.mediaDevices.getUserMedia()`
(directly, or indirectly -- e.g. the Web Speech API) it needs the
`media` capability declared (a `Capability<TAB>media` line, or
`"media"` in a real `widgets/<id>/widget.json`'s `"capabilities"`
list). This is not a Bridge API HTTP call like everything else in this
section -- it gates a real browser permission
(`QWebEnginePage.featurePermissionRequested`) instead, so there's no
`desk.*` call to make for it: declare the capability, then call
`getUserMedia()` normally, exactly as you would on any other page.
Without it declared, the request is denied and the returned `Promise`
rejects with a normal, catchable error -- check `.catch()`, don't
assume the call always succeeds. Every other browser permission a page
can ask for (`Notifications`, `Geolocation`, `ClipboardReadWrite`,
screen-capture, `MouseLock`, `LocalFontsAccess`) is always denied,
regardless of any capability -- there is no way to grant those yet.

## Sending and receiving named messages

Desk has its own built-in event message channel: a **mediator**
(a component of Desk itself) that every widget talks to instead of ever
talking to another widget directly. This is how one widget can tell
another "something happened" without either needing to know the other
exists.

- `desk.events.subscribe(names)` → `{ ok: true }` — `names` is an array
  of message names (arbitrary strings you and whatever you want to
  talk to agree on, e.g. `"todo.item_added"`) you want to receive.
- `desk.events.unsubscribe(names)` → `{ ok: true }` — stop receiving
  the given names.
- `desk.events.publish(name, payload)` → `{ ok: true }` — sends a named
  message to every *other* widget instance currently subscribed to
  `name`. `payload` is any JSON-serializable value (or omit it for
  `null`). **You never receive your own publish back**, even if you're
  also subscribed to the same name — this avoids a widget accidentally
  reacting to its own message.
- `desk.events.onMessage(callback)` — registers `callback(name,
  payload, senderInstanceId)`, called for every message you're
  currently subscribed to, for as long as your widget's page stays
  open. Call `subscribe` first, then `onMessage`; there's no way to
  unregister a single callback in this first version (your whole page,
  and its polling, is torn down when the widget closes).

Identity here is always your widget's own **instance** id — the one
specific placed copy of your widget, not "your widget's `keyword`/type"
— the same identity `self.getLocalStorage`/`setLocalStorage` already
use per instance. If two instances of the same widget kind are both
placed, they have entirely independent subscriptions.

Every published message (regardless of which widget sent or received
it) is logged to `MEDIATED-EVENT-LOG.tsv` in the current Desk's
directory — a plain, tab-separated `timestamp / event_name /
sender_instance_id / payload` history of everything sent over the
channel, viewable live in Desk's built-in **Event Log** widget (which
also has a "clear the log" action, with confirmation).

`kind: "python"` widgets can use this same channel too, just not
through this JS API — they get it via a direct Python import instead
(`desk.shell.event_broker.EventSubscription`), the same "REST for html
widgets, direct Python for python widgets" split every other Bridge API
capability already follows.

### A signal, or the data itself

An event does not have to carry anything, and it does not have to be
backed by a file. Two ends of one spectrum, both fine:

- **A bare signal.** `desk.events.publish("report.updated")` with no
  payload means just "I updated the file": every subscriber re-reads the
  file it already knows about. The file holds the data; the event is the
  nudge that saves everyone from polling it.
- **The data itself.** `desk.events.publish("report.row_added", { id: 7,
  text: "..." })` skips the file altogether: put in the payload what you
  would previously have written to a file and read back. Nothing to
  write, poll, parse or clean up.

Past about **1 KB**, prefer a file, with the event announcing it (no
payload, or just `{ path }`). Every subscriber gets its own copy of the
payload, every published event is written in full to
`MEDIATED-EVENT-LOG.tsv`, and (for an agent raising one) anything over
64 KiB is refused outright. Also, events are **not kept for latecomers**:
a widget receives only what is published after it subscribes, so anything
a widget must still find after it is opened or reopened belongs in a file
(or the shared state store, below), with the event as the nudge.

An agent uses the same channel (the `desk_raise_event` and
`desk_wait_for_event` MCP tools, see `tempui-agent-events.md`), so it
follows the same rule of thumb.

## Shared, project-scoped state

Desk also keeps a shared, project-scoped key/value store — every widget
with the `state` capability can read or write any key, with no
per-widget ownership. Use this instead of hand-rolling your own
cross-widget persistence scheme (e.g. one widget writing to a file the
other polls); it also gets you change notification and a short history
for free. The built-in **State Manager** widget (TODO `6330249`) gives
a Desk user a live view/edit UI over every registered schema and the
data stored under it — reach for that instead of building your own
inspector when you just need to see or tweak what's currently there.

- `desk.state.get(key, typeHint)` → `{ value, edit }` — the current
  value for `key`, and the `edit` that was passed alongside the write
  that produced it (see below). A key nothing has ever written to
  returns `{ value: null, edit: null }`, not an error. `typeHint` is
  optional and only meaningful for a **non-validated** key (see below)
  — ignored entirely for a key that currently has a schema.
- `desk.state.set(key, value, edit, typeHint)` → `{ ok: true }` —
  writes `value` (any JSON-serializable value) as the new current value
  for `key`. `edit` is optional (omit or pass `null`) and is never
  interpreted by Desk — it's stored and handed back verbatim from
  `get`/`getHistory`, meant for widgets that want to describe *what
  changed* (e.g. a structured patch or a human-readable description)
  alongside the new full value, without Desk needing to understand that
  description's format at all. `typeHint` is optional, and only
  meaningful for a non-validated key.
- `desk.state.getHistory(key, limit)` → `{ history: [{ value, edit },
  ...] }` — up to the most recent `limit` `(value, edit)` pairs written
  to `key`, **newest first**. Desk keeps only the 50 most recent writes
  per key (older ones are dropped as new ones arrive); asking for a
  `limit` larger than what's kept just returns everything available,
  never an error. Omit `limit` for the full kept history.

Every `set` also publishes `desk.state.changed` with payload `{ key,
value, edit }` over the same `desk.events` channel described above —
subscribe to it (`desk.events.subscribe(["desk.state.changed"])`,
capability `events`, in addition to `state`) to react to another
widget's writes live rather than polling `get`. As with any
`desk.events` message, you never receive your own `set` echoed back to
you.

### Validated vs. non-validated keys (TODO af7898b)

A key is **validated** if some widget currently declares a schema for
it (a `state_schema` entry in that widget's own manifest — see
`StateSchema<TAB>key<TAB>type_expr` above for a `DefineWidget`, or the
`"state_schema"` field of a real `widgets/<id>/widget.json`), or if a
**top-level schema file** declares it (see below), and **non-validated**
otherwise — this is a property of the key itself, not of any individual
`get`/`set` call.

- A schema (`type_expr`) is a string in a small, intentionally
  -constrained subset of TypeScript type syntax: primitives (`string`,
  `number`, `boolean`, `null`), literal unions (`"a" | "b"`, `1 | 2`),
  arrays (`string[]`, `number[][]`), and simple object shapes (`{ a:
  string; b?: number }`, extra keys beyond those declared are always
  allowed). No generics, tuples, or intersections in this version.
- **`set` on a validated key**: `value` is checked against the active
  schema. A mismatch is a real error (the call fails, nothing is stored
  or published) — this holds even if *you* didn't declare the schema
  yourself; whichever widget's manifest currently owns `key`'s schema
  governs every write to it. `typeHint` is ignored.
- **`set`/`get` on a non-validated key**: `typeHint` (the same small
  type-expression syntax as a schema) is optional and purely
  call-site-local — `set` best-effort-coerces `value` to it before
  storing; `get` best-effort-coerces the *returned* value only (the
  stored value itself is untouched). Coercion never fails the call —
  a hopeless coercion just returns the value unchanged. Omitting
  `typeHint` entirely (the common case) stores/returns exactly what was
  given, no coercion at all.
- **Declaring a schema that conflicts with an already-active one for
  the same key** means your widget doesn't load at all — no placement,
  not even a normal placement notification. Instead, a clickable
  notification appears explaining the conflict, and
  `self.getManifest()`'s response gains a `desk_widget_loading_errors`
  array with the same message, for as long as the conflict is still
  live.
- **Top-level schema files** (TODO `9aef267`) declare a schema
  independent of any widget's manifest — for state that should have a
  canonical schema without tying its lifecycle to any one widget's own
  placement. A schema file is a plain JSON file, `{"<key>": "<type
  expression>", ...}` (the same syntax as a manifest's own
  `state_schema`), placed in either of two watched locations:
  `.desk_temp/schemas/` (ephemeral — created automatically alongside
  the rest of `.desk_temp`, not git-tracked), or `./desk-schemas/` (a
  real, git-tracked project-root directory Desk never creates itself —
  create it yourself and it's picked up automatically, no restart
  needed). Only `*.json` files are read; the filename itself carries no
  meaning beyond that extension, so name it for what it holds (e.g.
  `document-state.json`). A key declared this way is **permanently
  enforced** from the moment the file is picked up — unlike a
  tempui-placed widget's own schema, it's never tied to any widget
  being placed and never goes dormant. Editing the file live-updates
  its registrations; deleting it clears them. A conflicting file (or a
  file conflicting with an already-active widget-declared schema) gets
  the same clickable-notification treatment as a widget-vs-widget
  conflict above, just with no `desk_widget_loading_errors`-equivalent
  to write into (there's no manifest to attach it to) — the live
  notification is authoritative while the conflict lasts.

## Inspecting another widget

`desk.introspect.snapshot(targetInstanceId)` → `{ dom, console }` gets
a snapshot of *another* `kind: "html"` widget instance's own rendered
page: `dom` is a tree (`{ tag, attrs, children }` for an element,
`{ text }` for text content — bounded: max depth 12, max 50 children
per node, attribute/text values truncated to 200 characters) rooted at
that page's `<html>` element; `console` is its recent
`console.log`/`warn`/`error` output (level, message, line, source —
capped at the most recent 200 entries).

**This is the one Bridge API capability that isn't just a manifest
declaration** — the first time your widget asks to inspect a
particular target, the Desk *user* sees a confirmation dialog naming
both widgets and must approve it before you get anything back
(declining gives you a failed call, not empty/fake data). Once
approved, that specific (your widget, that target) pairing won't be
re-prompted again for the rest of the session — asking to inspect a
*different* target still prompts fresh. This is because inspecting
another widget's rendered content and console output is materially
more sensitive than anything else in the Bridge API; declaring the
`introspect` capability in your manifest is necessary but not
sufficient on its own.

`targetInstanceId` is that widget's own instance id (e.g. from
`desk.workspace.getState()`, capability `workspace`, or
`desk.widgets.list()`, capability `widgets`) — not its `kind`/type.
