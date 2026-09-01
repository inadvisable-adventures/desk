# Bug: widget popups render as detached macOS windows (TODO `5242aeb`) (COMPLETED)

## Summary

A widget-triggered alert/confirmation dialog built from a raw native
`QMessageBox` (parented to a widget's own content, which lives inside a
`QGraphicsProxyWidget` on the canvas, not as a real top-level window)
renders as a genuine, detached macOS window whose position Qt computes
from `mapToGlobal` -- a computation that doesn't account for the
canvas's own zoom/pan transform. The user hit this in the new State
Manager widget's (TODO `6330249`) "Load State" confirmation and its
"New Key" validation alerts, all of which used `QMessageBox` directly
instead of the already-existing desk-internal popups service
(`desk_services.popups`, TODO `359684f`) -- reintroducing a bug that
service was specifically built to eliminate. `widgets/markdown/widget.py`'s
own "Save As" error alert had the same, apparently pre-existing,
never-migrated bug.

**The fix mechanism already exists and needs no new code**:
`current_context.get_popup_opener()` for `kind: "python"` widgets and
`desk.popups.show(...)` (Bridge API) for `kind: "html"` widgets both
call the exact same `PopupsService.show_blocking`/`.show` -- confirmed
directly (`DeskWindow.show_popup` and `current_context
.set_popup_opener(self._popups_service.show_blocking)` both close over
the same `self._popups_service` instance). This item is: (1) fix the
two widgets that bypassed it, (2) make sure this doesn't happen again
-- stronger, more prominent guidance in the docs an agent actually
reads before writing a widget, plus a real, automated regression guard
rather than relying on anyone remembering to check.

## Affected files

- `widgets/state_manager/widget.py` -- replace all `QMessageBox` calls
  with the popups service.
- `widgets/markdown/widget.py` -- same, for its one remaining call.
- `design-docs/architecture.md` -- a explicit callout in the Widget
  Model's `kind: "python"` description.
- `src/desk/temp_ui.py` -- strengthens the existing `desk.popups.show`
  doc bullet with an explicit "don't use a raw browser
  alert()/confirm()/prompt() instead" callout; version bump.
- `tests/verify/` -- new coverage, including a durable, automated
  regression guard.

## Design decisions

- **No new mechanism** -- `desk_services.popups.PopupsService` already
  is "a Desk-specific way to surface alerts and confirmations from
  python or via the Desk API for html," already using the same
  codepath for both. Building a second one would just be a second
  thing to forget to use.
- **`QMessageBox`/`QDialog` remain fine for `DeskWindow` itself**
  (`_confirm_fn`/`_warn`/`_info`/`_confirm_stale_reload`/etc.) -- those
  are parented to the real, genuine top-level `QMainWindow`, not to
  content embedded in a `QGraphicsProxyWidget` on the canvas, so they
  were never subject to this bug. Nothing there changes.
- **`QFileDialog`/`QInputDialog` are out of scope** -- the report is
  specifically about alerts/confirmations; a native file-picker (Save
  State/Load State's own file choosers, already in `state_manager`) is
  conventionally a separate OS-level dialog everywhere, including in
  apps with no canvas-embedding concern at all, and isn't the bug being
  reported.
- **Guidance goes where an agent actually looks**: `design-docs
  /architecture.md`'s Widget Model section is the closest thing this
  codebase has to "how a widget is built," read before `design-docs
  /widget-ux.md`'s own deep-dive (which already documents this bug and
  fix in full, TODO `359684f`, but is UX-implementation-detail
  documentation, not a first read for "how do I write a widget").
  `temp_ui.py`'s existing `desk.popups.show` bullet is already
  reasonably clear for `kind: "html"` (it already says "not a real OS
  window") but doesn't explicitly warn against the raw browser
  alternative.
- **A real, automated regression guard, not just docs** -- a small
  verify script that scans every `widgets/*/widget.py` for a live
  `QMessageBox.(question|warning|information|critical)(` call is cheap,
  durable, and doesn't depend on an agent having read the guidance at
  all. Docs are still worth improving (an agent who reads them first
  never introduces the bug in the first place), but the guard is what
  actually prevents a silent regression going forward.

## Step-by-step implementation

1. `widgets/state_manager/widget.py`: two new small helpers, `_alert(title,
   message)` and `_confirm(title, message) -> bool`, both routing through
   `current_context.get_popup_opener()`; every existing `QMessageBox`
   call site (4 `.warning`, 1 `.question`) replaced with one of the two;
   drop the now-unused `QMessageBox` import.
2. `widgets/markdown/widget.py`: `_save_as`'s one `QMessageBox.warning`
   replaced the same way (inline, only one call site, no helper
   needed); drop the now-unused `QMessageBox` import.
3. `design-docs/architecture.md`: a short paragraph in the `kind:
   "python"` bullet of the Widget Model section -- alerts/confirmations
   must go through `current_context.get_popup_opener()`, never a raw
   `QMessageBox`/`QDialog` parented to the widget's own content, with a
   one-sentence why and a pointer to `design-docs/widget-ux.md`'s
   "Desk-Internal Popups" section for the full story.
4. `temp_ui.py`: extends the existing `desk.popups.show` bullet with an
   explicit "don't use a raw browser `alert()`/`confirm()`/`prompt()`"
   callout; `TEMPUI_DOC_VERSION` bump with a matching comment block and
   `_NEW_FEATURES_DOC`-adjacent note (this is a doc-wording strengthening,
   not a new call -- covered by a changelog line regardless, matching
   this project's own "bump whenever DOC_TEMPLATE's static content
   changes in a way that would matter to an agent reading it" rule).
5. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- The automated regression guard only scans `widgets/*/widget.py` --
  it wouldn't catch a `kind: "html"` widget's own raw JS
  `alert()`/`confirm()`, which isn't mechanically scannable the same
  way from Python. Documentation is the only guard for that side.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_state_manager_widget_ui.py` (extended): the
  "New Key" dialog's empty-key-name and invalid-JSON validation
  failures call the fake `current_context` popup opener (not a real
  `QMessageBox`, which would hang/misbehave headless if the fix
  regressed) with the expected title/message; "Load State" without
  confirming (`popup_opener` returning `"No"`/`None`) does not call the
  importer at all; confirming (`"Yes"`) does.
- `tests/verify/verify_widgets_use_popup_service.py` (new): scans every
  real `widgets/*/widget.py` file's source text for a live
  `QMessageBox\.(question|warning|information|critical)\s*\(` call
  (a plain regex, not an AST-aware check -- deliberately simple and
  fast) and fails if any is found outside of a comment -- a real,
  automated regression guard, not just a one-time fix.
- Full `tests/verify/` regression suite (123 scripts as of TODO
  `297f1a6`, plus this item's new/extended scripts).
