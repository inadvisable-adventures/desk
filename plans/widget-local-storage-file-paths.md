# Wire Markdown/Markdown (Old, Basic)/Editor widgets onto widget-local storage (COMPLETED)

TODO `02eda20`.

## Summary

TODO `fb76057` built the general "widget-local storage" mechanism
(`WidgetState.state: dict`, duck-typed `get_widget_local_storage()`/
`set_widget_local_storage()`, generic binding in `DeskWindow`) but
deliberately didn't wire any real widget onto it. Only the Stack
widget (`widgets/stack/widget.py`) uses it today. `PARKINGLOT.md`
names three widgets left unwired for their own "remember the chosen
file across a reload" case: Markdown (`widgets/markdown/`), Markdown
(Old, Basic) (`widgets/markdown_old_basic/`), and Editor
(`widgets/editor/`) -- all three currently save/restore an empty
`{}` for their `"state"` field, confirmed directly by inspecting a
real `.desk` file's saved widget state. This is a separate, unrelated
issue from the desk-picker segfault fixed under TODO `8c9436b` -- the
crash there was entirely inside Qt/C++ event dispatch and never
reached Python-level path-handling code at all.

## Fix

**New shared helper**: `src/desk/persisted_path.py`, a single function
`resolve_persisted_path(raw: str | None) -> Path | None`:

```python
def resolve_persisted_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    return path
```

This is the "recover gracefully from a path that no longer exists at
load time" mechanism -- a moved/deleted file just leaves the widget in
its normal empty/placeholder state (each widget already has one, for
"no file open yet") instead of crashing or silently misbehaving (e.g.
watching a nonexistent path, or showing a stale error string baked
into the restored view). Lives in a small top-level `desk` module
(alongside `desk.file_watch`, `desk.stack_file`) since all three
widget packages already import sibling top-level `desk.*` modules
directly (`desk.file_watch`, `desk.shell`) -- widget packages can't
import each other, but they can all import the same shared `desk.*`
module.

**Each of the three widgets gets a matching pair of methods**,
following the Stack widget's existing shape exactly:

- `widgets/markdown_old_basic/widget.py` (`MarkdownWidget`):
  ```python
  def get_widget_local_storage(self) -> dict:
      return {"path": str(self._current_path)} if self._current_path else {}

  def set_widget_local_storage(self, data: dict) -> None:
      path = resolve_persisted_path(data.get("path"))
      if path is not None:
          self.set_file(path)
  ```
- `widgets/editor/widget.py` (`EditorWidget`): identical shape, using
  its own `_current_path`/`set_file`.
- `widgets/markdown/widget.py` (`MarkdownWidget`, the TOC/Mermaid one):
  identical shape, but only ever persists a real file path -- when
  tempui-bound (`set_tempui_content`), `_current_path` is already
  `None` (set explicitly in that method), so `get_widget_local_storage`
  naturally contributes `{}` for a tempui-bound instance without any
  extra check. (Tempui-bound widgets are re-bound fresh from the
  tempui file itself on every reload via the existing
  `_bind_temp_ui_content` path in `window.py`, not through saved
  widget-local storage at all -- persisting a stale path here would be
  actively wrong, not just redundant.)

No changes needed in `src/desk/shell/window.py` -- `_bind_widget_local_
storage`/`_get_widget_local_storage` are already fully generic
(duck-typed via `hasattr`), which is the whole point of TODO
`fb76057`'s design.

## Affected files

- `src/desk/persisted_path.py` (new) -- `resolve_persisted_path`.
- `widgets/markdown_old_basic/widget.py` -- new methods + import.
- `widgets/markdown/widget.py` -- new methods + import.
- `widgets/editor/widget.py` -- new methods + import.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
`importlib.util.spec_from_file_location` for each widget module, no
`DeskWindow` construction needed since these methods are tested
directly on the widget instance):

- `resolve_persisted_path`: `None`/`""` input -> `None`; a path that
  doesn't exist -> `None`; a path to a real file -> that `Path`.
- Each widget: open a real temp file via `set_file`, confirm
  `get_widget_local_storage()` returns `{"path": "<that path>"}`;
  construct a fresh instance, call `set_widget_local_storage` with
  that dict, confirm the file loads (label/current path updated); call
  `set_widget_local_storage({"path": "<a path that doesn't exist>"})`
  on a fresh instance, confirm it does NOT crash and stays in its
  normal placeholder/empty state rather than adopting the bogus path.
- Markdown (TOC/Mermaid) widget specifically: after
  `set_tempui_content(...)`, confirm `get_widget_local_storage()`
  returns `{}` (not a stale/`None` path), matching the "don't persist
  tempui-bound state" design decision above.

## Status

Implemented exactly as planned: `src/desk/persisted_path.py` (new,
`resolve_persisted_path`); matching `get_widget_local_storage`/
`set_widget_local_storage` pairs added to `widgets/markdown_old_basic/
widget.py`, `widgets/editor/widget.py`, and `widgets/markdown/
widget.py` (the last one's `get_widget_local_storage` relies on
`_current_path` already being `None` whenever tempui-bound, so a
tempui-bound instance naturally contributes `{}`). No `window.py`
changes needed, confirming TODO fb76057's generic duck-typed design
worked as intended for a second, independent set of widgets.

Also updated `design-docs/architecture.md`'s widget-local-storage
paragraph to name which widgets actually use the mechanism now, and
`PARKINGLOT.md`'s entry to mark this half of the parked idea resolved
(the other half — migrating the TempUI/Claude bespoke bindings onto
this same mechanism — remains parked, undecided).

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
`importlib.util.spec_from_file_location` per widget module to avoid
`widget.py`-name collisions across the three widget packages):
`resolve_persisted_path` on `None`/empty/missing/real paths; each
widget's own file-open → `get_widget_local_storage()` →
fresh-instance `set_widget_local_storage()` round-trip; each widget's
`set_widget_local_storage` on a bogus/deleted path leaves a fresh
instance in its normal untouched placeholder state (`_current_path is
None`) rather than crashing or adopting the bogus path; the Markdown
widget's tempui-bound state contributes `{}`. Re-ran the full
scratchpad regression suite from this session — three pre-existing,
unrelated failures found (a crash-log-directory test, a `switch_desk`
fake test double missing a `provisioning` kwarg added by later work,
and a stale reference to the since-renamed `markdown_ex` directory),
none touching `persisted_path` or the three widgets touched here;
left as-is since fixing stale scratchpad scripts from earlier in the
session is out of scope for this TODO.
