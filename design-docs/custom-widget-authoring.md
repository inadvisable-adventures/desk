# Desk — `DefineWidget` Custom Widget Authoring & Lifecycle

This document specifies how a `DefineWidget` tempui custom widget (see
`tempui-custom-widgets.md`, `desk.custom_widgets`, `desk.temp_ui
.CustomWidgetDefinition`) should be **authored** from real source, and closes
three lifecycle gaps identified while building one for real in another
project. Source: `FEEDBACK-DESK-widget-building-2026-07-14-1242.md` (a peer
project's feedback file, written by a Claude instance building
`widgets/lifeforce-heart/` in that project's own repo, `necro-4x`).

`DefineWidget` itself already covers the *delivery* format well: one
self-contained, base64-encoded HTML document. This doc adds the missing
pieces: a repeatable *authoring* format that satisfies this project's own
CLAUDE.md constraints (strict TypeScript, `<template>`/`<slot>` over
string-built HTML), and three fixes to rough edges in the define/place/run
lifecycle that cost real debugging time.

## 1. A repeatable authoring pattern: source directory + generic build script

Hand-writing a `DefineWidget` file's inline `<script>` as plain JS with
markup assembled via `innerHTML` satisfies neither of CLAUDE.md's browser
-code constraints. Instead, a widget should be authored as a small source
directory and mechanically packaged.

**Current state (as of TODO 59c5a70/029047b): this section originally
recommended a project-root `custom_widget_src/<name>/` directory and a
`scripts/build_widget.py` seeded once per project. Both have since
moved — see below for their current locations. The four-file layout
and build steps themselves are unchanged.**

### Per-widget source layout

A widget's *source* lives at `.desk_temp/widgets/<name>/` before
promotion, and `desk_widgets/<name>/` at the project root after (TODO
59c5a70) — distinct either way from the runtime
`.desk_temp/custom_widgets/<keyword>/` materialized cache, and
deliberately **not** under the project's own top-level `widgets/`,
since that directory is scanned by Desk's own widget discovery, which
expects every `widget.json` there to have a `kind` of `"python"` or
`"html"` — this directory's `widget.json` has a different shape and
would break that scan if placed there instead. Four files:

- **`<name>.ts`** — the widget's logic as a custom element (`class Foo
  extends HTMLElement`), written in normal strict TypeScript. No knowledge
  of base64/tempui/Desk leaks into this file — it just calls
  `document.getElementById("<name>-template")`, clones its `.content`, and
  attaches it to a shadow root. The only Desk-specific surface it touches is
  the Bridge API (`window.desk...`), guarded by `if (window.desk)` so the
  file still works if opened as a plain page outside Desk.
- **`widget.html`** — the eventual self-contained document, authored with a
  placeholder: a `<template id="<name>-template">` holding the real markup
  and a scoped `<style>` (this is where CLAUDE.md's template/slot
  preference is honored — shadow DOM content is real markup, not a JS
  string), a `<script>` containing only a marker comment
  (`/* BUILD:COMPILED_JS */`), and the actual `<name-tag></name-tag>`
  element instantiation.
- **`tsconfig.json`** — whatever strictness the project wants (`strict:
  true` at minimum, per CLAUDE.md). No project-wide `package.json` needed —
  a single-directory `tsc -p <dir>` works standalone if `tsc` is already on
  `PATH`.
- **`widget.json`** — a tiny manifest: `{"keyword", "label", "width",
  "height"}`, i.e. exactly the fields a `DefineWidget`/`Size` tempui line
  needs. Keeping this as data (rather than hardcoding it into the build
  script) is what makes the build script reusable across every widget
  authored this way.

### The build script

One generic script, `.desk_temp/build_widget.py` (stdlib-only — no new
dependency, matching CLAUDE.md's "avoid adding dependencies"), takes a
widget source directory and:

1. Runs `tsc -p <widget-dir>`.
2. Concatenates the compiled `.js` output.
3. Substitutes it into `widget.html` in place of the `BUILD:COMPILED_JS`
   marker comment.
4. Base64-encodes the resulting HTML document.
5. Writes a `DefineWidget` tempui file (`DefineWidget<TAB>keyword<TAB>label`,
   `Size<TAB>w<TAB>h`, one or more chunked `Html<TAB>...` lines) to a fresh
   UUID under `.desk_temp/`.

Authoring happens once in TS + template HTML; `python3
.desk_temp/build_widget.py .desk_temp/widgets/<name>` (or
`desk_widgets/<name>` once promoted) repackages it any time it changes,
and the packaging step is entirely mechanical and never hand-edited.

### Where the build script itself lives (TODO 029047b)

It isn't a file seeded once into a new project (as it originally was,
TODO b324217, the same way `scripts/todo_item_ids.py` still is) — its
own content changes exactly as often as the rest of the tempui doc set
does, and a one-time seed would leave an older project's copy stale
forever, the same staleness problem the doc-split versioning (TODO
e57ce5f) already solved. It's generated into `.desk_temp/build_widget
.py` instead, refreshed automatically by the same mechanism
(`desk.temp_ui.write_tempui_docs`/`ensure_docs_current`) that keeps
`desk-temporary-ui.md`/`tempui-custom-widgets.md`/etc. current — see
`desk.temp_ui.SPLIT_DOC_CONTENT`'s `BUILD_WIDGET_SCRIPT_FILENAME`
entry, which isn't itself a Markdown doc but is treated identically by
that write/refresh path.

## 2. Gap: `DefineWidget` registers a kind, it doesn't place an instance

Dropping a `DefineWidget` file into `.desk_temp/` registers the widget kind
(it appears in `desk-temporary-ui.md`'s auto-generated registered-widgets
list, and a matching `custom_widgets/<keyword>/index.html` is materialized)
but produces **no user-facing notification and places no widget instance**.
Placing an instance requires a *separate* tempui file whose entire first
line is just the keyword (`tempui-custom-widgets.md`'s "Invoking a defined
widget" section already documents this) — but `DefineWidget` is the only
tempui kind that's a two-step dance, and every other kind (`Question`,
`Scratch`, ...) both defines and surfaces a notification in one step. It's
easy to read `DefineWidget`'s own section, see it succeed with no error,
and reasonably assume that's the whole job.

Concretely, in code: `DeskWindow._on_temp_ui_file_added` calls
`_handle_define_widget_file(path)` first, and returns immediately if that
returns `True` — skipping `_notify_temp_ui` entirely, with nothing else to
signal that the drop succeeded but the "obvious next step" (seeing it) was
never taken.

**Fix**: a one-line callout at the very top of `DefineWidget`'s section in
`tempui-custom-widgets.md` — defining a widget kind never places an
instance, whether the keyword is brand-new or only being redefined; you
always need a second, separate invocation file, see below — instead of
leaving it implied by section ordering.

**Tried and reverted**: TODO `5ff02d2` originally paired the doc callout
above with also auto-placing one instance the first time a genuinely new
keyword was registered live (not a bulk startup/Desk-switch rescan, and
not a re-save/edit of an existing keyword) — the theory being that "I just
wrote this widget, of course I want to see it" is the overwhelmingly
common case. TODO `dafbaab` reverted the auto-place half entirely, per
direct user feedback that it proved too confusing in practice (presumably
because it made `DefineWidget` behave *inconsistently* with itself —
sometimes a one-step dance, sometimes two, depending on whether the
keyword happened to be new — rather than the flat, predictable "always
two steps" rule every other case already had to learn anyway). Only the
doc-callout half of the original fix remains.

## 3. Gap: no way to tell which code version a placed instance is running

A placed `DefineWidget` instance's `QWebEngineView` loads its widget's URL
once, at placement time, and only reloads on an explicit
`HotReloadBroker.widget_changed` signal or a manual reload — it does not
re-fetch just because `custom_widgets/<keyword>/index.html` changed on disk
later. That's the right design (a widget shouldn't silently mutate under a
user's cursor), but it has a sharp edge: from outside a running instance,
there's no way to tell which version of the code it's actually executing.
Answering "is this specific placed widget running old code?" currently
means decoding base64 by hand, reading through the runner/materialization
code path, and asking a human to reload and report back — all to answer a
question that should have a one-line answer.

**Fix:** compute a short content hash (e.g. the first 12 hex digits of an
MD5 of the decoded HTML) when a `CustomWidgetDefinition` is registered
(`DeskWindow._register_custom_widget`, alongside the existing
`desk.custom_widgets.materialize` call), and:

- Store it on the widget's `WidgetInfo` (`content_hash: str | None`,
  `None` for every ordinary `widgets/<id>/widget.json`-backed widget —
  this is a tempui-custom-widget-only concept) so it's live-queryable —
  a widget's own JS can call `desk.self.getManifest()` and get the
  *currently-registered* definition's hash, without decoding base64 or
  spinning up a separate headless browser to check "does the source I
  think I wrote match what Desk has registered."
- Track, per placed instance, the content hash that was current *at
  placement time* (alongside `instance_id`/`widget_id` in the placed
  frame's own state), so Desk itself — not just the widget's own JS — can
  tell, at any later point, whether a specific placed instance predates
  the currently-registered definition, and surface that as a passive
  indicator in the frame's own chrome (e.g. the `[TEMPUI]` button's
  tooltip) rather than requiring a widget author to opt in by writing
  code to display it themselves. This is the more valuable half of the
  fix: it helps a human debugging their own Desk canvas without touching
  devtools at all, and "why doesn't my widget look right" almost always
  reduces to "which build is this instance actually running."

## 4. Gap: `desk.fs.*` has no project-root resolution, and `events` deserves top billing for cross-widget signaling

`desk.fs.readFile`/`writeFile` (`fs_read_file`/`fs_write_file` in
`desk/server/app.py`) resolve a `path` argument with exactly
`Path(path).read_text()`/`.write_text()` — no resolution against the
*current Desk's own directory* at all. A relative path like
`.desk_temp/<uuid>` resolves against the Desk Python process's own working
directory, which has no reliable relationship to whichever project is
actually open — so a widget's `desk.fs.writeFile('.desk_temp/<uuid>', ...)`
call can silently write somewhere the user never sees, with no error at
all. Compounding this, no Bridge API call currently exposes the open Desk's
own directory to widget JS (`self.getManifest()` returns only
id/kind/name/capabilities/default_size), so there's no way to construct a
*correct* absolute path from inside a widget even if you wanted to route
around the relative-path problem yourself.

**Fix, two parts:**

- Resolve a relative `desk.fs.*` path against the current Desk's own
  directory, server-side, instead of the server process's ambient working
  directory.
- Expose the current Desk's directory through `self.getManifest()` (a new
  `directory` field) so a widget that genuinely needs to construct a
  project-relative path itself can do so correctly and portably.

Separately, and arguably more important than the path-resolution bug
itself: **for anything resembling "notify/signal another part of the
system," `desk.events.*` is a much better fit than `desk.fs.*` and should
be the *first* thing `tempui-custom-widgets.md`'s Bridge API section points
a widget author to.** It needs no path at all, and it's genuine cross
-widget delivery instead of a same-directory side effect masquerading as
one. The doc currently mentions `events`' `.publish`/`.onMessage` calls only
in passing, in the same flat list as `fs`/`workspace`/`widgets`, with none
of the "this is probably what you actually want for cross-widget
communication — most other calls here are single-widget-scoped" framing
that would surface it sooner. The Bridge API section should say this
explicitly, near the top of the capability list, not leave it to be
discovered only by reading `desk/server/app.py`'s source directly.
