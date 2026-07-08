# Native Qt Python widget hosting (COMPLETED)

## Summary

Per updated requirements: widgets should generally be written in Python and
should render *directly in the app*, with no local web server in between.
Since Desk is already a Qt application, use Qt directly for default widget
rendering, following ordinary Qt patterns.

Concretely, this item:

1. Introduces `PythonWidgetHost` (in the Desk Shell): given a widget
   directory with `widget.py` exposing `build() -> QWidget`, imports the
   module directly and calls `build()` in-process, on the GUI thread,
   embedding the resulting `QWidget` on the Workspace Canvas via
   `QGraphicsProxyWidget` — no HTTP, no local server, no browser.
2. Wires hot reload for `python` widgets to mean "rebuild": on a source
   change, `PythonWidgetHost` re-imports `widget.py` fresh (no caching) and
   calls `build()` again, swapping the new `QWidget` in for the old one.
3. Moves `discover_widgets`/`WidgetInfo`/`WidgetWatcher` out of
   `desk.server` into a shared `desk.widgets` module, since they're no
   longer specifically HTTP-server concerns — the Shell needs them
   directly for `python` widgets, independent of whether the Local Web
   Server is involved at all.
4. Removes `src/desk/server/python_widget.py` and the `python`-kind route
   registration in `src/desk/server/app.py` entirely — the Local Web
   Server now serves only `kind: "html"` widgets (plus, eventually, the
   Bridge API).
5. Replaces `widgets/demo/widget.py`'s `render() -> str` (HTML string) with
   `build() -> QWidget` (a native Qt widget), so the shipped example widget
   demonstrates the new default path.

This supersedes `plans/python-backed-widgets.md` (TODO item 7, now marked
superseded) and implements TODO item 8, done next ahead of item 6.

## Affected files

- `src/desk/widgets.py` (new, moved from `src/desk/server/widgets.py`) —
  `WidgetInfo`, `discover_widgets`, `WidgetWatcher`/`_DebouncedHandler`
  unchanged in behavior, just relocated so both the Shell and the server
  can depend on them without the Shell depending on `desk.server`.
- `src/desk/server/widgets.py` (deleted) — superseded by `desk.widgets`.
- `src/desk/server/python_widget.py` (deleted) — no longer needed; Python
  widgets don't render via HTTP anymore.
- `src/desk/server/app.py` (edit) — `create_app` now only mounts `kind:
  "html"` widgets (filters `discover_widgets` results by kind); drops the
  `python`-kind branch and the `render_python_widget` import entirely.
- `src/desk/server/runner.py` (edit) — imports `WidgetInfo`/`discover_widgets`
  from `desk.widgets` instead of `desk.server.widgets`; `ServerHandle.widgets`
  now reflects only the `html`-kind widgets the server actually serves;
  drops `WidgetWatcher` ownership (moved to `desk.app.main()` — see below),
  so `ServerHandle.stop()` no longer stops a watcher itself.
- `src/desk/shell/python_widget.py` (new) — `PythonWidgetHost(QWidget)`: a
  thin container (`QVBoxLayout`) that loads `widget.py` fresh, calls
  `build()`, and holds the result as its one child; on the broker's
  `widget_changed` signal matching its id, reloads and swaps the child.
- `src/desk/shell/window.py` (edit) — `DeskWindow` now takes the full
  `widgets: dict[str, WidgetInfo]` plus the server `handle` (for `html`
  widget URLs) and the `broker`; for each widget, creates a
  `PythonWidgetHost` (kind `python`) or `ChromiumWidget` (kind `html`) and
  places it on the canvas.
- `src/desk/app.py` (edit) — discovers widgets once via `desk.widgets
  .discover_widgets`, creates and starts a `WidgetWatcher` directly (no
  longer nested inside `start_server()`), starts the Local Web Server (for
  `html`-kind widgets + future Bridge API), and passes the full widget
  dict + handle + broker into `DeskWindow`. Connects `aboutToQuit` to both
  the server handle's `.stop()` and the watcher's `.stop()`.
- `widgets/demo/widget.py` (edit) — replace `render() -> str` with
  `build() -> QWidget`: a simple `QWidget` with a `QVBoxLayout` containing
  a `QLabel` showing the same kind of message/timestamp as before, styled
  via `setStyleSheet` (no HTML/CSS string building — plain Qt API calls).
- `README.md` (edit) — clarify that widgets render as native Qt directly,
  not via a browser, for the default (`python`) kind.

## Implementation approach

1. Move `src/desk/server/widgets.py` to `src/desk/widgets.py` unchanged
   (`git mv`), update its internal imports if any (none needed — it only
   imports from `desk.hotreload`, which is already a top-level module).
2. Delete `src/desk/server/python_widget.py`.
3. `src/desk/server/app.py`: update the import to `from desk.widgets import
   discover_widgets`; in `create_app`, iterate `discover_widgets(widgets_dir)
   .items()` and only handle `kind == "html"` (mount `StaticFiles`); drop
   the `kind == "python"` branch and its route-factory helper entirely.
4. `src/desk/server/runner.py`: update imports to `from desk.widgets import
   WidgetInfo, WidgetWatcher, discover_widgets`; stop constructing/owning a
   `WidgetWatcher` inside `start_server()` (remove that responsibility —
   the watcher becomes `desk.app.main()`'s concern, shared by both kinds,
   not something the server owns just because it used to serve `python`
   widgets too); `ServerHandle.widgets` becomes only the `html`-kind subset
   (filter after calling `discover_widgets`); `ServerHandle.stop()` drops
   the `self._watcher.stop(...)` call and the `_watcher` field.
5. `src/desk/shell/python_widget.py`:
   ```python
   class PythonWidgetHost(QWidget):
       def __init__(self, widget_id, widget_path, broker, parent=None):
           super().__init__(parent)
           self.widget_id = widget_id
           self.widget_path = widget_path
           self._layout = QVBoxLayout(self)
           self._layout.setContentsMargins(0, 0, 0, 0)
           self._current: QWidget | None = None
           self._rebuild()
           broker.widget_changed.connect(self._on_widget_changed)

       def _rebuild(self) -> None:
           module = _load_widget_module(self.widget_id, self.widget_path)
           widget = module.build()
           if self._current is not None:
               self._layout.removeWidget(self._current)
               self._current.deleteLater()
           self._layout.addWidget(widget)
           self._current = widget

       def _on_widget_changed(self, changed_id: str) -> None:
           if changed_id == self.widget_id:
               logger.info("Rebuilding widget %s", self.widget_id)
               self._rebuild()
   ```
   `_load_widget_module` mirrors the previous `render_python_widget`'s
   `importlib` usage, but returns the module (so `build` can be called)
   instead of calling a `render` function itself.
6. `src/desk/shell/window.py`: `DeskWindow(widgets: dict[str, WidgetInfo],
   handle: ServerHandle, broker: HotReloadBroker)` — for each widget:
   `kind == "python"` → `PythonWidgetHost(id, path, broker)`; `kind ==
   "html"` → `ChromiumWidget(id, handle.widget_url(id), broker)`. Both are
   added to the canvas the same way as before (`view.add_widget(...)`).
7. `src/desk/app.py`:
   ```python
   widgets_dir = DEFAULT_WIDGETS_DIR  # from desk.widgets or desk.server.app
   widgets = discover_widgets(widgets_dir)
   watcher = WidgetWatcher(widgets_dir, broker)
   watcher.start()
   handle = start_server(broker, widgets_dir=widgets_dir)
   app.aboutToQuit.connect(handle.stop)
   app.aboutToQuit.connect(watcher.stop)
   window = DeskWindow(widgets, handle, broker)
   ```
8. `widgets/demo/widget.py`: rewrite as described.
9. Verify no widget content changes rely on the removed HTTP path.

## Verification

1. Headless check via `urllib` with the per-launch token: `GET /api/ping`
   still returns `{"status": "ok", "widgets": []}` (empty, since `demo` is
   now `python`-kind and the server no longer knows about it at all) —
   confirms the server is correctly scoped to `html`-kind widgets only now.
2. Launch the real app; confirm via `ps` that **no** `QtWebEngineProcess`
   renderer starts this time (since there are no `html`-kind widgets at
   all currently) — a meaningful behavior change from every prior TODO
   item, worth explicitly checking.
3. With the app running, edit `widgets/demo/widget.py`'s displayed message
   (no rebuild step — it's plain Python) and confirm, via a log line added
   to `PythonWidgetHost._on_widget_changed`, that the watcher still fires
   and the widget host rebuilds.
4. Quit the app (via a `quit` Apple Event, as before); confirm via `ps`
   that the process exits and via `curl` that the server's port stops
   accepting connections.
5. Visual confirmation of the rendered native widget is expected to be
   **skipped**, per the precedent in `plans/desk-shell.md` and later plans
   (screenshots haven't reliably shown this app's window contents in this
   environment).

### Status (verification notes)

- Headless check via `urllib`: `GET /api/ping` now returns `{"status":
  "ok", "widgets": []}` — confirms the server correctly no longer knows
  about `demo` (it's `python`-kind), a meaningful behavior change from
  every prior TODO item.
- Launched the real app and confirmed via `ps` that **no**
  `QtWebEngineProcess` starts at all now (there are currently no
  `html`-kind widgets), unlike every prior TODO item's verification.
- **Found and fixed a real bug during verification**: loading `widget.py`
  via `importlib` wrote a `__pycache__/*.pyc` into the widget's own
  directory, which `WidgetWatcher` (watching that directory recursively)
  picked up as a spurious source change, firing an unwanted rebuild right
  at startup. Fixed by toggling `sys.dont_write_bytecode` around the
  `exec_module` call in `_load_widget_module`. Re-verified clean: no
  `__pycache__` appears anywhere under `widgets/` after loading, and no
  spurious "Rebuilding widget demo" log line at startup.
- With the fix in place, edited `widgets/demo/widget.py`'s label text
  while the app was running (no rebuild step, since it's plain Python) —
  confirmed via the `desk.shell.python_widget: Rebuilding widget demo` log
  line that the watcher still correctly fires exactly once for a real
  edit, and (implicitly, since `_rebuild()` re-imports fresh) that the
  new text would be shown.
- Quit via a `quit` Apple Event; confirmed via `ps` that the process
  exited and via `curl` that the server's port stopped accepting
  connections.
- Visual confirmation of the rendered native widget was **skipped**, per
  the same environment screenshot limitation noted in earlier plans.

## Key design decisions / tradeoffs

See `design-docs/architecture.md`'s Key Design Decisions for the full
rationale; in short:

- Native `QWidget` construction directly by the Shell removes an HTTP
  round-trip and a full browser engine for something Qt already renders
  for free — the right default now that "no local server in between" is
  an explicit requirement.
- Hot reload for `python` widgets is "rebuild from scratch," not a
  fine-grained patch — simplest correct thing, consistent with the
  previous "always re-execute fresh" approach, at the cost of not
  preserving widget-internal state across a reload (noted as Future Work).
- `discover_widgets`/`WidgetWatcher` move to a shared top-level module
  (`desk.widgets`) because they're now used by both the Shell (for
  `python` widgets, with no server involved) and the server (for `html`
  widgets) — keeping them under `desk.server` would wrongly suggest they're
  server-specific.
