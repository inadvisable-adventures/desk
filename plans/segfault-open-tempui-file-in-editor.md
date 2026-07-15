# Segfault opening a tempui file from Project Files into the Editor widget (COMPLETED)

TODO `810a5d6`.

## Summary

Reported: opening `./necro-4x/necro-4x.desk` segfaulted. The last action
taken in that Desk beforehand was double-clicking `./necro-4x/.desk_temp
/desk-temporary-ui.md` in the Project Files widget -- which opens it in a
**new Editor widget instance** (`FileExplorerWidget._open_index`
hardcodes `opener("editor")` regardless of file extension/kind -- it
never routes to Markdown/MarkdownEx even for a `.md` file). A traceback
was captured at the time, cut off before the actual exception type/
message:

```
Traceback (most recent call last):
  File "./desk/widgets/project_files/widget.py", line 246, in _open_index
    widget.set_file(path)
    ~~~~~~~~~~~~~~~^^^^^^
  File "./desk/widgets/editor/widget.py", line 181, in set_file
    self._load_file(path)
    ~~~~~~~~~~~~~~~^^^^^^
  File "./desk/widgets/editor/widget.py", line 146, in _load_file
    self.refresh_external_path_status()
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
  File "./desk/widgets/editor/widget.py", line 155, in refresh_external_path_status
    is_external = self._current_path is not None and current_context.path_is_external(
```

`refresh_external_path_status`/`path_is_external` are brand new (TODO
a053e3a, implemented immediately before this was reported) -- the timing
and the trace both point at that feature as the likely trigger, even
though the exact exception is unknown.

## Investigation

- **Why a plain Python exception can present as "a segmentation
  fault"**: this codebase already has a confirmed, documented precedent
  for exactly this failure shape. `PythonWidgetHost._rebuild`'s own
  docstring/`plans/isolate-hot-reload-crash.md`: "an uncaught exception
  [escaping a Qt slot] is fatal to the whole process in this PyQt6
  setup -- confirmed via a real crash, not theoretical." `_open_index`
  is connected to `QTreeView.doubleClicked`, a Qt signal dispatched from
  C++ -- so any uncaught Python exception anywhere in the call chain it
  triggers (`_open_index` -> `set_file` -> `_load_file` ->
  `refresh_external_path_status` -> `path_is_external`) is exactly this
  same class of bug, at a *different* call site than the one already
  fixed. This alone is sufficient to explain a hard crash, independent
  of whatever the specific exception turns out to be.
- **This is *not* the same shape as the other known segfault in this
  codebase** (`PARKINGLOT.md`'s Desk Picker crash, TODO b44e8ba): that
  one is "a true segfault with **no** Python traceback at all" (no
  faulthandler is installed anywhere in this app -- confirmed, `grep`
  turns up nothing). A real, signal-level segfault with nothing
  installed to catch it would print *nothing* Python-shaped. Getting a
  real (if truncated) Python traceback here means a Python exception
  genuinely was raised and printed (almost certainly via PyQt6's default
  exception hook) before the process went down -- reinforcing the
  "uncaught exception escaping a Qt slot" theory over "an unrelated
  native crash that happened to interrupt at this exact line."
- **Direct repro attempted, did not reproduce**: built a real
  `EditorWidget` headlessly, set a real current-Desk directory, and
  called `set_file()` on a `.desk_temp/desk-temporary-ui.md`-shaped path
  inside it -- no exception. Read through `path_is_external`,
  `refresh_external_path_status`, and `_load_file` line by line for
  anything that could raise uncaught given a well-formed `Path` and
  `Path` current-Desk-directory (both of which are true in the normal
  code path -- `Desk.directory` is a typed `@property` returning
  `self.path.parent`, never a bare string). No concrete bug was
  isolated with certainty; plausible but unconfirmed candidates: a
  symlink loop under `.desk_temp` (`Path.resolve()` raises
  `RuntimeError` for that, which is **not** caught by
  `path_is_external`'s `except (ValueError, OSError)`), or some other
  filesystem edge case specific to the real machine/directory that
  doesn't reproduce in a fresh temp directory.
- **Given the trace is cut off before the exception type/message**,
  the *exact* originating bug can't be pinned down with full certainty
  from this report alone. Rather than block on that, this plan hardens
  the whole call chain against *any* exception at each of these
  boundaries -- which fixes the reported crash regardless of the
  precise cause, closes the same category of gap TODO 810a5d6 was
  opened for, and is the right shape of fix even if the true root cause
  turns out to be something not listed above.

## Fix

- **`EditorWidget._load_file`**: wrap the file read in `try`/`except
  (FileNotFoundError, OSError)`, matching the Markdown/Markdown
  (Extended)/SVG Viewer widgets' own existing pattern (show a friendly
  on-screen message instead of raising) -- currently the *only* one of
  the four single-file widgets whose load path has no error handling at
  all. Unrelated to the specific traceback (which got past the read),
  but a real, adjacent gap in the exact code path being hardened here.
- **`refresh_external_path_status()` in all 5 widgets** (Markdown,
  Markdown (Extended), SVG Viewer, Editor, TODO -- TODO a053e3a): wrap
  the body in `try`/`except Exception`, logging via a new
  module-level `logging.getLogger(__name__)` (matching
  `desk.shell.python_widget`'s existing style) and falling back to not
  emitting a change on failure. This is a purely cosmetic titlebar
  feature; it must never be capable of crashing anything, regardless of
  what future caller ends up invoking it or what edge case a real
  filesystem throws at `path_is_external`.
- **`FileExplorerWidget._open_index`**: wrap `widget.set_file(path)` in
  `try`/`except Exception`, logging the same way, mirroring
  `PythonWidgetHost._rebuild`'s established precedent exactly. This is
  the actual UI action that triggered the crash, and it hands off to an
  arbitrary widget's `set_file` (today's four, or any future widget kind
  that adopts the same convention) -- that boundary should never be
  able to take down the whole app, independent of the specific bug
  living inside whichever `set_file` it happens to call today.
- **Not doing**: adding a general "no Qt slot may ever crash" wrapper
  mechanism (a decorator, a global excepthook, etc.) -- that's the
  separately-tracked, not-yet-implemented TODO 95f7ce9 (global crash
  -log handler), deliberately scoped apart from this targeted fix.

## Affected files

- `widgets/editor/widget.py` -- `_load_file`'s read wrapped in
  `try`/`except`; `refresh_external_path_status` hardened; new
  module-level logger.
- `widgets/markdown/widget.py`, `widgets/markdown_ex/widget.py`,
  `widgets/svg_viewer/widget.py`, `widgets/todo/widget.py` --
  `refresh_external_path_status`/`reload`'s status call hardened; new
  module-level logger in each.
- `widgets/project_files/widget.py` -- `_open_index`'s `set_file` call
  wrapped; new module-level logger.
- `LEARNINGS.md` -- an entry recording this as a second, distinct
  instance of the "uncaught exception escaping a Qt slot is fatal"
  class first documented in `plans/isolate-hot-reload-crash.md`, since
  it's exactly the kind of non-obvious, likely-to-recur mistake that
  file exists for.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- Each widget's `refresh_external_path_status`, with
  `current_context.path_is_external` monkeypatched to raise: confirm no
  exception escapes, a log line is emitted, and the widget keeps
  functioning afterward (its `changed`/other signals still fire
  normally on the next real load).
- `FileExplorerWidget._open_index`, with the opened widget's `set_file`
  monkeypatched to raise: confirm no exception escapes `_open_index`
  and the Project Files widget itself stays fully usable afterward
  (can still browse/search/open a different, working file).
- `EditorWidget._load_file` against a real unreadable/missing path:
  confirms a friendly message is shown instead of raising, matching the
  Markdown widget's own equivalent behavior.
- Full regression pass of TODO a053e3a's own existing verification
  (dedup/fan-out unaffected; each widget still correctly reports
  external/internal status for real, well-formed paths) -- confirming
  none of this hardening changed the feature's actual behavior in the
  non-error case.

## Status

Implemented as planned. `EditorWidget._load_file` now reads the file
before touching any widget state and shows a `QMessageBox` warning
(rather than writing an error message into the editable buffer itself,
which risked the user then hitting Save and overwriting a real file
with that message) on `OSError`; each of the 5 widgets'
`refresh_external_path_status` and `FileExplorerWidget._open_index`'s
`widget.set_file(path)` call are now wrapped in `try`/`except
Exception`, logging via a new per-file `logging.getLogger(__name__)`
matching `desk.shell.python_widget`'s existing style.

All headless verification steps above passed: each widget's
`refresh_external_path_status` survives `path_is_external` monkeypatched
to raise (logs, doesn't emit, widget stays otherwise functional);
`_open_index` survives a `set_file` monkeypatched to raise (logs, File
Explorer widget stays fully usable -- confirmed by exercising its search
afterward); `EditorWidget._load_file` against a real nonexistent path
shows a warning dialog and leaves the existing buffer/`_current_path`
completely untouched; a full regression pass of TODO a053e3a's own
verification confirms none of this hardening changed the real,
non-error-case behavior.

Added a `LEARNINGS.md` entry (see its own new section) recording this
as a second, independent instance of the "uncaught exception escaping a
Qt slot is fatal" class first documented for hot-reload -- the general
lesson being that this is a per-slot hazard needing re-application at
every `*.connect(...)` site individually, not something fixed once for
the whole app (that broader backstop is the separate, not-yet
-implemented TODO 95f7ce9).

The exact original exception that caused the reported crash was never
conclusively identified, since the pasted traceback was cut off before
the exception type/message -- the fix addresses the whole class of bug
regardless, per the plan's own reasoning above.
