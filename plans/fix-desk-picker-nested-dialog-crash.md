# Fix Desk-picker nested-dialog segfault (generalizing the New Desk flow fix)

TODO `8c9436b`. Very likely also resolves `b44e8ba` (same crash shape,
that report never had a crash log to confirm against until now).

## Summary

Reported crash: loading an already-existing `.desk` file from the
picker segfaulted. The full crash report (kept out of the repo per
explicit instruction) shows the *identical* crashing-thread shape as
the already-fixed New-Desk-flow segfault (TODO `4716585`):
`QAbstractItemView::mouseReleaseEvent` -> `QListView
::mouseReleaseEvent` -> `sipQListWidget::mouseReleaseEvent`, reached
via the normal Cocoa mouse-event-delivery path. This time the faulting
address is small (`0x2f9`/`0x761`), consistent with a null/near-null
pointer dereference rather than "reused memory garbage bytes" -- but
the crashing call chain (a `QListWidget`'s own event handling) is the
same, and the trigger ("choose an entry from the Desk picker") is
`_DeskListPopup`'s own domain.

## Diagnosis

`_DeskListPopup` (`src/desk/shell/desk_picker.py`) is a `QListWidget`
-based, `WA_DeleteOnClose`, `Qt.WindowType.Popup`. Its own
`_activate_item` already has a **documented, prior partial fix**
(its own comment, referencing `plans/fix-desk-list-popup-deleted-mid
-callback.md`) for a *related* crash: `close()` is called *before*
emitting, specifically because "a downstream slot... may show a modal
dialog before returning. That modal stealing active-window status
auto-closes this still-open... Popup, and `WA_DeleteOnClose`'s
`deleteLater()` gets processed by the modal's own nested event loop
while this method is still on the call stack." That fix addressed
calling `close()` on an already-deleted `self` -- it did **not**
address the underlying condition it describes: a downstream modal
dialog's own nested event loop is what processes this popup's deferred
deletion, *while the originating click's own event delivery may still
be unwinding*. If a stale, still-in-flight native mouse event
(press/release can legitimately be split across event-processing
boundaries) targets the popup's `QListWidget` at exactly that moment,
it's delivered to a widget whose C++ object is either fully freed or
mid-teardown -- matching this crash's shape exactly, and TODO
`4716585`'s own diagnosis of the New-Desk-flow crash.

TODO `4716585` fixed this for the *New Desk* sub-flow specifically, by
collapsing five sequential modal dialogs into one non-modal
`NewDeskDialog.show()`. It did not touch the *other* four `DeskPicker`
-originated flows -- `desk_chosen` (-> `switch_desk`'s own "Switch to
X?" confirm), `browse_requested` (-> a modal `QFileDialog`),
`rename_requested` (-> a modal `QInputDialog`), and
`directory_change_requested` (-> a modal `QFileDialog`, then a confirm)
-- every one of which still reaches a modal `.exec()` call
**synchronously, within the same call stack as the popup's own click
handling**, exactly the condition the popup's own code comment warns
about. "Load an already-existing Desk" is the `desk_chosen` path --
matching this report exactly.

## Fix

**Defer every `DeskPicker`-originated signal handler in `DeskWindow`**
via a new `_deferred(fn)` helper (`QTimer.singleShot(0, ...)`), so any
modal dialog it might show always runs on a *fresh* event-loop
iteration -- never nested inside the same call stack as the
originating click. This is the correct, general fix for the actual
mechanism (a modal dialog's nested event loop processing a
`WA_DeleteOnClose` popup's deferred deletion while a stale event for
it might still be in flight), not a New-Desk-specific one:

```python
self.view.desk_picker.desk_chosen.connect(self._deferred(self._on_desk_chosen))
self.view.desk_picker.browse_requested.connect(self._deferred(self._on_browse_requested))
self.view.desk_picker.new_desk_requested.connect(self._deferred(self._on_new_desk_requested))
self.view.desk_picker.rename_requested.connect(self._deferred(self._on_rename_requested))
self.view.desk_picker.directory_change_requested.connect(self._deferred(self._on_directory_change_requested))
```

All five, not just the four with an obviously-reachable modal dialog
today -- `_on_new_desk_requested` (now a non-modal `.show()`, safe on
its own) gets it too, defensively, so a future change to that handler
can't silently reintroduce this exact bug without anyone noticing.

**Also applied to `WidgetSpawnMenu`** (`widget_chosen`/
`paste_requested`, connected in `WorkspaceView.contextMenuEvent`) --
the *only other* `WA_DeleteOnClose`, `QAbstractItemView` (a
`QTreeWidget`)-based popup in the codebase, i.e. the only other one
with the exact vulnerable shape. Neither of its current handlers shows
a modal dialog today, so this is purely preventive, for the same
"don't let a future change silently reintroduce this" reason.

**Not applied everywhere `WA_DeleteOnClose` appears.** `NewDeskDialog`,
`_PickOverlay` (Feedback widget), `_ItemDialog` (TODO widget),
`_AnswerDialog` (Questions widget) are plain `QWidget`s with ordinary
buttons/text fields, not `QAbstractItemView` subclasses -- the
*specific* crashing code path (`QAbstractItemView::mouseReleaseEvent`)
doesn't apply to them, confirmed by the fact that this crash (and TODO
4716585's) both name that exact call chain. Broadly wrapping every
`WA_DeleteOnClose` widget's every signal "just in case" would be
speculative hardening without a confirmed mechanism behind it for
those cases -- the general lesson is recorded (see below) for if it
ever does turn out to matter elsewhere.

## Prevention mechanism (as requested)

- **`DeskWindow._deferred(fn)`**: a small, named, reusable helper --
  the go-to answer for "a `WA_DeleteOnClose` list/tree-view popup's
  signal handler needs to show a modal dialog." Any *future* popup of
  this shape should wrap its DeskWindow-side connections with it from
  the start, not rediscover the bug first.
- **`LEARNINGS.md` entry** (see below) documenting the actual
  mechanism precisely, cross-referencing both this fix and TODO
  4716585's, so a future "segfault in `QAbstractItemView
  ::mouseReleaseEvent`" report is immediately recognizable instead of
  re-diagnosed from scratch.
- **Not a path-existence issue** (the user's own "e.g." guess) --
  confirmed directly: the crash is entirely inside Qt/C++ event
  delivery, never reaches Python-level path-handling code at all.
  TODO `02eda20` (a separate, related fix -- see
  `plans/widget-local-storage-file-paths.md`) is where a real
  path-existence-at-restore-time mechanism was actually needed, for a
  different, independently-diagnosed reason.

## Affected files

- `src/desk/shell/canvas.py` -- new module-level `deferred(fn)`
  helper (lives here, not `window.py`, since `window.py` already
  imports from `canvas.py` and not the other way around -- putting it
  in `canvas.py` lets both modules use the one implementation without
  a circular import); `WidgetSpawnMenu` signal connections in
  `contextMenuEvent` wrapped with it.
- `src/desk/shell/window.py` -- imports `deferred` from
  `desk.shell.canvas`; `DeskPicker` signal connections in `__init__`
  wrapped with it.
- `LEARNINGS.md` -- new entry.
- `TODO.md` -- `b44e8ba` resolved alongside this (same crash shape,
  now with a confirmed mechanism and fix).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
`QTimer`): confirms `_deferred(fn)` does *not* call `fn` synchronously
(the wrapped call returns before `fn` runs), and that `fn` *does* run
once the event loop actually processes the next iteration
(`QTest.qWait`/`app.processEvents()` after the scheduled delay). Also
confirms all five `DeskPicker` signals and both `WidgetSpawnMenu`
signals reach their handlers correctly through the wrapper (not just
that the wrapper itself works in isolation) -- unbound-method-on-a
-fake-double pattern for the `DeskWindow`-dependent connections, since
constructing a real `DeskWindow` stalls headlessly.

Not independently reproduced (a stale-event/deferred-deletion race
isn't reliably reproducible on demand, same caveat as TODO 4716585) --
this is a structural fix matching the confirmed mechanism (identical
crashing call chain, identical widget class, a direct generalization
of an already-fixed instance of the same bug), not a confirmed-by-repro
fix.

## Status

Not yet implemented.
