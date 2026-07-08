# Widget manifest & loader (COMPLETED)

## Summary

Introduce the `widget.json` manifest described in
`design-docs/architecture.md`'s Widget Model (currently just a sketch) as
the real, required source of truth for widget metadata, replacing the
current ad hoc "infer kind from which file exists" discovery in
`desk.widgets.discover_widgets`. Concretely: `name` (display title),
`entry` (the widget's entry file), `kind` (`"python"`/`"html"`),
`capabilities` (declared, not yet enforced — enforcement needs the Bridge
API, TODO 12), and `default_size` all come from the manifest now, and flow
through to the Shell (titlebar text, initial widget size) instead of the
placeholders used so far (widget id as title, one hardcoded canvas-wide
default size).

Per TODO item 7's original framing ("mounting `kind: "html"` widgets as
`ChromiumWidget` instances ... instead of the iframe approach originally
described"): that part is already done as of TODO 5/9 — the design doc no
longer mentions iframes anywhere (confirmed via `grep`) and `html`-kind
widgets are already `ChromiumWidget` instances. This plan's actual
remaining scope is the manifest/loader piece.

## Affected files

- `src/desk/widgets.py` (edit) — `WidgetInfo` gains `name: str`, `entry:
  str`, `capabilities: list[str]`, `default_size: tuple[int, int] | None`.
  `discover_widgets` now requires a `widget.json` in each widget directory
  (a directory without one is not discovered as a widget at all, same as
  a directory with neither `widget.py` nor `index.html` was skipped
  before); parses it, validates `kind`, and fills in defaults for the
  other fields.
- `src/desk/shell/python_widget.py` (edit) — `_load_widget_module` and
  `PythonWidgetHost` take the widget's `entry` filename instead of
  hardcoding `"widget.py"`.
- `src/desk/shell/canvas.py` (edit) — `WorkspaceView.add_widget()` accepts
  an optional `size: tuple[int, int] | None`, using it when given and
  falling back to the existing `DEFAULT_WIDGET_SIZE` constant otherwise.
- `src/desk/shell/window.py` (edit) — pass `widget.name` as the title
  (instead of the raw id), `widget.entry` into `PythonWidgetHost`, and
  `widget.default_size` into `add_widget()`.
- `widgets/demo/widget.json` (new) — manifest for the shipped demo widget.
- `design-docs/architecture.md` (edit) — Widget Model section: note the
  manifest is now actually implemented (not just a sketch), and call out
  two "for now" simplifications (see Key Design Decisions).

## Manifest schema (for now)

```json
{
  "name": "Demo",
  "kind": "python",
  "entry": "widget.py",
  "capabilities": [],
  "default_size": { "width": 680, "height": 520 }
}
```

- `kind` — **required**, must be `"python"` or `"html"`. `discover_widgets`
  raises a clear `ValueError` (naming the widget's directory) if missing
  or invalid — this is the one field a widget author must always get
  right, so it's worth failing loudly rather than guessing.
- `name` — optional, defaults to the widget's directory name (its `id`).
- `entry` — optional, defaults to `"widget.py"` for `kind: "python"` or
  `"index.html"` for `kind: "html"`.
- `capabilities` — optional, defaults to `[]`. Stored on `WidgetInfo` but
  not enforced anywhere yet (no Bridge API exists yet to enforce against —
  TODO 12).
- `default_size` — optional `{"width": int, "height": int}`, defaults to
  `None` (canvas falls back to its own default).
- No `id` field: a widget's id is always its directory name (see Key
  Design Decisions) — not read from the manifest, even though the
  original design-doc sketch showed one.

## Implementation approach

1. `desk/widgets.py`: add a `_load_manifest(path: Path) -> dict` helper
   that reads and `json.loads`s `path / "widget.json"`. In
   `discover_widgets`, for each subdirectory: skip if no `widget.json`;
   otherwise load it, validate `kind` is `"python"` or `"html"` (raise
   `ValueError(f"widgets/{path.name}/widget.json: ...")` otherwise), and
   build a `WidgetInfo` with the id always `path.name`, `name =
   manifest.get("name", path.name)`, `entry = manifest.get("entry",
   "widget.py" if kind == "python" else "index.html")`, `capabilities =
   manifest.get("capabilities", [])`, `default_size` parsed from the
   `{"width", "height"}` dict if present else `None`.
2. `desk/shell/python_widget.py`: `_load_widget_module(widget_id,
   widget_path, entry)` uses `widget_path / entry` instead of the
   hardcoded filename; `PythonWidgetHost.__init__` takes an `entry: str`
   param and threads it through `_rebuild`.
3. `desk/shell/canvas.py`: `add_widget(self, content, title, pos=(0,0),
   size: tuple[int, int] | None = None)` — `frame.resize(*(size or
   DEFAULT_WIDGET_SIZE))`.
4. `desk/shell/window.py`: for each widget, pass `title=widget.name`,
   `size=widget.default_size`; for `python`-kind, pass `widget.entry`
   into `PythonWidgetHost`.
5. `widgets/demo/widget.json`: the schema example above, matching the
   demo widget's existing `kind`/entry/size.
6. `design-docs/architecture.md`: update the Widget Model section's
   framing from "not built yet" to describing the real
   `discover_widgets`/`WidgetInfo` implementation, and add the two
   simplifications above to Key Design Decisions.

## Verification

1. Headless: `desk.widgets.discover_widgets(Path("widgets"))` on the repo's
   own `widgets/` directory returns a `WidgetInfo` for `demo` with the
   fields matching its new `widget.json` (name, entry, capabilities,
   default_size all present and correctly typed).
2. Headless: a throwaway widget directory with a `widget.json` missing
   `kind` raises `ValueError` from `discover_widgets` (confirms the
   required-field validation actually fires rather than silently
   defaulting or crashing with a confusing error).
3. Headless: a throwaway widget directory with *no* `widget.json` at all
   is simply not included in `discover_widgets`'s result (confirms the
   "manifest required" cutover doesn't crash on non-widget directories).
4. Launch the real app (`python -m desk`); confirm via `ps` it starts and
   stays running, and that the demo widget's titlebar would show "Demo"
   (its manifest `name`) rather than the raw id `demo` — check this via
   a quick headless instantiation of `DeskWindow`'s title-passing logic
   if a full visual check isn't reliable in this environment (see below),
   or by confirming `WidgetInfo.name == "Demo"` end-to-end from
   `discover_widgets` through to what gets passed to `add_widget`.
5. Confirm hot reload still works: the existing `desk.shell.python_widget:
   Rebuilding widget demo` log line still fires when `widgets/demo/
   widget.py` is edited while the app is running (this item didn't touch
   the watcher/broker path, but worth reconfirming since `PythonWidgetHost`'s
   constructor signature changed).
6. Quit the app (via a `quit` Apple Event); confirm the process exits and
   the server's port stops accepting connections.
7. Visual confirmation of the titlebar actually showing "Demo" (rather
   than just tracing the value programmatically) is expected to be
   **skipped**, per the precedent in `plans/desk-shell.md` and later plans
   (screenshots haven't reliably shown this app's window contents in this
   environment).

### Status (verification notes)

- Headless: `discover_widgets(Path("widgets"))` on the repo's real
  `widgets/` directory returns `WidgetInfo(id='demo', kind='python',
  name='Demo', entry='widget.py', capabilities=[], default_size=(680,
  520))` — matches `widgets/demo/widget.json` exactly.
- Headless: a throwaway directory with a `widget.json` missing `kind`
  raises `ValueError` naming the widget's path, as designed.
- Headless: a throwaway directory with no `widget.json` at all (just a
  `widget.py`) is correctly excluded from `discover_widgets`'s result.
- Launched the real app (`python -m desk`); it started cleanly, logging
  the same `demo`/`python` widget as before. (Found and cleaned up an
  unrelated stray `python -m desk` process left over from an earlier
  session/turn while doing this — not related to this change.)
- Edited `widgets/demo/widget.py` while the app was running: the
  `desk.shell.python_widget: Rebuilding widget demo` log line still fired,
  confirming hot reload survived `PythonWidgetHost`'s constructor gaining
  the new `entry` parameter.
- Quit via a `quit` Apple Event; confirmed via `ps` the process exited and
  via `curl` the server's port stopped accepting connections; no
  `__pycache__` left behind under `widgets/`.
- Visual confirmation that the titlebar actually renders "Demo" (rather
  than tracing `WidgetInfo.name` programmatically end-to-end, which was
  done) was **skipped**, per the precedent in `plans/desk-shell.md` and
  later plans (screenshots haven't reliably shown this app's window
  contents in this environment).

## Key design decisions / tradeoffs

- **Manifest required, ad hoc kind-detection removed entirely, rather than
  keeping both.** Maintaining two parallel discovery mechanisms
  indefinitely (manifest-if-present, else infer) would be more surface
  area for less benefit than just cutting over now, while Desk only ships
  one widget of its own to update. This is exactly what "Widget manifest &
  loader" as a TODO item is meant to establish as the real mechanism going
  forward.
- **Widget id is always the directory name, never read from the
  manifest** (even though the original design-doc sketch showed an `id`
  field). `WidgetWatcher` computes the changed widget's id from the first
  path component under `widgets_dir` (i.e. the directory name) — if a
  manifest's `id` could differ from its directory name, hot reload's
  watcher-emitted id and the discovery map's key would disagree and
  silently never match. Simplest correct fix: don't support a
  manifest-declared id at all yet; the directory name is the identity,
  full stop. A manifest `id` field could be reintroduced later if the
  watcher is changed to resolve ids by scanning rather than by path
  position, but that's not needed now.
- **`entry` is honored for `python`-kind widgets but effectively fixed to
  `index.html` for `html`-kind.** `python`-kind loading
  (`_load_widget_module`) is a simple `Path` join, so honoring a custom
  `entry` costs nothing. `html`-kind serving uses FastAPI's
  `StaticFiles(..., html=True)`, which specifically serves `index.html`
  for directory requests — supporting an arbitrary entry filename there
  would need custom routing instead of that convenience mount. Not worth
  building until an `html`-kind widget actually wants a non-`index.html`
  entry; noted as a known limitation rather than silently ignored.
- **`capabilities` stored but unenforced.** There's no Bridge API yet to
  enforce them against (TODO 12) — declaring the field now (rather than
  waiting) means widget authors can start writing manifests against the
  real final schema instead of an incomplete one that grows a field later.
