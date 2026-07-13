# TempUI-defined custom widgets (HTML-only), invocation, and promotion to the Desk (COMPLETED)

TODO `91b3f42`.

## Summary

A new tempui DSL construct, `DefineWidget`, lets an agent (or any
process writing into `.desk_temp/`) introduce a brand-new *kind* of
widget for the current Desk, without touching the `widgets/` directory
or writing any Python: the widget's entire implementation is a single,
base64-encoded, self-contained `index.html` (inline `<style>`/
`<script>` cover CSS/JS -- see Key decisions), rendered exactly like an
existing `kind: "html"` widget (`ChromiumWidget` + the Local Web
Server's static-file mount -- this mechanism already existed, just
unused by any in-tree widget until now).

Once defined, the new widget kind gets its own new tempui DSL keyword
(chosen by whoever wrote the `DefineWidget` file) that a *later*,
separate tempui file can use to place an instance of it -- "extending
the DSL so a tempui-defined widget can be invoked by tempui," as
requested. A widget defined this way can **only** ever be placed via
tempui invocation -- it never appears in the right-click "Add widget"
catalog.

Every placed instance of a custom widget gets a `[TEMPUI]` titlebar
button. Clicking it offers to **promote** the widget: on confirm, its
definition (label, keyword, base64 HTML, default size) is appended to
a new list in the `.desk` file (`Desk.custom_widgets`), the Desk is
saved immediately, and the `DefineWidget` file that originally defined
it is deleted from `.desk_temp` -- the `.desk` file becomes the sole
remaining source of truth. No re-mounting/re-pointing of the actually
-served files is needed (see Key decisions' materialization-cache
design) -- only which side is authoritative changes.

`.desk`-file-sourced custom widgets are registered into the live
widget catalog at startup and on Desk switch, the same as
tempui-sourced ones -- "registered just like built-in widgets," per
the request, meaning: present in `self._widgets` so `_place_widget`/
`_load_desk_widgets` can place instances of them, exactly like any
`widgets/<id>/` discovery result, just sourced from base64 instead of
files on disk.

`desk-temporary-ui.md` gets a new static section (for agents) documenting
`DefineWidget`/invocation, plus a dynamically-regenerated section
listing every *currently* registered custom widget (both `.desk_temp`
-sourced and `.desk`-file-sourced), refreshed at startup and whenever a
new one is registered.

## Key decisions

- **A custom widget's "code" is one self-contained `index.html`
  document, not separate HTML/CSS/JS files.** The request says
  "in-browser (html/css/js) widgets" -- a single HTML file with inline
  `<style>`/`<script>` covers all three without inventing a multi-file
  bundling/base64 scheme (which file is CSS vs JS vs HTML, how they're
  concatenated, etc.). This is the simplest design that still satisfies
  "html/css/js" literally, and matches how `kind: "html"` widgets are
  already served (`StaticFiles(..., html=True)` on a directory -- one
  `index.html` is the normal, simplest case of that).
- **Widget kind + tempui invocation keyword are the same identifier.**
  A `DefineWidget` line supplies one keyword that's simultaneously (a)
  the new DSL keyword a later tempui file invokes, and (b) the widget
  catalog id (`self._widgets[keyword]`). Avoids a separate
  slug-derivation step and keeps "how do I invoke this" and "what's its
  id" the same answer.
- **Invocation carries no per-instance parameters.** A tempui file that
  invokes a custom widget is just its bare keyword on the first line,
  nothing else (`KanbanBoard`, say). Considered a per-instance label
  (`KanbanBoard My sprint board`, mirroring `Scratch`/`Markdown`'s
  shape) but dropped it: `kind: "html"` widgets are `ChromiumWidget`
  instances with no duck-typed `set_label`-style hook the way `python`
  -kind widgets have (`_bind_temp_ui_content`'s whole dispatch shape
  assumes a `PythonWidgetHost`), so there's nowhere for a per-instance
  label to actually go without inventing a new content-injection
  channel into the page itself -- out of scope here. The instance's
  titlebar title is always the *type's* own label (`widget.name`,
  already human-friendly, matching the "human-friendly label, no
  UUIDs" requirement directly).
- **Materialized HTML is a disposable cache, regenerated fresh into one
  unified location regardless of source** --
  `.desk_temp/custom_widgets/<keyword>/index.html`, decoded from
  whichever `CustomWidgetDefinition` (tempui file or `.desk` file) is
  currently authoritative for that keyword. This is what makes
  promotion's "re-pointing" step free: the served URL/directory never
  moves, only the bookkeeping of which side is authoritative changes
  and the tempui-side source file gets deleted. (This does mean the
  materialized cache lives under `.desk_temp/`, which does still exist
  when a widget is `.desk`-file-sourced -- reasonable, since `.desk_temp`
  is already this app's own general-purpose per-directory scratch
  space, not exclusively for not-yet-promoted content.)
- **`kind: "html"` only, `ChromiumWidget` only** -- exactly what's
  requested ("no python"). No dynamic Python widget kind is introduced;
  `PythonWidgetHost`/`importlib`-based loading is untouched.
- **Reserved-keyword/id collision is checked once, at registration,
  not continuously reconciled.** A `DefineWidget` can't shadow a
  built-in DSL keyword (`Question`/`LightningRound`/etc.) or an
  already-known catalog id (a real `widgets/<id>/` or another custom
  widget from a *different* source) -- logged and silently skipped, the
  same "unrecognized/conflicting input is ignored, not an error"
  posture this DSL already has everywhere else. Not defended: a real
  `widgets/<id>/` directory added *after* a custom widget with the same
  id already exists (a rare, self-inflicted setup) -- accepted as a
  known limitation rather than adding continuous reconciliation for an
  edge case nobody is likely to hit.
- **Scope explicitly excludes the Bridge API** (`/api/bridge/widgets/*`
  in `src/desk/server/app.py`): "widgets defined in tempui can only be
  added to the Desk by tempui" is enforced at the two real
  human-facing placement avenues (the right-click spawn menu, and
  nowhere else a human can place a widget) -- the Bridge API's
  `widgets/open` doesn't discriminate by kind today for *any* widget,
  and teaching it about `tempui_only` is a separate, unasked-for
  hardening question about *inter-widget* capability boundaries, not
  this feature.
- **The tempui doc's dynamic section is patched in place, not a blind
  overwrite** -- delimited by HTML-comment markers
  (`<!-- BEGIN/END: registered custom widgets -->`), so a user's own
  edits elsewhere in `desk-temporary-ui.md` are never clobbered by a
  refresh, matching this codebase's established "never silently
  overwrite existing content" posture (e.g. `_seed_development_process`,
  `ensure_gitignore_entry`).

## DSL additions (`src/desk/temp_ui.py`)

**Defining a new widget kind** -- first line, tab-separated (matching
`LightningRound`'s multi-value shape, since a label may contain
spaces):

```
DefineWidget	<keyword>	<label>
```

Optionally, a `Size` line (also tab-separated):

```
Size	<width>	<height>
```

Then one or more `Html` lines, each carrying one chunk of the
base64-encoded `index.html` document (split across multiple lines only
because a single line has to hold the *entire* file otherwise --
concatenated in file order before decoding):

```
Html	<base64 chunk>
Html	<base64 chunk>
...
```

Example:

```
DefineWidget	KanbanBoard	Kanban Board
Size	600	400
Html	PGh0bWw+PGJvZHk+PGgxPkthbmJhbjwvaDE+...
Html	PC9ib2R5PjwvaHRtbD4=
```

**Invoking (placing an instance of) an already-defined widget kind**
-- a separate tempui file whose *entire* first line is just the
keyword, nothing else:

```
KanbanBoard
```

New API in `desk.temp_ui`:

- `DEFINE_WIDGET_KEYWORD = "DefineWidget"`.
- `CustomWidgetDefinition` dataclass: `keyword: str`, `label: str`,
  `html_b64: str`, `default_size: tuple[int, int] | None`.
- `parse_define_widget(text) -> CustomWidgetDefinition | None`.
- `detect_temp_ui_kind(text, custom_keywords=())` gains a
  `custom_keywords` parameter (default empty, so every existing call
  site/test is unaffected unless it opts in): returns `"define_widget"`
  for a `DefineWidget` file, or `f"custom:{keyword}"` if the file's
  first line is exactly one of `custom_keywords`.
- `render_custom_widgets_section(entries: list[tuple[CustomWidgetDefinition, str]]) -> str`
  and `sync_custom_widgets_doc_section(doc_path, entries) -> None` (the
  marker-delimited patch-in-place logic above). `entries`' second tuple
  element is `"tempui"` or `"desk"`, for the doc's own "defined by ..."
  blurb.
- `DOC_TEMPLATE` gains a new "The TempUI DSL: DefineWidget" section
  (written for agents, same style as the other five), and the file
  type count in the intro paragraph updates from five to six.

## Catalog/schema additions

- `src/desk/widgets.py`: `WidgetInfo` gains `tempui_only: bool = False`
  (never set by `_parse_manifest` -- only by custom-widget
  registration). `WidgetSpawnMenu`'s catalog is filtered to exclude
  `tempui_only` entries at the one call site that constructs it
  (`WorkspaceView.contextMenuEvent`), not inside `WidgetSpawnMenu`
  itself -- keeps the "who's allowed to see this" decision in one
  place.
- `src/desk/desks.py`: `Desk` gains `custom_widgets:
  list[CustomWidgetDefinition] = field(default_factory=list)`;
  `load_desk`/`desk_state_dict` round-trip it (same nested
  `{"width":, "height":}` shape as `default_size` elsewhere in this
  file).
- `src/desk/custom_widgets.py` (new): `materialize(desk_temp_dir,
  definition) -> Path` -- base64-decodes `definition.html_b64` and
  writes it to `desk_temp_dir/custom_widgets/<keyword>/index.html`
  (creating directories as needed), returning that directory. Malformed
  base64/UTF-8 is caught and logged, not raised -- one bad definition
  shouldn't take down the whole app.
- `src/desk/server/runner.py`: `ServerHandle` gains an `_app: FastAPI`
  field (set in `start_server`) and a `mount_html_widget(widget_id,
  directory, info)` method -- adds `info` to `self.widgets` and calls
  `self._app.mount(...)` directly. FastAPI/Starlette route tables are
  just an appendable list, so mounting after the server has already
  started serving requests is safe -- this is the only way a widget
  kind discovered *after* server startup (impossible for real
  `widgets/` directories, since those are only ever discovered once,
  at `start_server`) can ever become servable.

## `DeskWindow` wiring (`src/desk/shell/window.py`)

New state: `self._custom_widget_definitions: dict[str,
CustomWidgetDefinition]`, `self._custom_widget_sources: dict[str, str]`
(`"tempui"` | `"desk"`), `self._custom_widget_source_paths: dict[str,
Path]` (tempui-sourced ones only, for deletion on promotion).

New methods:

- `_register_custom_widget(definition, source) -> bool`: the shared
  registration path (materialize, build a `kind: "html"` `WidgetInfo`
  with `tempui_only=True`, add to `self._widgets`, mount on the server,
  refresh the spawn-menu-visible catalog) used by every caller below.
  Returns `False` (and logs, doesn't raise) on a reserved-keyword/id
  collision or a cross-source redefinition attempt.
- `_register_custom_widgets_from_desk(desk)`: iterates
  `desk.custom_widgets`, registers each with `source="desk"`.
- `_register_custom_widgets_from_desk_temp(directory)`: scans
  `directory/.desk_temp` for UUID-named files whose content is
  `DefineWidget`-kind, registers each with `source="tempui"`
  (recording its source path for later deletion).
- `_handle_define_widget_file(path) -> bool`: called first from both
  `_on_temp_ui_file_added`/`_on_temp_ui_file_edited` -- if `path` is a
  `DefineWidget` file, registers/re-registers it and syncs the doc,
  returning `True` so the caller skips the normal notify/live-refresh
  flow entirely (a widget *type* definition has nothing to open as a
  notification).
- `_sync_tempui_doc()`: calls `sync_custom_widgets_doc_section` with
  the current `(definition, source)` pairs.
- `_on_tempui_promote_requested(frame)`: the `[TEMPUI]` button's
  handler -- confirms, appends to `self.current_desk.custom_widgets`,
  flips that keyword's source to `"desk"`, calls
  `self.save_current_desk()` immediately (not deferred to the next
  natural save point), deletes the original tempui definition file,
  hides nothing (the button stays -- clicking it again on an
  already-`"desk"`-sourced widget just shows an informational "already
  part of this Desk" message rather than tracking separate visible
  -vs-hidden button state), and syncs the doc.

Existing methods touched:

- `detect_temp_ui_kind` call sites (`_bind_temp_ui_content`,
  `_notify_temp_ui`, `_temp_ui_widget_id_for`) pass
  `self._custom_widget_definitions.keys()` as `custom_keywords`.
  `_temp_ui_widget_id_for` gains a `kind.startswith("custom:")` branch
  returning that keyword directly. `_notify_temp_ui` gains a matching
  branch for the notification text ("New <label>").
  `_activate_temp_ui`/`open_widget_content` need **no changes** --
  `open_widget_content` already returns `None` for `kind: "html"`
  widgets, and `_activate_temp_ui`'s existing `if content is not None:`
  guard already skips `_bind_temp_ui_content` in exactly that case,
  which is correct here (nothing to bind for an instance with no
  per-instance content).
- `_place_widget`: after building the frame, if `widget_id in
  self._custom_widget_definitions`, calls
  `frame.set_tempui_promotable(True)`.
- `_on_widget_changed_refresh_catalog`: snapshots the current custom
  `WidgetInfo` entries before calling `discover_widgets()` (which only
  ever scans the real `widgets/` directory and would otherwise silently
  drop every custom entry from the live catalog on the next hot
  -reload-triggered refresh) and merges them back in afterward.
- `__init__`/`switch_desk`: `_provision_temp_ui(...)` now runs *before*
  `_load_desk_widgets` in `__init__` too (already true in `switch_desk`
  -- this was an existing asymmetry between the two, harmless to fix
  since the one documented ordering constraint near this code
  -- `current_context.set_current_desk_directory`, set by
  `_refresh_picker` -- is unaffected). Both now run, in order:
  `_register_custom_widgets_from_desk` -> `_provision_temp_ui` ->
  `_register_custom_widgets_from_desk_temp` -> `_load_desk_widgets` ->
  ... -> `_sync_tempui_doc()`.

## Titlebar button (`src/desk/shell/widget_frame.py`, `canvas.py`)

A new `_TempuiPromoteButton` (`_TitleBar`'s new child) -- **not** a
`_TitlebarButton` subclass, since that class is sized as a fixed
square for a single glyph (✕/▲/▼/🔒/🔓) and "[TEMPUI]" (the literal
requested label) doesn't fit that shape. Fixed height (matches the
titlebar), width sized to its text. Hidden by default; shown via
`WidgetFrame.set_tempui_promotable(bool)` (mirrors `set_locked`'s
existing show/hide-a-titlebar-button shape).

Click handling is centralized in `WorkspaceView`, exactly like
close/bring-to-front/send-to-back/lock/unlock: `_BUTTON_KINDS` gains
`"tempui_promote"`, `_hit_test_chrome` recognizes
`_TempuiPromoteButton`, a new `tempui_promote_requested =
pyqtSignal(WidgetFrame)` fires from `mouseReleaseEvent`, and
`DeskWindow.__init__` connects it to `_on_tempui_promote_requested`.

## Affected files

- `src/desk/temp_ui.py` -- DSL additions above.
- `src/desk/widgets.py` -- `WidgetInfo.tempui_only`.
- `src/desk/desks.py` -- `Desk.custom_widgets`, round-tripped.
- `src/desk/custom_widgets.py` (new) -- `materialize`.
- `src/desk/server/runner.py` -- `ServerHandle._app`,
  `mount_html_widget`.
- `src/desk/shell/widget_frame.py` -- `_TempuiPromoteButton`,
  `set_tempui_promotable`.
- `src/desk/shell/canvas.py` -- signal, button-kind wiring, spawn-menu
  catalog filtering.
- `src/desk/shell/widget_spawn_menu.py` -- no code change; catalog
  filtering happens at its one call site instead (see Key decisions).
- `src/desk/shell/window.py` -- all wiring above.
- `design-docs/architecture.md` -- Widget Model section: mention
  tempui-defined custom widgets alongside the existing `kind: "html"`
  description.
- `design-docs/widget-ux.md` -- new titlebar button.
- `LEARNINGS.md` -- only if something genuinely surprising turns up
  during implementation/verification (nothing anticipated going in).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
`WorkspaceView` where placement/catalog/signal wiring matters; plain
function-level tests for the pure DSL-parsing/materialization/doc
-rendering pieces):

- `parse_define_widget`/`detect_temp_ui_kind` (fixed keyword, and
  `custom_keywords`-based detection) on well-formed and malformed
  input.
- `materialize`: valid base64 decodes to a real `index.html` at the
  expected path; malformed base64 is caught, logged, doesn't raise.
- `render_custom_widgets_section`/`sync_custom_widgets_doc_section`:
  empty list, non-empty list, first-time-append (no markers yet),
  re-sync (markers present, replaced in place, content outside the
  markers untouched).
- `Desk.custom_widgets` round-trips through `save_desk`/`load_desk`.
- `ServerHandle.mount_html_widget` (against a real, running
  `uvicorn`-backed server via `desk.server.runner.start_server`):
  mounting after startup actually serves the new content over real
  HTTP.
- End-to-end via `DeskWindow`-dependent methods bound onto a fake
  double (this session's established pattern for methods that would
  otherwise require constructing a real, stalling `DeskWindow`):
  registering a `DefineWidget` definition makes its keyword catalog
  -resolvable and reserved-keyword/collision cases are rejected;
  invoking it via `_activate_temp_ui`-equivalent logic places an
  instance with the right title and no crash; promotion appends to
  `Desk.custom_widgets`, saves immediately, removes the tempui source
  file, and a second promotion attempt is a safe no-op (informational
  message, not a duplicate list entry); the hot-reload catalog-refresh
  path preserves custom entries.
- Full scratchpad regression suite re-run.

## Status

Implemented exactly as planned, with one addition surfaced during
implementation: `DeskWindow._capture_desk_state` built a fresh `Desk`
on every save without ever passing through `custom_widgets` -- every
`save_current_desk()` call would have silently wiped out any promoted
custom widget the very next time anything else triggered a save. Fixed
by carrying `self.current_desk.custom_widgets` through explicitly
(it's not derived from `view._frames` like everything else
`_capture_desk_state` builds, since a custom widget *definition* isn't
a placed instance). Also added a small `DeskWindow._info(title,
message)` wrapper (mirroring the existing `_warn`) so the "already
promoted" informational message stays testable the same way
`_confirm_fn`/`_warn` already are, rather than calling
`QMessageBox.information` directly.

All files listed in "Affected files" above were touched as planned.
`switch_desk` also needed to *forget* the previous Desk's custom
widget registrations before registering the new Desk's (custom widgets
are per-Desk-directory state, unlike the app-wide real `widgets/`
catalog) -- not explicitly called out in the original plan text, but a
direct consequence of "registered just like built-in widgets... at
startup and after being added" applying per-Desk.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
a real `WorkspaceView`/`QGraphicsScene` where placement/catalog/signal
wiring matters, a real running `uvicorn` server via
`desk.server.runner.start_server` for the dynamic-mount check, unbound
-method-on-a-fake-double for `DeskWindow`-dependent logic): 29 new
tests across DSL parsing, `materialize`, doc-section
rendering/patching, `Desk.custom_widgets` round-tripping,
`ServerHandle.mount_html_widget` serving real content over real HTTP
after startup, `_register_custom_widget`'s collision/redefinition
rules, both registration-scan methods, `_handle_define_widget_file`,
the full promote flow (confirm -> save -> delete tempui source ->
safe-no-op on a second attempt), the `[TEMPUI]` button's
placement-time visibility, the hot-reload catalog-refresh's
custom-entry preservation, and the spawn-menu's `tempui_only`
filtering -- all pass. Confirmed each fix in this feature actually
matters, not just "the assertions happen to pass," for the two most
consequential ones: `_capture_desk_state`'s `custom_widgets` carry
-through, and the promote flow's full round trip through a real
`Desk`/save/reload cycle.

Re-ran the full scratchpad regression suite. Six pre-existing test
scripts needed updating (not left broken) because they called
`DeskWindow._temp_ui_widget_id_for`/`_capture_desk_state`/`switch_desk`
against minimal fakes/`None` that predate this TODO's new
`self._custom_widget_definitions` (etc.) reads -- these are genuine
consequences of a real, intentional API surface change (the method
now legitimately needs that state), not stale references to something
removed. Updated each fake to carry the new attributes (or a
`types.SimpleNamespace` stand-in for the `None`-as-self cases), and
extended `verify_new_desk_flow.py`'s existing ordering test to also
assert the new registration-scan/doc-sync steps land in the right
place relative to the ones it already checked. Three separate,
pre-existing, unrelated failures remain (a crash-log-directory test, a
`switch_desk` fake test double missing a `provisioning` kwarg added by
earlier work, and a stale reference to the since-renamed `markdown_ex`
directory) -- same three flagged in the two most recent prior TODOs'
plans, none touching any file edited here.

No `LEARNINGS.md` entry -- nothing here violated a reasonable
assumption or took real investigation to root-cause in the way that
file is for; the one non-obvious mechanical detail worth remembering
(Starlette route tables are appendable after the app is already
serving requests) is documented directly in
`ServerHandle.mount_html_widget`'s own docstring instead, where a
future reader touching that exact code will actually see it.
