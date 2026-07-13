# Learnings

Unexpected corner cases, non-obvious library/API behavior, and mistakes worth not repeating, recorded for whoever (human or agent) works on this codebase next. See `development-process.md`'s Learnings section for what belongs here and the workflow for adding to it.

## `QWidget.graphicsProxyWidget()` does not bubble up from a child to its embedding proxy

If a `QWidget` is embedded in a `QGraphicsScene` via `scene.addWidget(widget)`, only that exact widget's `graphicsProxyWidget()` returns the real `QGraphicsProxyWidget` — a *child* of that widget's own `graphicsProxyWidget()` returns `None`, even though it's just as embedded. Confirmed directly: constructing a parent/child pair and embedding only the parent, `child.graphicsProxyWidget()` is `None` while `parent.graphicsProxyWidget()` is not.

To find the enclosing proxy from a descendant widget, use `self.window().graphicsProxyWidget()` instead — `QWidget.window()` correctly walks up to the top-level embedded ancestor.

## An embedded/scene-level mouse press must call `event.accept()` to keep receiving the rest of the drag

`QGraphicsScene` (and the `QGraphicsProxyWidget` embedding machinery) only continues delivering `mouseMoveEvent`/`mouseReleaseEvent` to whichever item accepted the initial `mousePressEvent`. If a widget's `mousePressEvent` handler does its bookkeeping but never calls `event.accept()` (e.g. delegates to the base `QWidget` implementation, which leaves it unaccepted), the widget receives exactly one press event and nothing else — no error, no exception, the interaction just silently does nothing beyond the initial click. If a click-and-drag interaction "does nothing," check this before suspecting the drag math itself.

## Mouse events delivered *into* a `QGraphicsProxyWidget`-embedded widget don't reliably reflect real screen coordinates once the view is zoomed

`event.globalPosition()`, `event.position()`, and `event.scenePosition()`, all read from the `QMouseEvent` that `QGraphicsProxyWidget` synthesizes when forwarding a scene-level event down into an embedded child widget, were each tried as the basis for computing on-screen drag deltas — all three gave different, scale-dependent wrong answers once the enclosing `QGraphicsView` was at a non-unity zoom level (confirmed on real trackpad hardware, then reproduced with synthetic `QMouseEvent`s routed through the view). Reliable only at scale = 1.0, which is why the bug went unnoticed until someone actually zoomed out.

Don't compute interaction deltas from an *embedded* child widget's own mouse events when the result needs to stay correct across zoom. Instead, handle mouse events on the top-level view itself — it isn't embedded in anything, so its own coordinates are the real ones — and hit-test which child widget (if any) the press landed on, driving the whole interaction from there. See `design-docs/widget-ux.md`'s Zoom-Correct Dragging section for the actual fix.

## `importlib`-loading a module writes `__pycache__` into its own source directory by default

`importlib.util.module_from_spec` + `exec_module` compiles and caches bytecode into a `__pycache__/` next to the source file, same as a normal `import` would. If something is recursively watching that same directory for source changes (a hot-reload watcher, say), the very first load of a widget's module creates a file inside the watched tree and immediately, spuriously triggers a "source changed" event — before anyone has actually edited anything.

Wrap the load in `sys.dont_write_bytecode = True` (save and restore the previous value around just that call) to suppress it.

## `QGraphicsView.centerOn()` is silently clamped by the scene's current bounding rect

Without an explicit `setSceneRect(...)`, a `QGraphicsView`'s effective scene rect is derived from wherever the currently-placed items happen to be. Asking to center on a point outside that rect doesn't error — it just lands somewhere else (as close as the implicit rect allows), silently. This broke restoring a saved pan position that wasn't near whatever widgets currently exist on the canvas.

If a view's pan position needs to be persisted/restored to an arbitrary point, give it a large, fixed `sceneRect()` up front rather than relying on the auto-computed one.

## `QSizeF`/`QPointF`-derived values are floats, but `QWidget.resize()` needs ints

`QGraphicsProxyWidget.size()`/`.pos()` return `QSizeF`/`QPointF` (floats). Round-tripping one of these through JSON and back, then passing it straight to `QWidget.resize(width, height)`, fails with a confusing "arguments did not match any overloaded call" `TypeError` rather than an obvious type error — `resize()` only accepts `int`. Round to `int` explicitly wherever a persisted/computed float size needs to become an actual widget resize.

## Constructing a `QNativeGestureEvent` with `dev=None` segfaults the process

When synthesizing a `QNativeGestureEvent` for testing (e.g. to simulate a trackpad pinch), passing `None` for the pointing-device argument crashes the whole Python process with a segfault — no exception, no traceback, just gone. Use a real device instead: `QPointingDevice.primaryPointingDevice()`. Real hardware always supplies a valid device, so this only matters for constructing test events by hand.

## Prefer `git commit -F <file>` over an inline heredoc for commit messages in this environment

`git commit -m "$(cat <<'EOF' ... EOF)"` intermittently fails in this shell with `unexpected EOF while looking for matching` even for messages that look correctly quoted. Writing the message to a scratch file and using `git commit -F path/to/file` avoids the issue entirely and has been reliable throughout this project's history.

## A `Qt.WindowType.Popup` widget can silently self-destruct during headless testing

A widget shown with the `Popup` window flag (used for `WidgetSpawnMenu`, matching how `QMenu` behaves) auto-closes when it isn't the real, active, window-manager-focused window — which it never is in this offscreen/headless test environment. Combined with `WA_DeleteOnClose`, calling `app.processEvents()` any time after `.show()` can tear down and delete the underlying C++ object out from under you, so a later access raises `RuntimeError: wrapped C/C++ object ... has been deleted` with no other warning.

When testing a `Popup`-flagged widget headlessly, don't call `.show()`/`processEvents()` and then poke at its children afterward — exercise its logic directly instead (call its methods, feed it synthetic `QEvent`s via `eventFilter`/`keyPressEvent`, emit its child widgets' signals directly) without an intervening event-loop turn. This isn't a bug in the widget; a real interactive popup behaves normally once it actually has focus.

## Connecting an object's own `destroyed` signal to one of its own bound methods never fires

`self.destroyed.connect(self._cleanup)` — a seemingly natural way to run cleanup when a widget is destroyed — silently never calls `_cleanup`. Confirmed directly with a minimal reproduction: the exact same pattern works when the slot belongs to a *different* object (`other.destroyed.connect(handler.cb)`) or is a plain lambda, but fails specifically when an object's `destroyed` signal is connected to a bound method of that *same* object. By the time `destroyed` is emitted, Qt apparently no longer considers the emitting object a valid signal-dispatch receiver for its own connections, even though nothing about the method call itself would be invalid.

To run cleanup on destruction, connect to a lambda (or plain function) that closes over plain local values captured *before* connecting — not `self` — and calls a module-level function or `@staticmethod` that never touches `self` or any of its Qt child objects:

```python
master_fd = self._master_fd          # capture plain values, not `self`
process = self._process
self.destroyed.connect(lambda: TerminalWidget._cleanup_resources(master_fd, process))
```

## `app.processEvents()` does not process `deleteLater()`-scheduled deletions

Calling `some_widget.deleteLater()` followed by `app.processEvents()` (even with `QEventLoop.ProcessEventsFlag.AllEvents`) does not actually destroy the object or fire its `destroyed` signal in a script-driven/headless context — `DeferredDelete` events aren't processed by a plain `processEvents()` call the way they are by a genuinely running `app.exec()` loop. Confirmed directly with a bare `QWidget`. This is specifically a *testing* gotcha, not a production one — `deleteLater()` works exactly as expected under a real, running event loop (which is what every actual Desk session uses), so this only bites when verifying `deleteLater()`-triggered cleanup headlessly.

To force it in a script/test: `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` before/around `processEvents()`.

## `subprocess.Popen(preexec_fn=...)` silently fails to spawn when called from a running PyQt app

Spawning a PTY-backed child process with `subprocess.Popen(..., preexec_fn=os.setsid)` worked perfectly in standalone headless test scripts, but inside the real, running Desk app the child process never actually appeared (no error, no exception, no traceback — just no child process, ever, confirmed by checking the process tree directly). Root cause: `preexec_fn` runs arbitrary Python code in the child between `fork()` and `exec()`, which Python's own `subprocess` documentation says is unsafe in a multi-threaded process — and a running PyQt/`QApplication` process is exactly that (Qt maintains its own internal threads). Only the forking thread's state survives into the child, so anything relying on state another thread held at fork time (locks, etc.) can silently misbehave.

Use `start_new_session=True` instead of `preexec_fn=os.setsid` to get the same "new session leader" PTY-spawning behavior — it achieves this through a safe path rather than arbitrary post-fork Python. If a subprocess spawn works in an isolated test script but the same child process never seems to materialize when run inside the actual Qt app, suspect `preexec_fn` first.

## `pyte` 0.8.2 crashes on most DEC-private CSI sequences, and `Stream.feed()` drops the rest of the chunk when it does

Confirmed via a real crash: running `claude` inside the console widget aborted the *entire app* with `TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'`. Root cause: `pyte.Stream` dispatches a DEC-private CSI sequence (`ESC[?...`) by calling the matching `Screen` method with an extra `private=True` keyword — but of the ~22 `Screen` methods CSI sequences can dispatch to, only `erase_in_line` actually declares a `private` parameter, and only four others (`erase_in_display`, `report_device_attributes`, `set_mode`, `reset_mode`) accept `**kwargs` to silently absorb it. Every other one — including `report_device_status`, `cursor_position`, `cursor_to_column`, `set_margins` — accepts neither, so *any* program sending one of those as a DEC-private variant crashes. This is confirmed to still be true in 0.8.2, the latest release on PyPI; there's no newer version to upgrade to.

Worse: `pyte.Stream.feed()` has no per-sequence error recovery — one bad dispatch call raises straight out of the whole `feed()` call, meaning every byte after the offending sequence *in that same chunk* (e.g. an entire subsequent `echo`'s output, if it happened to arrive in the same PTY read) never gets processed at all, not just the offending sequence. Wrapping the whole `feed()` call in a `try/except` "fixes" the crash but silently eats real output that was queued right after it.

The fix that actually preserves surrounding output: subclass `pyte.Stream` and override `feed()` with an exact copy of the upstream implementation, but wrap only the per-character dispatch call (`self._send_to_parser(...)`) in `try/except Exception`, keeping the surrounding character-walking loop intact. `_send_to_parser` already resets pyte's internal parser state on exception (by design — see its own docstring reference to PR #101), so recovering per-character and continuing the loop is safe and correct, not a hack layered against pyte's intent.

Separately, `pyte.Screen.write_process_input()` (used to reply to cursor-position/terminal-status queries) is a no-op by default — even once the crash is fixed, such queries get no real reply unless a `Screen` subclass overrides `write_process_input` to actually `os.write()` back to the PTY's master fd.

## `WidgetWatcher` never fires when pointed at a `tempfile.mkdtemp()` path on macOS

A headless test for catalog-level hot reload (creating/editing/deleting real widget directories under a temp path and waiting for `WidgetWatcher`'s debounced `broker.widget_changed` signal) never fired at all — not even for the simplest case, editing an existing watched file. Root cause: `tempfile.mkdtemp()` returns a path under `/var/folders/...`, which on macOS is a symlink to `/private/var/folders/...`. The watcher's FSEvents-backed observer reports the *resolved* `/private/var/...` path in its events, but `_DebouncedHandler.on_any_event` computes the changed widget's id via `Path(event.src_path).relative_to(self.widgets_dir)` against the *original, unresolved* path passed to `WidgetWatcher` — `relative_to` raises `ValueError` for the mismatch, which the handler already catches and silently returns from, so the failure produces no error at all, just silence.

This only affects test code that hands `WidgetWatcher` a raw `tempfile.mkdtemp()` result — the real app is unaffected, since `desk.server.app.DEFAULT_WIDGETS_DIR` is already built with `.resolve()`. When writing a headless test that watches a temp directory for file-system changes, always `.resolve()` the temp path first (`Path(tempfile.mkdtemp()).resolve()`), or the watcher will silently never fire.

## `QWebEngineView`/`QtWebEngine` needs real `sys.argv` and an import-order-correct `QApplication`

Two separate but easy-to-conflate failures when constructing a `QWebEngineView` (confirmed directly, testing the Desk Bridge API's browser-side injection):

1. `ImportError: QtWebEngineWidgets must be imported or Qt.AA_ShareOpenGLContexts must be set before a QCoreApplication instance is created` — if any module that imports `PyQt6.QtWebEngineWidgets`/`QtWebEngineCore` (directly or transitively, e.g. `desk.shell.window` → `desk.shell.chromium_widget`) is imported *after* `QApplication(...)` already exists. Fix: import anything touching `QtWebEngine*` before constructing `QApplication`, not after.
2. `Abort trap: 6` / `Argument list is empty, the program name is not passed to QCoreApplication` — if `QApplication` is constructed with an empty `argv` (e.g. `QApplication([])` or relying on `sys.argv` when the script was run via `python3 -c`/a heredoc, where `sys.argv` is empty). QtWebEngine's embedded Chromium requires a real `argv[0]`. Fix: run any script touching `QWebEngineView` as a real file (`python3 script.py`), and construct `QApplication(sys.argv)`.

Neither is a real-window requirement — `QWebEngineView` otherwise works fine fully offscreen/headlessly in this environment (confirmed: `setHtml()`, `loadFinished`, and `runJavaScript()` all work without ever calling `.show()`).

## `QWebEnginePage.runJavaScript()`'s promise-following doesn't reliably resolve back to Python here

Per Qt's docs, if the evaluated script's result is a `Promise`, `runJavaScript(script, callback)` is supposed to wait for it to settle and call `callback` with the resolved value. Confirmed directly that this doesn't work reliably in this environment: evaluating an async IIFE that explicitly returns `{status, text}` still invoked the Python callback with an empty `{}`, even though the underlying `fetch()` call itself succeeded (confirmed via a separate check that `window.desk`'s injected keys were all correct).

Workaround that does work: don't rely on `runJavaScript`'s own promise-following at all. Have the JS store the resolved value as a side effect (`promise.then(v => { window.__result = v; })`), fired via one `runJavaScript` call that ignores its own return value, then poll for `window.__result` with *separate*, plain (non-promise-returning) `runJavaScript` calls until it's no longer `null`. This is how the Desk Bridge API's `ChromiumWidget` round-trip test (`ChromiumWidget` → local server → response) is actually verified.

## Reverse video (`char.reverse`) must swap *resolved* colors, not the pre-resolution name strings

A first attempt at fixing the console widget's broken reverse-video rendering swapped `char.fg`/`char.bg` (the raw name strings pyte reports, e.g. `"default"`, `"red"`) *before* resolving them to `QColor`s. This looked right and even passed a shallow test, but is a no-op whenever both names happen to be the literal string `"default"` — swapping two identical strings changes nothing, and `"default"` carries no information about *which* slot (foreground vs. background) it was in once extracted as a bare string, so there's no way to recover "the other one's default" after the swap.

The fix: resolve `fg`/`bg` to concrete colors *first* (each against its own correct default — foreground's default is not the same color as background's default), and swap the two resolved `QColor`s afterward. Generalizes: when two "empty"/"unset" values need to swap places to have any visible effect, resolve them to their real, distinct values before swapping — swapping still-abstract placeholders that happen to look identical is silently a no-op.

## Verifying a `QTextCharFormat` background actually renders needs a dense, whole-widget pixel scan, not a spot-check

Confirmed a `QTextCharFormat.setBackground()` produces a real, correctly-colored background in `QPlainTextEdit`/`QTextEdit` (via `grab()` → `QImage` → `pixelColor()`), but only after abandoning single-pixel or single-row spot-checks: sampling one guessed `(x, y)` coordinate (even when derived from `fontMetrics()` character-cell math) reliably missed the actual glyph/background region and only ever found the surrounding viewport's own background color, making a *correct* fix look like it wasn't rendering at all. Scanning a dense grid across the whole widget and counting color frequencies (`collections.Counter`) reliably found the expected color as a large, unambiguous block, distinguishing a real rendering bug from a bad sampling coordinate. Also note: `grab()`'s returned `QImage` is in *device* pixels (e.g. 2x on a Retina/HiDPI machine, even fully offscreen) — logical-pixel coordinates from `fontMetrics()`/widget geometry don't line up 1:1 with it.

## `pyte` 0.8.2 has its own typo: background bright magenta reports as `"bfightmagenta"`

Confirmed directly: feeding `ESC[105m` (background bright magenta) into a `pyte.Screen` produces a `Char` with `bg == "bfightmagenta"` — missing the `r` — while every other bright color (including foreground bright magenta, `ESC[95m`, which correctly reports `"brightmagenta"`) is spelled correctly. Only affects that one specific background code. If a color-name lookup table ever seems to silently miss exactly one bright-magenta-background case, this is why; handle both spellings rather than waiting on an upstream fix (this library's release cadence is slow — 0.8.2 has been the latest version for a while).

## A blocking `subprocess.run()` on the Qt GUI thread freezes the whole app's UI feedback, not just the caller

A bug report described the TODO widget's item-editor text caret intermittently "disappearing," "sometimes coming back after a few seconds," and "sometimes not" — and speculated (then dismissed as unlikely) that some other process was stealing focus. The real cause had nothing to do with focus: `_write_and_commit` ran `git rev-parse`/`git add`/`git commit` via synchronous `subprocess.run()` calls directly on the Qt GUI thread, both immediately on add/edit and periodically from a debounce timer. While any of those blocked (a slow pre-commit hook, a `.git` lock held by another process, a GPG-signing prompt — anything that can make `git commit` take an unbounded amount of time), the entire Qt event loop stalled, which stops *every* `QTimer` in the process — including `QPlainTextEdit`'s own internal caret-blink timer. So the caret wasn't losing focus; the whole app was just unresponsive for as long as `git` took, and resumed blinking exactly when `git` finally returned (or never, if it was genuinely hung).

The general lesson: any symptom that looks like "some other part of the UI is interfering" (focus loss, stalled animations, unresponsive widgets elsewhere) is also exactly what a blocking call *anywhere* on the GUI thread produces, since Qt has only one thread driving its whole event loop. Before chasing a focus/interference theory, check for a blocking, especially I/O-bound (subprocess, network, disk) call reachable from that code path first — the "obvious" symptom (a specific widget losing focus) doesn't localize the cause to that widget at all.

The fix: move the actual blocking call to a background `threading.Thread`, and report its result back to the GUI thread via a Qt signal's `.emit()` (Qt automatically queues a signal emitted from a non-GUI thread onto the receiving `QObject`'s own thread — this is the safe, idiomatic way to marshal a background result back without touching a `QWidget` from the wrong thread). If the same operation can be triggered again before a previous one finishes, guard the actual blocking work with a `threading.Lock` so overlapping attempts serialize on the background thread rather than raising the same hazard's mirror image (two concurrent `git commit`s corrupting the same repo).

## The TODO widget silently reverts external edits to `TODO.md` it doesn't know about

The running `TodoWidget` loads `TODO.md` into an in-memory `state["items"]` list at `reload()` time and, on its own next write (add/edit/reprioritize — see `_write_and_commit`), always re-renders the *entire* file from that in-memory list via `render_todo_file`. If something else edits `TODO.md` directly on disk in the meantime — another process, a text editor, or (as actually happened) an agent editing the file directly to mark an item `COMPLETED` and add a `[planned: ...]` note — the widget has no idea that happened. Its next write overwrites the file with its own (now-stale) in-memory content, silently discarding the external edit, with no error or warning anywhere.

Confirmed directly, twice, in the same session: an agent added `COMPLETED:` to a finished TODO item's line, and each time, the next real "Add Item" action taken through the live, already-running `TodoWidget` reverted it back to un-`COMPLETED`, because that running widget instance had loaded its in-memory copy before the direct edit landed.

If editing `TODO.md` directly while a `TodoWidget` instance may also be running against the same file, either get the widget to `reload()` (its own button, or restart it) right after each external edit, or re-check the file after any action taken through the live widget and re-apply the external edit if it got clobbered. **Update:** TODO d25e557 fixed this — the widget now watches its resolved `TODO.md` for external changes and reloads automatically (see `plans/todo-widget-file-watcher.md`), so a live instance no longer silently reverts an out-of-band edit; direct file edits while the app is running are safe again.

## A `.show()`n test widget is a real OS window and can steal real keyboard focus mid-test

While verifying the console widget headlessly, a synthetic `send_line()` helper drove input via direct `widget.keyPressEvent(ev)` calls — but the widget was also `.show()`n (to let redraws actually paint), making it a real, visible, focusable OS window. Typing in an *unrelated* window on the same machine while such a test was running produced garbled command text in the terminal widget (extra, unrelated characters appearing mid-command) — the shown test window had genuine OS keyboard focus at that moment, so real hardware keystrokes from typing elsewhere were *also* delivered to it through Qt's normal event pipeline, interleaved with the synthetic `keyPressEvent` calls driving the test.

This isn't a bug in the widget or the test's logic — it's a hazard of `.show()`-ing a real window during any interactive verification step. If a headless/scripted test needs to `.show()` a widget (e.g. so painting/redraw actually happens), avoid typing in any other window while it runs, or drive the whole test without touching the keyboard until it completes.

## `QWidget.scroll()` (used internally by `QAbstractScrollArea`'s fast-scroll path) silently drags along any child widget inside the scrolled area

TODO 4adfcad/TODO 1f9bd34 fixed the top-left Desk picker/bottom-right zoom control drifting away from their pinned screen-space corners on window resize, but attributed it to a vague "some recurring internal Qt layout pass, plausibly `QGraphicsView`'s scrollbar/viewport geometry recalculation" and fixed it by reasserting position afterward without pinning down the real mechanism. TODO 82d66c0 found the actual cause while investigating the same drift happening on pan/zoom too: `QGraphicsView` (a `QAbstractScrollArea`) scrolls its viewport via `QWidget.scroll(dx, dy)` as a fast-blit optimization, and `QWidget.scroll()`'s own documented behavior is to also move any child widget whose geometry lies fully inside the scrolled area, by that same delta. The Desk picker and zoom control are plain `QWidget` children of `self.viewport()` (positioned with manual `.move()` calls, not scene items), so literally *any* operation that shifts the view's scroll position — panning, or a zoom operation that re-centers the view (`zoom_to_fit`, `reset_zoom`) — silently drags them along, confirmed directly by instrumenting `scrollContentsBy` and observing large nonzero deltas exactly when the drift occurred. This is very likely the same actual mechanism behind the original resize-time drift too (the very first resize already fires `scrollContentsBy` with nonzero deltas, given this app's huge/effectively-infinite scene rect).

If a plain `QWidget` is added as a direct child of a `QAbstractScrollArea`'s viewport (rather than as a scene item, e.g. for a "screen-space HUD overlay on a pannable/zoomable canvas" pattern) and its position mysteriously drifts whenever the view scrolls, zooms (if the zoom re-centers), or resizes (if resizing changes the scroll range) — suspect `QWidget.scroll()`'s child-dragging behavior first, not a generic "layout pass." Fix by overriding `scrollContentsBy(dx, dy)`, calling `super().scrollContentsBy(dx, dy)`, then reasserting the overlay widget's fixed position — confirmed this reassertion can be synchronous here (unlike a resize-triggered reassertion, which needed `QTimer.singleShot(0, ...)` deferral because Qt's displacing pass runs later; `scrollContentsBy` itself *is* the mechanism doing the moving, so there's nothing further to be preempted by). Guard the override with `hasattr` for the overlay attribute(s): `QGraphicsView.__init__` can invoke `scrollContentsBy` during its own internal setup, before a subclass's `__init__` has constructed those attributes yet.

## The symlinked-`tempfile.mkdtemp()`-path watchdog gotcha isn't specific to `WidgetWatcher` — it hits *any* single-file `watchdog` watcher on macOS

Building the TODO widget's own file watcher (TODO d25e557, a small dedicated `watchdog` observer distinct from `WidgetWatcher`) hit the exact same failure already documented above ("`WidgetWatcher` never fires when pointed at a `tempfile.mkdtemp()` path on macOS") in a second, independent piece of code — because the root cause (`tempfile.mkdtemp()`'s `/var/folders/...` symlink resolving to `/private/var/folders/...` in the FSEvents observer's reported `event.src_path`) is a property of `watchdog`/macOS, not of `WidgetWatcher`'s specific implementation. It's confusingly hard to notice while debugging: the watcher's real background thread doesn't error, the debounced signal *does* still fire (since the debounce timer itself doesn't depend on the path match), so it's easy to assume the watcher "worked" and go looking for the bug elsewhere (e.g. suspecting the Qt signal/thread marshalling, or the file read racing the write) — when the actual filter comparing `event.src_path` to the watched target path is just silently never matching and returning early.

Any new code that watches one specific file by filtering `watchdog` events down to an exact path (not just `WidgetWatcher`) must `.resolve()` both the stored target path and each event's `src_path` before comparing — not only when constructing the test's temp directory, but as standard practice inside the watcher implementation itself, so it's also correct against any real symlinked directory a user might actually have (not just test tempdirs).

## A brand-new file reliably fires *both* a `watchdog` `FileCreatedEvent` and a `FileModifiedEvent` in quick succession

Building the Temporary UI feature's directory watcher (TODO a02b001, `TempUiManager`/`_DirectoryHandler`), a first version classified "was this file just added, or just edited" from whichever raw watchdog event type triggered the (debounced) callback. This reliably misclassified *every* newly-created file as "edited": creating a file (even via a single `Path.write_text()` call) fires a `FileCreatedEvent` immediately followed by a `FileModifiedEvent` (the write itself modifies what it just created) — and since the debounce logic cancels/replaces any pending timer for the same path on each new event, the *last* event before the debounce fires determines the recorded type, which in practice is always the trailing `FileModifiedEvent`, never the `FileCreatedEvent`.

Don't classify "created vs. modified" from the specific event type of whichever event happens to survive a debounce window. Instead, track which filenames have ever been seen before (a plain `set`, populated the first time a given name is handled) and classify from that: the first time a name is handled, it's "added"; every time after, it's "edited." This is both simpler and correct, since it matches what the distinction is actually *for* (has the user/downstream logic seen this file before) rather than trying to infer it from Qt/watchdog's own low-level event stream.

## A widget that reads `current_context` once in its own `__init__` depends on *when in `DeskWindow.__init__` it gets constructed*, not just on the context module existing

TODO 1a051d1: the TODO widget started showing "No TODO.md found near the current Desk's directory" at boot even though a real `TODO.md` sat right next to the current Desk's file. `desk.shell.current_context` is a plain module-level global, populated by `DeskWindow._refresh_picker()`; the TODO widget's `reload()` reads it once, synchronously, in its own `__init__`. `DeskWindow.__init__` happened to call `_load_desk_widgets()` (which can construct a saved `TodoWidget`) *before* `_refresh_picker()` ever ran — so any such widget saw `None` for the current directory, every single boot, since the very first commit that introduced it. This had been invisible for a long time not because the ordering was ever correct, but because the TODO widget used to have a manual "Reload" button: since both calls finish before the event loop starts, a user's *first* click of Reload always landed after `_refresh_picker()` had already run, silently papering over the wrong construction-time order. Removing that button (TODO d25e557) in favor of automatic file-watching — which only reacts to *later* external file changes, never to the widget's own initial state — turned an unnoticed ordering bug into a permanent, un-workaround-able regression.

If a widget resolves some piece of shared, lazily-populated global state exactly once at construction time (rather than subscribing to a live-update signal), auditing "is the state actually populated by the time this widget gets built" matters more than auditing the state-setting code itself — and a manual escape hatch (a Reload button, a refresh action) can mask a real ordering bug for a long time by giving the *user* a way to re-trigger the read after the state becomes correct, right up until that escape hatch is removed as "no longer needed."

## `QPlainTextEdit.setReadOnly(True)` doesn't just block editing — it silently strips the flag Qt requires before it will ever paint the native cursor

TODO 1217380: the Console widget's terminal cursor (tracked via `QPlainTextEdit`'s own native text cursor — `setTextCursor()` + `setCursorWidth()`, in `widgets/console/widget.py`) never rendered at all, even though focus (`hasFocus()`), `cursorWidth()` (2), and `cursorRect()` (a valid, non-empty rect) were all individually confirmed correct in isolation. The actual cause: `setReadOnly(True)` doesn't just disable keyboard/mouse editing as its name suggests — it replaces `textInteractionFlags()` wholesale, from the default `Qt.TextInteractionFlag.TextEditorInteraction` down to just `Qt.TextInteractionFlag.TextSelectableByMouse`, dropping `Qt.TextInteractionFlag.TextEditable` entirely (confirmed directly: `w.textInteractionFlags()` before/after `setReadOnly(True)`). Qt's internal text-cursor paint/blink logic requires that flag before it draws the cursor at all, regardless of every other cursor-related property being otherwise correct — so a read-only `QPlainTextEdit`/`QTextEdit` simply never shows its native cursor, full stop.

Re-adding the flag (`setTextInteractionFlags(flags | Qt.TextInteractionFlag.TextEditable)`) does bring the native cursor back, but also flips `isReadOnly()` back to `False` — the two are coupled, not independently controllable — reopening mouse-driven native editing (drag-drop, context-menu paste) even if keyboard input is still fully intercepted elsewhere. If a read-only text widget needs a visible caret/cursor indicator, don't fight this coupling: render the cursor explicitly (e.g. a per-character reverse-video `QTextCharFormat` override at the tracked position, as the Console widget now does) instead of relying on Qt's native mechanism.

## A `Qt.WindowType.Popup` + `WA_DeleteOnClose` widget can be destroyed mid-callback by a downstream modal dialog, crashing a `self.close()` called after emitting a signal

TODO c8f6fb3: the Desk picker's name-popup (`_DeskListPopup`, a `Qt.WindowType.Popup` window with `WA_DeleteOnClose`, same pattern as `WidgetSpawnMenu`) crashed the whole app with `RuntimeError: wrapped C/C++ object of type _DeskListPopup has been deleted` when picking a Desk that required a confirmation dialog to switch to. `_activate_item` emitted `desk_chosen` (which synchronously runs the connected chain all the way to `DeskWindow.switch_desk` → `_provision_temp_ui`, which can show a real `QMessageBox.question`) and only *then* called `self.close()`. A `Qt::Popup` window auto-closes as soon as it loses active-window status — the same mechanism that makes "click away to dismiss" work — and a modal dialog appearing *does* take that status away from it. Since `WA_DeleteOnClose` schedules a `deleteLater()`, and a modal dialog's own `exec()` runs a nested event loop that processes pending deferred-delete events, the popup's underlying C++ object was destroyed while `_activate_item` was still executing on that same object — so the later `self.close()` call executed against an already-deleted object. Confirmed directly with a minimal, business-logic-free repro: a `_DeskListPopup`, a slot connected to one of its signals that opens any real `QDialog().exec()`, then calling `self.close()` afterward reproduces the identical `RuntimeError` — the specific downstream cause (`_provision_temp_ui`'s dialog) is incidental, not essential.

If a `Qt.WindowType.Popup`/`WA_DeleteOnClose` widget's activation handler both emits a signal with arbitrary downstream effects *and* needs to close itself, call `self.close()` **before** emitting, and don't touch `self` again afterward — regardless of whether the object ends up destroyed synchronously (a nested event loop inside a downstream slot) or only later (the ordinary case). Any other widget built on the same Popup+DeleteOnClose pattern whose activation handler emits-then-closes (e.g. `WidgetSpawnMenu._activate_item`) has the identical latent hazard, even if nothing downstream happens to show a modal dialog yet — see `PARKINGLOT.md`.

## A `watchdog` file-watcher that only handles `FileCreatedEvent`/`FileModifiedEvent` silently misses any atomically-written file (write-to-scratch-name, then rename into place)

TODO bb65aab: a real temp-UI file, written into this project's own already-watched `.desk_temp/` directory while a real Desk session had it as the current Desk, never produced a notification — no error, nothing in the logs, the file just sat there undetected. `TempUiManager`'s `_DirectoryHandler.on_any_event` (`src/desk/shell/temp_ui_manager.py`) filtered on `isinstance(event, (FileCreatedEvent, FileModifiedEvent))`, which covers a direct `open()`/`write()`, but not the extremely common "atomic write" idiom many editors and safe-write libraries use instead — write the new content to a scratch-named file, then `os.rename()` it into its real final name. `watchdog` reports *that* as a `FileMovedEvent`, a third, distinct event type this filter silently discarded. Confirmed directly: a real `DeskWindow`, watching this project's real `.desk_temp/`, writing a temp-UI file via scratch-name-then-`os.rename()` produced zero `file_added` events and no banner — while the identical content written with a single direct `Path.write_text()` call was detected correctly.

A second, independent gotcha compounds the first: even after widening the `isinstance` check, a `FileMovedEvent`'s *useful* path is `event.dest_path` (where the file ended up) — its `src_path` is the scratch name, which won't match whatever filename-based filter (a UUID check, an exact target path, a directory-prefix check) the watcher applies, since that's exactly the whole point of a scratch name. Reading `event.src_path` unconditionally (as `FileCreatedEvent`/`FileModifiedEvent` correctly do, since renamed-*from* is meaningless for those) silently fails the filter for the wrong reason before a widened type-check would even matter.

Any `watchdog` handler meant to detect "a matching file showed up or changed" — not just this one — needs to explicitly handle `FileMovedEvent` and read `dest_path` for it specifically (falling back to `src_path` only for the event types where that's the field that actually matters), or it will silently miss every tool/editor/agent that writes safely via rename instead of a direct write. `widgets/todo/widget.py`'s own single-file watcher (`_SingleFileHandler`) had the identical gap against `TODO.md` itself, confirmed and fixed the same way by TODO 54b0a9f — two independent occurrences of the same lesson in one codebase within a single day, worth double-checking any *other* `watchdog` handler here for the same pattern before assuming it's fine.

## A widget's own `isVisible()` is `False` at the end of its own `__init__` — it hasn't been parented/shown by whoever placed it yet

The Git Status widget (TODO ef77819) polls `git status` on a timer, gated on `self.isVisible()` so a widget nobody's looking at doesn't burn compute — and calls that same gated poll once at the end of `__init__` too, to show real status immediately rather than leaving the widget blank until the first timer tick. That initial poll was silently a no-op every single time: a `QWidget` is not yet visible at the moment its own constructor finishes running, regardless of whether it's about to be shown a moment later by its caller (`PythonWidgetHost._rebuild` builds the widget, *then* adds it to a layout; a `QGraphicsProxyWidget`-embedded widget becomes visible only once the whole ancestor chain is shown) — there is no point during construction where `isVisible()` can honestly return `True`, since visibility is inherently a property of showing, not building. Confirmed directly: constructing the widget and deliberately never calling `.show()` on it at all still left it permanently blank, proving the gate — not any timing race — was eating the first poll outright.

A visibility (or any other "is this actually on screen / being used" gate) that's meant to skip *later*, repeated/expensive work should not be reused unconditionally for the *first* invocation of that work performed from inside `__init__` — separate the two with an explicit flag (e.g. `_poll(initial=True)` bypassing the gate) rather than assuming the object's own state already reflects what its caller is about to do with it.

## Calling `setFocus()` inside an embedded child's `eventFilter` for the *same* mouse press is silently clobbered by `QGraphicsProxyWidget`'s own focus resolution

TODO 6cf4543: the Lightning Round widget's `Qt.FocusPolicy.StrongFocus` and `keyPressEvent` override (correctly implemented from the start — see `plans/lightning-round-tempui.md`) only actually worked if the user clicked an option button or empty stretch space within the widget. Clicking the prompt/item `QLabel` text — the most natural place to click, since that's the actual content being read — silently failed to grant keyboard focus, because Qt's click-to-focus handling only ever considers the *exact* child widget under the cursor, and `QLabel` defaults to `Qt.FocusPolicy.NoFocus`; this doesn't climb to an ancestor's focus policy the way an *ignored key press* does. This part is ordinary, well-known Qt behavior (true even outside a `QGraphicsProxyWidget`).

The non-obvious part: the seemingly-obvious fix — install an event filter on the label and call `self.setFocus()` synchronously on `QEvent.Type.MouseButtonPress` — did not work either, and failed *silently* (no exception, `hasFocus()` just stayed `False`). Confirmed directly, via a real `WorkspaceView`/`QGraphicsProxyWidget`: `QGraphicsProxyWidget` resolves which embedded child widget should own scene-level keyboard focus for a given press *after* installed event filters run for that same event, walking to the specific child under the cursor and clearing scene focus if that child isn't focusable — so a synchronous `setFocus()` call made from inside the filter gets clobbered immediately afterward by this later step, within the same event. Deferring the call with `QTimer.singleShot(0, lambda: self.setFocus(...))` lets the grab happen on the next event-loop iteration, after `QGraphicsProxyWidget`'s own resolution has already finished clobbering — and it sticks. This is the same "something else reasserts state right after this" shape as the `scrollContentsBy`/HUD-positioning fixes elsewhere in this codebase, just one layer deeper (inside a single event's dispatch, not across a later Qt layout pass).

If a click on a non-focusable child inside a `QGraphicsProxyWidget`-embedded widget needs to grant focus to an ancestor instead (e.g. via an installed event filter), don't call `setFocus()` synchronously from that filter — defer it with `QTimer.singleShot(0, ...)`, and verify with a real `QGraphicsProxyWidget` (a bare, unwrapped widget under `QTest` won't reproduce this at all, since the clobbering step is specific to proxy-widget embedding).

Separately, worth flagging for whoever verifies proxy-embedded widget interactions headlessly with `QTest.mouseClick`: a hardcoded content-relative click offset can easily land on a `WidgetFrame`'s titlebar chrome instead of the intended content — `WorkspaceView.mousePressEvent`'s `_hit_test_chrome` intercepts titlebar clicks for dragging before they ever reach the scene's normal item-interaction path, so a "reproduction" built against the wrong coordinates can look like it confirms a bug (or a fix) while actually testing an unrelated code path. Compute the target's real on-screen position from the actual widget hierarchy (`child.mapTo(frame, ...)` plus the proxy's scene position) and confirm with `view.itemAt(...)` before trusting the result.

## A genuinely separate top-level `Qt.WindowType.Tool` window parented to a `QGraphicsProxyWidget`-embedded widget never gets real OS-level keyboard focus, even though every Qt-level flag says it does

TODO c8e3b28: the TODO widget's add/edit item popup (`_ItemDialog`, a `Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint` widget, constructed as `_ItemDialog(self)` where `self` is the embedded `TodoWidget`) already called `self._field.setFocus()`, yet the field never actually had real keyboard focus once popped up in the live app. `self.window()` for an embedded `python`-kind widget resolves to its `WidgetFrame` (see this file's own `QWidget.graphicsProxyWidget()` entry above on why `.window()` correctly walks up to it) — but `WidgetFrame` is never itself shown as an independent OS-level window; it only exists as the source content for a `QGraphicsProxyWidget`, embedded into the real top-level `DeskWindow`'s scene. Passing a descendant of it as a `Qt.WindowType.Tool` widget's `parent` still makes that widget genuinely top-level (Qt honors the `Tool` flag regardless of parent) — `isActiveWindow()` on it, and even `QWidget.activateWindow()`/`.raise_()` called on it, all report/behave as if it worked — but the single, real, global `QApplication.focusWidget()` never actually moves to it, so real keystrokes keep going wherever they were going before (in this case, the `WorkspaceView` housing the whole embedded widget tree). Every per-widget signal you'd normally trust (`hasFocus()`, `isActiveWindow()`) lies in this specific configuration; only checking `QApplication.focusWidget()` itself (or, better, actually driving a keystroke through and observing where the character lands) revealed the real state.

Confirmed by direct, controlled comparison in the same running app: constructing the identical `_ItemDialog` with the real `DeskWindow` (or even `parent=None`) instead of the embedded widget reliably moved `QApplication.focusWidget()` to the dialog's field; constructing it with the embedded widget (or any of its embedded ancestors) as parent never did, no matter how many `raise_()`/`activateWindow()`/`setFocus()` calls were added or how they were deferred.

If a widget kind (`build() -> QWidget`, embedded via `PythonWidgetHost`/`WidgetFrame`/`QGraphicsProxyWidget`) needs to pop up a genuinely separate top-level window that should receive real keyboard input, don't parent it to `self` (or any embedded ancestor) for that purpose — parent it to `QApplication.activeWindow()` instead (reliably the real `DeskWindow` at the moment a click inside it triggered the popup), falling back to `self` only if nothing is active. Since that breaks Qt's automatic parent-child object lifetime (the popup is no longer a child of the embedded widget, so it won't be auto-deleted when that widget is torn down, e.g. by hot reload), wire that explicitly instead: connect the embedded widget's own `destroyed` signal to the popup's `close` method (the same "connect a *different* object's bound method to `destroyed`" pattern already established elsewhere in this file for the reverse direction).

## An embedded `QWebEngineView` bounces an unconsumed wheel event back up to its parent, so forwarding wheel events to it can infinitely recurse

TODO c44e88f: making the browser widget's page scroll meant letting `WorkspaceView.wheelEvent` forward wheel events to the embedded `QWebEngineView` (via `super().wheelEvent(event)`) instead of treating them as a canvas zoom. That worked — but *intermittently* crashed with `RecursionError: maximum recursion depth exceeded`, right back at the top of `wheelEvent`. The cause: when `QtWebEngine` receives a wheel event its page can't consume (a non-scrollable page — `about:blank` — or one already at its scroll limit), it *propagates the unconsumed event back up the parent widget chain* (Chromium-style scroll chaining). That bounced event travels up through the `QGraphicsProxyWidget`/viewport and re-enters `WorkspaceView.wheelEvent` **synchronously, while the original `super().wheelEvent(event)` call is still on the stack** — which sees the cursor still over the web view, forwards again, bounces again, and recurses until the stack overflows. It's timing-dependent (hence intermittent): it only bounces when the page genuinely has nothing to scroll at that moment, which for a `QWebEngineView` depends on async page-load/compositor state.

The fix is a re-entrancy guard: set a flag around the `super().wheelEvent()` forward, and if `wheelEvent` is re-entered while that flag is set, just return (don't re-forward, and don't fall through to the zoom branch either — zooming on a bounce-back would be wrong). This also harmlessly covers the analogous case of a `QAbstractScrollArea` bouncing a wheel event at its scroll boundary. The general lesson: any time you forward an input event from a container into an embedded child that might *not* consume it, assume it can bubble straight back into your handler on the same stack — guard against synchronous re-entry rather than trusting the child to swallow it.

## A `QTreeWidgetItem` (or other PyQt-wrapped C++ object)'s `id()` is not a stable dict key across separate accesses

Building the Markdown (Extended) widget's TOC (TODO `a76e723`), the first
attempt mapped each `QTreeWidgetItem` to its corresponding `_SectionWidget`
via a plain Python dict keyed on `id(toc_item)`, populated once right after
creating each item. Clicking a TOC entry later (via the `itemClicked`
signal, or any other fresh call like `tree.topLevelItem(i)`/`item.child(i)`)
looked up `id(item)` again — and the lookup silently missed, because PyQt/
sip does not guarantee the *same Python wrapper object* is returned for
repeated accesses to the same underlying C++ `QTreeWidgetItem`. If nothing
else keeps the original Python wrapper alive, a later access can produce a
newly-allocated wrapper with a different `id()` (or even, per CPython's
`id()`-reuse-after-`free()` behavior, a coincidentally *matching* one for
the wrong object) — either way, `id()`-as-dict-key is not trustworthy here.

This was caught by an actual test (clicking a nested TOC entry after
collapsing its ancestor section was supposed to re-expand the ancestor; it
silently didn't), not by inspection — the bug produces no error, just a
lookup that returns `None`/wrong-value some of the time.

The fix: don't shadow Qt object identity with a side dict at all. Use the
item's own storage — `item.setData(column, Qt.ItemDataRole.UserRole,
python_object)` / `item.data(column, Qt.ItemDataRole.UserRole)` — which
PyQt keeps attached to the real C++ object regardless of which Python
wrapper is currently referencing it. General lesson: for any Qt item type
that supports `setData`/`data` (tree/list/table items, model indexes),
prefer that over a Python-side `id()`-keyed lookup table whenever the same
logical item might be accessed through more than one code path (a signal
callback vs. a direct `.child()`/`.item()` walk, for instance).

## `QSortFilterProxyModel.setRecursiveFilteringEnabled` silently misses matches in unexpanded `QFileSystemModel` branches

Building the File Explorer widget's search box (TODO `b927389`), the
obvious approach was `QFileSystemModel` + `QSortFilterProxyModel` with
`setRecursiveFilteringEnabled(True)` (the documented, built-in Qt
mechanism for "keep a row visible if any descendant matches the
filter"). Confirmed directly, against a real temp directory tree, that
this does not work correctly on top of `QFileSystemModel`: a match
several levels deep in a directory that has never been expanded in a
view (and so never lazily fetched by the model) is invisible to the
recursive filter — it can only "recurse into" rows the model has
already materialized, not force-load undiscovered ones just to check
them. A fresh search against a never-browsed subtree silently returns
nothing, with no error.

Separately (and more dangerously) hit a real crash chasing this down:
holding a plain `QModelIndex` captured *before* calling
`setFilterFixedString(...)` and then reusing it afterward segfaults —
`QSortFilterProxyModel` invalidates its internal index mapping on a
filter change, so an old `QModelIndex` into it is a dangling reference,
not just "stale data." Always re-fetch (`model.mapFromSource(...)` /
`model.index(...)`) a fresh index *after* any model-invalidating change
rather than reusing one obtained beforehand.

The fix here was to stop trying to make Qt's built-in recursive
filtering work at all: a bespoke, synchronous `Path.iterdir()` walk
(building a small `QStandardItemModel` containing only matches and
their ancestor chain) swapped onto the tree view in place of
`QFileSystemModel` while a search is active. See
`plans/file-explorer-widget.md` and `widgets/file_explorer/widget.py`'s
`_build_search_model`. General lesson: `QFileSystemModel`'s laziness
(by design, for scalability) is fundamentally in tension with any
filtering mechanism that needs to know about the *whole* tree to decide
what's visible — recursive filtering over it needs either an eager
pre-walk (as done here) or a background thread that populates ahead of
the filter, not just flipping a boolean on the proxy.

## `QSvgWidget` stretches an SVG non-uniformly to fill its rect — it does not preserve aspect ratio

Building the SVG Viewer widget (TODO `c7d6e4d`), the obvious starting
point was `PyQt6.QtSvgWidgets.QSvgWidget` — it sounds like (and is
documented as) "a widget that displays an SVG." Confirmed directly,
headlessly: loading a simple 100×100 SVG containing a centered circle
into a `QSvgWidget` resized to 400×100 renders the circle as a
~300px-wide ellipse, not a circle — `QSvgWidget`'s `paintEvent` renders
the SVG into its *entire* widget rect with no attempt to preserve the
source's aspect ratio, so any widget size that doesn't match the SVG's
own aspect ratio visibly distorts the content.

Fix: don't use `QSvgWidget` for anything where the widget's aspect
ratio might not match the SVG's own — use a bare `QSvgRenderer`
directly and render into a manually computed, letterboxed `QRectF`
(scaled to fit within the widget, centered on whichever axis has
slack) instead of the widget's raw `rect()`. See
`widgets/svg_viewer/widget.py`'s `_fit_rect`/`_AspectSvgView`. General
lesson: a Qt convenience widget named after "displaying X" doesn't
necessarily do the display-fitting work you'd assume from the name —
check what it actually paints into (its full rect vs. something aspect
-aware) before trusting it for anything other than a full-bleed, exact
-aspect-match use case.

## A native-style-drawn control (e.g. `QTreeView`'s branch/disclosure arrow) can visually desync from its own click hit-region once embedded in a zoomed `QGraphicsProxyWidget`

Reported against the File Explorer widget (TODO `b927389`): the
expand/collapse arrows appeared to scale independently from the rest of
the tree, and clicking them didn't always work. Couldn't reproduce the
visual symptom directly in this headless environment —
`QT_QPA_PLATFORM=offscreen` renders with Qt's own software style, not
the real platform style (`QMacStyle` on macOS, which is what the actual
running app uses) — so this was root-caused by reasoning from what's
already documented rather than by seeing the glitch: `QTreeView`'s
click-to-toggle hit-testing is computed purely from `indentation()`/row
geometry, entirely independent of what the active style actually paints
for the arrow. If a native style's own drawing doesn't composite
correctly through `QGraphicsProxyWidget`'s offscreen-buffer-then-blit
pipeline at a non-1.0 view scale (a plausible sibling of this file's
existing note on embedded-widget mouse coordinates being unreliable
under zoom), the *visible* arrow can end up drawn somewhere slightly
different from the *real* (still entirely correct) clickable region —
so a click that looks like it landed on the arrow misses, while the
underlying toggle mechanism itself was never actually broken.

Fix: don't rely on the native style for this element at all inside an
embedded/zoomable context — override `QTreeView.drawBranches` and paint
a simple indicator with plain `QPainter` calls, positioned within the
exact same indentation rect Qt's own hit-testing already uses. This
can't drift from the hit region because it's now derived from the same
geometry, and plain `QPainter` drawing (unlike native style painting)
reliably respects whatever transform the enclosing view applies. See
`widgets/file_explorer/widget.py`'s `_FileTreeView`. General lesson:
if a *native-platform-style-painted* element (checkboxes, disclosure
triangles, radio buttons — anything a style plugin draws rather than
plain `QPainter` primitives) behaves oddly only when embedded in a
`QGraphicsProxyWidget` and/or at non-unity zoom, suspect the native
paint path itself before assuming the interaction/event-handling logic
is at fault — and note that this category of bug may not reproduce
under the offscreen platform, since that skips the real native style
entirely.

## An uncaught Python exception escaping a Qt-signal-invoked slot can crash the whole process, not just raise -- and this can happen at any such slot, not only the one already fixed for it

TODO 810a5d6: a user reported a segmentation fault opening a `.desk`
file; the last action beforehand was double-clicking a file in the File
Explorer widget (`QTreeView.doubleClicked` → `_open_index`, which opens
the file in a new Editor widget instance via `widget.set_file(path)`).
The captured traceback was cut off before the actual exception type/
message, so the precise originating bug was never conclusively
identified -- but that ended up not mattering, because this codebase
had *already* documented the general mechanism behind exactly this kind
of crash, at a different call site: `PythonWidgetHost._rebuild`'s own
docstring and `plans/isolate-hot-reload-crash.md` record that an
uncaught exception escaping a Qt slot (there, the Hot Reload Broker's
`widget_changed` signal) is fatal to the whole process in this PyQt6
setup, confirmed via a real crash. `QTreeView.doubleClicked` is exactly
the same shape of hazard -- a Qt-dispatched signal invoking a Python
slot (`_open_index`) that calls into arbitrary further code
(`widget.set_file`, and whatever *that* widget kind's implementation
does) -- just a call site nobody had hardened yet.

The mistake worth not repeating: treating the earlier hot-reload fix as
having "solved" this class of bug, rather than as one instance of a
general rule (*any* Qt-signal-invoked slot in this app is a hard
crash boundary) that has to be re-applied at every such slot
individually -- a single global backstop now exists (`desk
.crash_handler`, TODO 95f7ce9's `sys.excepthook`-based logger, which
does *not* prevent the crash itself, only records it), but each hazard
still has to be found and hardened at its own call site. When a
crash report includes a Python traceback (even a truncated one) ending
inside code reached from a `*.connect(...)`-wired slot, suspect this
mechanism first, regardless of whether the specific exception can be
pinned down -- wrapping that slot's risky call in `try`/`except
Exception` (logging via `exc_info=True`, matching `_rebuild`'s own
style) fixes the crash regardless of the exact underlying cause. Also
worth noting: a real, signal-level segfault with no Python involved at
all (this app installs no `faulthandler`) prints *no* Python traceback
whatsoever (see `PARKINGLOT.md`'s Desk Picker crash note) -- so a report
that *does* include one, even an incomplete one, points at this
uncaught-exception mechanism, not an unrelated native crash.

## `QWidget.mapToGlobal()` is unreliable for a `QGraphicsProxyWidget`-embedded widget under a non-unity view transform -- not just live mouse events

TODO 10b0321: fixing the TODO widget's add/edit popup so it stays
within the widget's own on-screen bounds needed that bounds rect in
the first place -- the obvious approach, `self.mapToGlobal(QPoint(0,
0))` / `self.mapToGlobal(QPoint(width, height))` on the embedded
widget itself, was tried first and confirmed wrong before building
anything on top of it. Reproduced directly: a widget placed at a
non-origin scene position, embedded via a real `WorkspaceView`
(mirroring the actual `WidgetFrame` -> `PythonWidgetHost` -> built
-widget nesting depth), then the view zoomed 2x -- `mapToGlobal()`
reported a rect offset by exactly the widget's own *placed scene
position*, as if it had been placed at the scene origin instead, while
still correctly applying the 2x zoom scale to the reported *size*. In
other words: right size, wrong position, and wrong in a way that's easy
to not notice if the widget in question happens to sit near the scene
origin during manual testing.

This is the same underlying category the existing "mouse events
delivered into a `QGraphicsProxyWidget`-embedded widget don't reliably
reflect real screen coordinates once the view is zoomed" entry (above)
already documents -- but that entry is specifically about live
`QMouseEvent` coordinates; this confirms the *static* geometry API
(`mapToGlobal`/`mapFromGlobal`) has the analogous problem, not just
event coordinates. Don't assume a plain geometry call "must" be safe
just because it isn't an event handler.

The reliable alternative, confirmed against the same real setup: don't
ask the embedded widget to map its own coordinates at all -- go through
the enclosing proxy/view chain explicitly, composing with this file's
first entry (`self.window().graphicsProxyWidget()` to find the real
proxy from a descendant):

```
proxy = self.window().graphicsProxyWidget()
view = proxy.scene().views()[0]
window_point = widget.mapTo(self.window(), local_point)   # local -> window-local
scene_point = proxy.mapToScene(QPointF(window_point))     # window-local -> scene
global_point = view.viewport().mapToGlobal(view.mapFromScene(scene_point))  # scene -> real screen
```

See `widgets/todo/widget.py`'s `_screen_point`/`_screen_rect`. If a
zoom-dependent position/size bug shows up for something computed via
`mapToGlobal`/`mapFromGlobal`/`geometry()`-style APIs on a
canvas-embedded widget, suspect this before the specific feature's own
logic.

## Manually constructing a `QDropEvent` in Python and calling `dropEvent()` on it directly is flaky, not deterministically broken or safe

While writing headless verification for drag-and-drop file support
(TODO 5915ac2), an identical construct-a-`QDropEvent`-then-call-
`view.dropEvent(event)` sequence segfaulted on one run and completed
successfully on the very next, unchanged run. This has the shape of a
dangling-pointer/reference-counting bug in PyQt6's ownership handling
for a manually-built event object dispatched outside Qt's own event
loop, not a logic bug in the code under test -- so a single passing
run proves nothing, and a single crashing run doesn't necessarily mean
the code under test is wrong either.

The reliable fix: don't construct a real `QDropEvent` for a headless
test at all. `dropEvent`/`dragEnterEvent`/etc. only ever call a small,
fixed set of methods on whatever object they're given
(`.mimeData()`/`.position()`/`.acceptProposedAction()`/`.isAccepted()`
here) -- a plain duck-typed Python object implementing just those
methods exercises the exact same code path deterministically, with
none of the real event class's construction/lifetime risk. See
`plans/drag-drop-open-external.md` for the pattern in full. If a handler needs
to fall through to `super().dropEvent(event)` for the "not handled
here" case, that branch specifically still needs a *real* Qt event
(the C++ base implementation won't accept a duck-typed fake) -- test
that branch's own new logic (if any) directly instead of by driving it
through the real `super()` call.

## `QApplication.aboutToQuit`'s connection order can't be used to sequence cleanup against a widget's own `destroyed` signal

`desk/app.py` connected the shared file-watcher service's
`get_service().stop()` to `aboutToQuit` *last*, with a comment
claiming this makes it run after every other consumer's own cleanup.
That was wrong for any cleanup wired to a widget's `destroyed` signal
instead of directly to `aboutToQuit` (e.g. the TODO widget's
`_flush_on_teardown`, which calls `watcher.stop()`) -- `destroyed`
fires *later*, as part of Qt's own widget-teardown cascade during
actual application shutdown, which happens only *after* all
`aboutToQuit` slots have already run to completion. So the shared
`watchdog.observers.Observer` could already be fully stopped (and
`.join()`-ed) by the time a `destroyed`-triggered `SingleFileWatcher
.stop()` tried to unschedule its own watch from it -- watchdog's own
internal bookkeeping for that watch was already gone, raising a
`KeyError` that crashed the whole Cmd+Q teardown (TODO `03f623a`,
`plans/fix-teardown-keyerror.md`).

The general lesson: connecting slot B to a signal "after" slot A
(construction order) only orders B relative to A's *own* signal firing
-- it says nothing about ordering against a *different* signal (here,
`destroyed`) that fires at a different phase of the same shutdown
sequence, even though both are conceptually "cleanup that happens when
the app quits." Don't assume two different Qt signals' relative timing
without checking; make the cleanup itself tolerant of running in
either order instead (here: treat a `KeyError` from an already
-cleared native watch as "nothing left to do," not a bug).

## `QApplication.focusChanged` reports the enclosing `QGraphicsView`, not the specific widget, for anything embedded via `QGraphicsProxyWidget`

While building the widget-focus concept (TODO `397770c`), the natural
first approach -- connect to `QApplication.focusChanged` and inspect
the `new` widget it reports -- silently gave the wrong answer for any
widget embedded in the canvas (i.e. every actual Desk widget): `new`
was always the `WorkspaceView` (the `QGraphicsView`) itself, never the
specific embedded control (a `QLineEdit`, `QsciScintilla`, etc.) that
actually received focus, confirmed directly by printing
`app.focusWidget()` right after `content.setFocus()` on an embedded
widget. `content.hasFocus()` was `True` at the same moment -- Qt's own
per-widget focus bookkeeping is correct, but `QApplication`'s
app-wide focus tracking only names the one real, top-level-focusable
native widget as far as the OS/window-manager is concerned, which for
scene-embedded content is the view, not anything inside it.

The reliable alternative, confirmed directly: `QGraphicsScene
.focusItemChanged(new_item, old_item, reason)` operates at the correct
level -- `new_item`/`old_item` are the `QGraphicsProxyWidget` whose
*embedded* widget hierarchy now holds (or just lost) focus. From
there, `proxy.widget().focusWidget()` (a plain `QWidget` method, nothing
to do with `QApplication`) correctly returns the specific focused
descendant within that one proxy's own hierarchy. If a feature needs
to know "which embedded widget/frame currently has focus" for
anything canvas-embedded, use the scene-level signal, not
`QApplication.focusChanged` -- the same category of gotcha as this
file's other "mouse/focus/geometry APIs don't reflect what you'd
expect once something is embedded via `QGraphicsProxyWidget`" entries
above; check before assuming the plain top-level API applies.

## `QsciScintilla.marginBackgroundColor()`/`SCI_SETMARGINBACKN` only apply to a `SC_MARGIN_COLOUR`-typed margin — a `NumberMargin`'s actual background is a different mechanism entirely

While making the Editor widget's line-number margin dark-mode-friendly
(TODO `17a2720`), `setMarginsBackgroundColor(...)` was used to color
margin 0 (a `NumberMargin`) to match the editor's own background.
Verifying this by reading it back via `marginBackgroundColor(0)`
(the getter QScintilla pairs with `setMarginBackgroundColor`) failed —
it reported an unrelated, untouched value, not the color that was just
set and that visibly renders correctly.

The reason: `marginBackgroundColor`/`setMarginBackgroundColor` are
backed by Scintilla's `SCI_GETMARGINBACKN`/`SCI_SETMARGINBACKN`, which
Scintilla's own docs limit to margins whose *type* is `SC_MARGIN_COLOUR`
(or `SC_MARGIN_BACK`/`SC_MARGIN_FORE`) — a `NumberMargin`'s background
is controlled by an entirely different mechanism, the `STYLE_LINENUMBER`
style's own background (what `setMarginsBackgroundColor` -- plural,
note the name -- actually sets, via `SCI_STYLESETBACK`). Two visually
identical-looking concepts ("this margin's background color"), two
unrelated storage/API paths depending on the margin's type. The
foreground side has the same split: `setMarginsForegroundColor` also
sets `STYLE_LINENUMBER`'s foreground, with no getter at all — reading
it back requires the raw message directly:
`editor.SendScintilla(QsciScintilla.SCI_STYLEGETFORE,
QsciScintilla.STYLE_LINENUMBER)` (similarly `SCI_STYLEGETBACK` for the
background, `SCI_GETCARETFORE` for `setCaretForegroundColor`, which
also has no getter). These raw messages return a Scintilla "colour" as
a BGR-ordered int (`0x00BBGGRR` — confirmed directly by round-tripping
a known `QColor`), not RGB — swap byte order when converting back to a
`QColor` for comparison.

If a QScintilla color/style getter doesn't exist or reports something
that doesn't match what was just set, check whether the property in
question is actually backed by a per-margin-type message
(`SCI_SETMARGINBACKN`) versus a named style (`STYLE_LINENUMBER` and
friends, via `SCI_STYLESETFORE`/`BACK`) before assuming the setter
didn't work — `SendScintilla` with the matching `SCI_*GET*` message is
the reliable fallback either way.

## A `WA_DeleteOnClose`, `QAbstractItemView`-based popup (`QListWidget`/`QTreeWidget`) that closes-then-emits can still crash if the receiver shows a modal dialog — closing before emitting isn't the whole fix

`_DeskListPopup` (`desk_picker.py`) already had one fix for this shape
of bug: call `self.close()` *before* emitting its own signal, not
after, because a receiver showing a modal dialog can steal
active-window status, which auto-closes this still-open `Qt.WindowType
.Popup`, and `WA_DeleteOnClose`'s `deleteLater()` then gets processed
by the modal's own nested event loop *while the original method is
still on the call stack* — calling `self.close()` a second time
afterward crashed with "wrapped C/C++ object … has been deleted."

That fix was necessary but not sufficient. Two real, reproduced
segfaults (TODO `4716585`, TODO `8c9436b`) came from a related but
distinct mechanism, confirmed by an identical crashing call chain in
both real macOS crash reports:
`QAbstractItemView::mouseReleaseEvent` -> `QListView::mouseReleaseEvent`
-> `sipQListWidget::mouseReleaseEvent`. The popup's deferred deletion
being processed by a downstream modal dialog's nested event loop — the
exact condition the *first* fix's own comment already described — can
happen *while the native mouse event that triggered the whole chain
hasn't finished being delivered yet* (press and release aren't
guaranteed to be delivered to the same widget without any queued event
in between). If a stale, still-in-flight mouse event for the popup
arrives after that nested loop has already torn it down, it's
delivered to an object that's fully freed or mid-teardown — a genuine
use-after-free/null-deref, not something `self.close()`'s own
double-call guard protects against, since the crash is in Qt's C++
event dispatch, never reaching back into this class's own Python code
at all.

The actual fix: don't let *anything* downstream of this popup's own
signal run synchronously, in the same call stack as the click that
triggered it. Defer the popup's own outgoing re-emission via
`QTimer.singleShot(0, ...)` (`desk.shell.qt_utils.deferred`) at the
point where its *container* (the long-lived, never-destroyed widget
that owns/creates the popup, e.g. `DeskPicker`) re-emits it —
fixed once, at the source, rather than requiring every eventual
receiver to remember to defer its own handling. This applies to *any*
`WA_DeleteOnClose`, `QAbstractItemView`-based popup, not just this one
— `WidgetSpawnMenu` (the only other one in this codebase) got the same
treatment defensively, even though neither of its current handlers
happens to show a modal dialog today. A plain-`QWidget`-with-ordinary
-controls popup (`NewDeskDialog`, `_ItemDialog`, `_AnswerDialog`,
`_PickOverlay`) doesn't have this specific vulnerable code path
(`QAbstractItemView`'s own mouse handling) — no reason to believe the
same fix is needed there absent an actual, confirmed crash report
naming that code path.

## Pressing Tab in a `QGraphicsProxyWidget`-embedded widget can silently hand keyboard focus to an unrelated sibling widget elsewhere on the canvas

Reported (TODO `e69f209`) as "when widgets with carets overlap
visually, sometimes focus seems to switch between them while typing."
Reproduced directly, headlessly, with a real `QGraphicsScene`/
`QGraphicsProxyWidget` (not a guess): two `WidgetFrame`s placed on the
canvas, each wrapping a `QLineEdit`. Typing ordinary characters never
moves focus. Pressing **Tab** does — every time, unconditionally, with
no relationship between the two widgets beyond both being embedded in
the same scene. `QLineEdit` (unlike `QPlainTextEdit`/`QScintilla`,
which consume Tab themselves to insert an actual tab character)
doesn't handle Tab itself, so once its own local search is exhausted,
Qt's default `focusNextPrevChild` chain runs — and for a
`QGraphicsProxyWidget`-embedded widget, that chain doesn't stop at
"this widget's own subtree, nothing else here." It escalates to the
*scene* level and hands keyboard focus to a different sibling
`QGraphicsProxyWidget` item — in this app, a completely unrelated
widget that happens to sit next in the scene's internal item list, not
anything spatially or logically related to the widget just being typed
into. The **visual overlap** in the report isn't a separate
precondition, just what makes the bug legible: the stolen widget's
caret appears in the same screen region the user was just looking at,
reading as "focus flickered" rather than "focus silently jumped to
some unrelated widget," which is the same bug either way — just easier
to notice when the two widgets don't overlap and the caret visibly
teleports across the screen.

**A synchronous fix inside an overridden `focusNextPrevChild` doesn't
work**, confirmed directly — the same non-obvious shape already
documented above for the Lightning Round widget's click-to-focus fix,
one layer removed: `super().focusNextPrevChild()` can return `True`
("handled, nothing to escalate further") and `self.focusWidget()` can
still report the *correct* widget immediately afterward, in the same
call — and the scene's real focus item still ends up on a different
`WidgetFrame` a moment later anyway. `QGraphicsProxyWidget` resolves
which embedded widget actually owns scene-level focus *after*
whatever ran synchronously for the triggering key event, not during
it, exactly like the click-to-focus case — so nothing checked
synchronously inside `focusNextPrevChild` can see (or prevent) the
real outcome.

The fix (`WidgetFrame.focusNextPrevChild`/`_reclaim_focus_if_escaped`
in `src/desk/shell/widget_frame.py`): let the normal `super()` call run
(so cycling between multiple focusable controls *within* the same
widget, e.g. the Stack widget's per-frame fields, still works), then
schedule a `QTimer.singleShot(0, ...)` check for *after* whatever
resolves scene-level focus has actually run. If this widget's own
`QGraphicsProxyWidget` is no longer `scene().focusItem()`, focus
escaped — reclaim it by re-focusing the first (Tab) or last
(Shift+Tab) still-focusable descendant instead of leaving it on the
sibling. If a widget only has one focusable control, this is a
harmless idempotent re-affirm of the same control (which is also what
finally traps the single-control case — an unconditional `return True`
alone, discarding `super()`'s actual side effects, was tried first and
is *not* enough on its own).

General lesson: **any widget embedded via `QGraphicsProxyWidget` that's
meant to behave like an independent floating window (not a tab stop in
some scene-wide sequence) needs to explicitly trap its own Tab/Shift
+Tab focus chain** — Qt has no way to know your app's intent here, and
its default behavior (hand off to the next scene item once a local
chain is exhausted) is exactly backwards for that case. Don't trust a
synchronous check/return value from `focusNextPrevChild` to reflect
what actually happens — verify with `QTimer.singleShot(0, ...)` and a
real embedded `QGraphicsProxyWidget`, the same as any other focus
-resolution timing question in this codebase (see this file's other
`QGraphicsProxyWidget` focus entries).

## `shlex.quote`-ing an entire hand-written-prose blob before typing it into an interactive shell isn't automatically safe just because it's syntactically correct

TODO `624ff3a`: a `claude` widget failed to launch when its initial
prompt had an arbitrary, unbounded chunk of markdown (a `PARKINGLOT.md`
item's full text) appended to it. The command that got typed into the
shell was `exec claude --session-id <uuid> --permission-mode auto
'<prompt>'`, with the *entire* prompt run through `shlex.quote(...)`
first — so this wasn't a case of literally-unescaped shell
metacharacters; the quoting was correct POSIX shell syntax. `shlex.quote`
only guarantees the *shell's parser* sees one inert argument — it says
nothing about an *interactive* shell's other behaviors layered on top of
parsing: bash's default `histexpand` still performs `!`-history
-expansion *inside* an already-single-quoted argument, and the whole
quoted blob is written to the PTY in one `os.write` immediately after
spawning the shell, before there's any guarantee the shell's own
readline has taken over the terminal in raw mode (an early write can
still race the kernel tty layer's canonical-mode line-length limit).
Neither was proven as the exact mechanism here, but both are real gaps
`shlex.quote` alone doesn't close.

Don't treat "the whole string went through `shlex.quote`" as "this is
now safe to type into an interactive shell regardless of size/content."
For anything with unbounded, hand-written prose content (as opposed to
a short, fixed-shape value like a path or an id), prefer keeping what's
typed into the shell short and structurally simple — e.g. a reference
the receiving program can go read for itself (a file path, a line
number) — over splicing the actual content into the command line at
all.
