# Plan: TODO d4368bd — shared "auto-load/auto-save document editor" widget base type

From `../FEEDBACK/FEEDBACK-DESK-editor-widget-base-types-2026-07-30-1021.md`:
the missing-directory `writeFile` bug (see TODO `ad20867`, which fixes
its root cause server-side) shipped in four separate widgets because
every one of them hand-rolled its own file lifecycle (title → path
derivation, load-if-exists, create-if-not, save-on-edit) from scratch —
there's nothing to reach for *except* writing it from scratch. The
actual fix this feedback is about isn't the directory bug specifically
(TODO `ad20867` already closes that for everyone, unconditionally) —
it's that a widget author should be able to reach for a ready-made
"auto-load/auto-save document editor" base and skip re-deriving that
lifecycle a fifth time.

## Before implementing: read the real source this was extracted from

Unlike TODO `3b1ef3d` (the `hsv-color-picker` shared component, which
was built by reading `../necro-4x/custom_widget_src/
terrain-color-initializer/terrain-color-initializer.ts` in full first),
this plan was written *without* yet reading `../necro-4x`'s actual
Domain Analysis widget (`persist`/`createDomain`, TODO `906df91` in that
project) — worth flagging honestly rather than architecting purely from
the feedback's own prose description. **First implementation step:**
read that real widget's source (and the three terrain/token/color
-initializer ones the feedback also cites, for the load/auto-save shape
they all independently converged on) before writing the base class, the
same "extract from real, already-debugged code" discipline TODO
`3b1ef3d` established — the design below is a reasonable starting
sketch, not a final API to implement verbatim without checking it
against what real widgets actually needed.

## Design (subject to revision once the real source above is read)

### Where it lives

`shared-components/document-editor-base/` — same structure as
`hsv-color-picker/` (TODO `3b1ef3d`): a `.ts` file, a `README.md`, mirrored
into every project's own `.desk_temp/shared-components/` automatically
via the existing `sync_shared_components` (no changes needed there —
it already mirrors the whole `shared-components/` tree, not a hardcoded
per-component list).

### Shape: a base class, not a handle object

Deliberately **not** the feedback's second suggestion (a generic
`desk.fs.openDocument(path)` handle with `.read()`/`.write()`) — a
widget author extending a base class is where actual reuse happens
(override "what does this document contain"/"how do I render it," never
touch `desk.fs.*` directly); a lower-level handle object still leaves
the load-on-mount/save-on-edit/title-to-path plumbing to be
re-written around it every time, which is the actual recurring cost
this feedback is about.

Sketch: `abstract class DocumentEditorBase extends HTMLElement`,
configured by a subclass (via constructor args or overridden
getters) with a target directory and file extension. Responsibilities
the base class owns, so a subclass never touches `desk.fs.*` directly:

- **Path derivation**: `<directory>/<kebab-case(title)>.<extension>`
  from a `title` the subclass provides/updates.
- **Load on mount**: `desk.fs.readFile` the derived path; a missing
  file (not-yet-created document) is a normal empty-initial-document
  case, not an error — calls an overridable `onLoad(contents: string |
  null)` (`null` = didn't exist yet) rather than requiring every
  subclass to separately branch on read failure.
- **Save on edit**: an overridable `getContents(): string` the subclass
  implements; the base class calls `desk.fs.writeFile` (debounced —
  the same "auto-save on every edit, not spammed on every keystroke"
  shape the four hand-rolled widgets each converged on independently)
  whenever the subclass signals a change (`this.scheduleSave()` or
  similar). After TODO `ad20867` lands, this can never hit the
  missing-directory bug — one more reason that fix should land first.
- **Never silently clobbers**: create-vs-load semantics are explicit
  (loading an existing file never overwrites it until the subclass
  itself changes something) — matching the feedback's own "create/
  load/rename-free semantics" phrasing.

### Error visibility

The feedback explicitly ties this back to TODO `d4d6c71` (the titlebar
`[ERROR]` indicator, already implemented for `kind: "html"` widgets via
`ChromiumWidget`'s captured console errors): a rejected save/load
should `console.error(...)` with a clear message rather than swallowing
it, so it surfaces through the already-built mechanism for free — no
new plumbing needed on the Desk-shell side, just making sure this base
class's own error paths actually log instead of failing silently
(closing the same "widget looks inert, no error anywhere" symptom the
feedback's own evidence is built entirely around).

## Verification

New `tests/verify/verify_shared_document_editor_base.py`, mirroring
`verify_shared_components.py`'s real-`tsc`-compile +
real-headless-Chrome shape:

- A real, minimal subclass (a throwaway test widget extending the base
  class) compiled with real `tsc --strict`, loaded in a real
  `QWebEngineView` against a real running Local Web Server (matching
  `verify_html_widget_local_storage.py`'s end-to-end pattern, needed
  here since this exercises real `desk.fs.*` Bridge calls, not just DOM
  interaction the way `hsv-color-picker`'s own test could get away with
  a `data:` URL).
- **The actual bug this exists to prevent, reproduced and confirmed
  fixed**: mount the widget with a title whose derived path's directory
  doesn't exist yet — confirm the file is created and readable
  afterward (this is the precise failure shape all four cited widgets
  hit).
- Loading an existing file's contents on mount; editing schedules a
  debounced save that doesn't clobber an untouched document; a rejected
  write logs a console error (verifiable via `ChromiumWidget`'s own
  captured console log / TODO `d4d6c71`'s error-capture mechanism,
  confirming the two features actually compose as designed).
- `sync_shared_components`/doc-mention checks, matching TODO `3b1ef3d`'s
  own precedent for a new shared-components entry.
- Full `tests/verify/` regression suite.
