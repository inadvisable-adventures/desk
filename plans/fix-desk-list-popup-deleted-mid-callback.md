# Fix crash: Desk picker's list popup deleted mid-callback on Desk switch (TODO c8f6fb3) (COMPLETED)

## Summary

TODO c8f6fb3: picking a Desk from the Desk picker's name popup
(`_DeskListPopup`, added by TODO 8beab6e) can crash the whole app:

```
RuntimeError: wrapped C/C++ object of type _DeskListPopup has been deleted
```

raised from `_DeskListPopup._activate_item`'s `self.close()` call.

## Root cause

`_activate_item` currently does, in this order:

```python
def _activate_item(self, item: QListWidgetItem) -> None:
    path = item.data(PATH_ROLE)
    if path is None:
        self.browse_requested.emit()
    else:
        self.desk_chosen.emit(path)
    self.close()
```

`desk_chosen`/`browse_requested` are connected straight through to
`DeskPicker`'s own signals of the same name (`_on_name_clicked`), which
`DeskWindow` connects to `_on_desk_chosen`/`_on_browse_requested` →
`switch_desk()`. `switch_desk()` ends by calling `_provision_temp_ui()`,
which can synchronously show a real modal confirmation dialog
(`QMessageBox.question`, via `_confirm_fn`) if the newly-switched
-to directory hasn't been provisioned for Temporary UI yet (TODO
a02b001).

`_DeskListPopup` is a `Qt.WindowType.Popup` window with
`WA_DeleteOnClose`. A `Qt::Popup` window auto-closes as soon as it loses
active-window status — the exact mechanism that makes "click away to
dismiss" work — and a new modal dialog appearing *does* take active
-window status away from it. Since `WA_DeleteOnClose` schedules a
`deleteLater()` on close, and `QMessageBox.question()`'s own nested
`exec()` event loop processes pending deferred-delete events, the popup's
underlying C++ object is destroyed *while `_activate_item` is still on
the call stack of that same object's own slot* — so by the time control
returns from `self.desk_chosen.emit(path)` and execution reaches
`self.close()`, `self` no longer has a live C++ object behind it.

Confirmed directly with a minimal, unrelated-to-Desk-switching repro: a
real `_DeskListPopup`, a slot connected to `desk_chosen` that opens a
plain `QDialog().exec()` (auto-accepted via a timer so the repro
terminates), and then calling `self.close()` after the emit reproduces
the exact same `RuntimeError`. This confirms the hazard is general (any
downstream slot that shows a modal dialog while the popup is still open,
not specifically `_provision_temp_ui`'s dialog).

## Affected files

- `src/desk/shell/desk_picker.py` (edit) — `_DeskListPopup._activate_item`.

## Design

Close the popup *before* emitting the signal, and never touch `self`
afterward:

```python
def _activate_item(self, item: QListWidgetItem) -> None:
    path = item.data(PATH_ROLE)
    self.close()
    if path is None:
        self.browse_requested.emit()
    else:
        self.desk_chosen.emit(path)
```

Confirmed directly (same minimal repro as above, reordered) that this is
safe: whether the popup's underlying object ends up destroyed
synchronously (via a nested event loop inside a downstream slot) or only
later (the normal case, once `deleteLater()` is naturally processed),
nothing after the emit calls a method on `self`, so there's nothing left
that can raise once the object's already gone.

Not touching `DeskPicker._on_name_clicked` or the emit/connect wiring —
the bug is entirely local to the popup's own use-after-close-triggered
-deletion ordering.

### Related, deferred: `WidgetSpawnMenu._activate_item` has the same shape

`src/desk/shell/widget_spawn_menu.py`'s `_activate_item` emits
`widget_chosen` and *then* calls `self.close()` — the identical ordering
this fix removes, on the identical `Qt.WindowType.Popup` +
`WA_DeleteOnClose` pattern. It doesn't currently crash because nothing
downstream of `widget_chosen` happens to show a modal dialog today, but
that's circumstantial, not structural. Not fixed here (out of scope for
this specific crash report) — noted in `PARKINGLOT.md` instead, per
`development-process.md`'s workflow for a thought that surfaces while
working on something else.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`):

1. Reproduce the exact crash directly against the unfixed ordering: a
   real `_DeskListPopup`, a `desk_chosen` slot that shows a real modal
   `QDialog` (auto-dismissed via a timer so the repro terminates), then
   activating an item — confirm the `RuntimeError` is raised.
2. Confirm the fix: identical repro against the reordered code — no
   exception, the popup closes correctly either way.
3. Regression: the normal (no nested modal dialog) activation path still
   emits the right signal with the right argument and still closes the
   popup.
4. Full-app regression: construct a real `DeskWindow`, open the picker's
   name popup, and pick an MRU entry pointing at a directory that hasn't
   been Temporary-UI-provisioned yet (forcing `_provision_temp_ui`'s real
   confirmation dialog to appear) — confirm `switch_desk` completes and
   the app doesn't crash.

## Status

Implemented and verified headlessly:

1. Reproduced the exact crash directly against the unfixed ordering: a
   real `_DeskListPopup`, a `desk_chosen` slot showing a real modal
   `QDialog` (auto-accepted via a timer), then activating an item —
   confirmed `RuntimeError: wrapped C/C++ object of type _DeskListPopup
   has been deleted`.
2. Confirmed the fix: identical repro against the reordered code — no
   exception; the emitted path/value is still received correctly.
3. Regression: the normal (no nested modal) MRU-entry and browse-entry
   activation paths still emit the right signal/argument.
4. Full-app: constructed a real `DeskWindow` (catalog trimmed to the
   `todo` widget to avoid this sandbox's unrelated QtWebEngine GPU hang),
   monkeypatched `QMessageBox.question` to open a real (auto-accepted)
   modal `QDialog` in its place — preserving the actual mechanism under
   test (a modal stealing active-window status from the still-open
   popup) without needing to click a real dialog button — opened the
   name popup, and picked an MRU entry pointing at a directory not yet
   provisioned for Temporary UI (forcing `_provision_temp_ui`'s
   confirmation path). `switch_desk` completed and `window.current_desk
   .path` correctly reflected the new Desk, with no crash.
