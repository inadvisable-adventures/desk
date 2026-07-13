# Fix Desk-picker nested-dialog segfault (generalizing the New Desk flow fix) (COMPLETED)

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

**Defer at the source: where each `WA_DeleteOnClose` popup's own
signal gets re-emitted by its stable, long-lived container**, via a
new shared `deferred(fn)` helper (`QTimer.singleShot(0, ...)`) --
rather than at every downstream connection point that happens to show
a dialog today. This is both simpler (one wrap per popup, not one per
eventual receiver) and more robust (any *future* receiver of
`DeskPicker.desk_chosen`/etc. -- not just today's `DeskWindow`
handlers -- automatically inherits the protection, with nothing for
that future code to remember):

- `desk_picker.py`, `DeskPicker._on_name_clicked`: the four
  `popup.<signal>.connect(self.<signal>)` re-emission connections
  become `popup.<signal>.connect(deferred(self.<signal>.emit))` (or
  the `path`-carrying variant for `desk_chosen`).
- `canvas.py`, `WorkspaceView.contextMenuEvent`: `menu.widget_chosen`/
  `menu.paste_requested`'s re-emission lambdas get wrapped the same
  way.

Once `DeskPicker.desk_chosen`/etc. themselves only ever fire from
within an already-deferred call (a fresh event-loop iteration), every
downstream receiver -- `DeskWindow`'s handlers included -- is safe
without needing its own wrapping. `DeskWindow`'s existing
`self.view.desk_picker.<signal>.connect(self._on_...)` connections are
therefore **unchanged**.

**`deferred` lives in a new, tiny, dependency-free
`src/desk/shell/qt_utils.py`**, not in `canvas.py` or `window.py`
directly -- `desk_picker.py` and `canvas.py` both need it, and
`window.py` already imports from `canvas.py` (not the reverse), so
neither existing module can be the shared home without risking a
circular import as more callers show up.

**Also applied to `WidgetSpawnMenu`** (the *only other*
`WA_DeleteOnClose`, `QAbstractItemView` (`QTreeWidget`)-based popup in
the codebase -- the only other one with the exact vulnerable shape).
Neither of its current handlers shows a modal dialog today, so this is
purely preventive, for the same "don't let a future change silently
reintroduce this" reason.

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

- **`desk.shell.qt_utils.deferred(fn)`**: a small, named, reusable,
  importable-from-anywhere-in-`desk.shell` helper -- the go-to answer
  for "a `WA_DeleteOnClose` list/tree-view popup needs to re-emit a
  signal that might eventually reach a modal dialog." Any *future*
  popup of this shape should wrap its own outgoing re-emission with it
  from the start, not rediscover the bug first.
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

- `src/desk/shell/qt_utils.py` (new) -- `deferred(fn)`.
- `src/desk/shell/desk_picker.py` -- `DeskPicker._on_name_clicked`'s
  four popup-signal re-emission connections wrapped with `deferred`.
- `src/desk/shell/canvas.py` -- `WorkspaceView.contextMenuEvent`'s two
  `WidgetSpawnMenu`-signal re-emission connections wrapped with
  `deferred`.
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

Implemented as planned: new `src/desk/shell/qt_utils.py` (`deferred`);
`DeskPicker._on_name_clicked`'s four popup-signal re-emission
connections wrapped with it in `src/desk/shell/desk_picker.py`;
`WorkspaceView.contextMenuEvent`'s two `WidgetSpawnMenu`-signal
re-emission connections wrapped the same way in
`src/desk/shell/canvas.py`. `DeskWindow`'s own connection points are
unchanged, since the fix is applied at the source. Also updates
`design-docs/widget-ux.md`'s Desk Picker and Add Widget Menu sections,
and resolves `b44e8ba` (marked `COMPLETED` in `TODO.md`, answered in
`QUESTIONS.md` explaining the resolution without a direct repro).

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`):
`deferred(fn)` itself doesn't call `fn` synchronously and does call it
once the event loop processes the next iteration, with arguments
forwarded correctly. End-to-end: a real `DeskPicker` with a real
`_DeskListPopup` shown and an item activated confirms
`DeskPicker.desk_chosen` doesn't fire synchronously from the popup
click and does fire once deferred; a real `WorkspaceView.contextMenuEvent`
confirms `widget_add_requested` behaves the same way through
`WidgetSpawnMenu`. Regression-checked every other verification script
from this session.

No new `LEARNINGS.md` entry beyond the one already added for this
fix's own mechanism (see above) -- it directly extends, rather than
contradicts, the existing `_DeskListPopup` close-before-emit comment's
own documented reasoning.
