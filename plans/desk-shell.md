# Desk Shell (COMPLETED)

## Summary

Build the PyQt6 Desk Shell described in `design-docs/architecture.md`: a
`QMainWindow` hosting a single `QWebEngineView` that loads the Local Web
Server (TODO 2) at startup, using the per-launch token from
`start_server()`. This replaces the temporary "block on signal" loop added
in TODO 2's `desk.app.main()` with the Qt application owning process
lifetime: the Qt event loop runs until the window is closed, and closing the
window stops the local web server cleanly. No Workspace SPA content exists
yet (TODO 4), so the window will simply show today's static placeholder
page from TODO 2 — this item is only about the Shell/server wiring and
lifecycle.

## Affected files

- `src/desk/shell/__init__.py` (new) — package marker.
- `src/desk/shell/window.py` (new) — `DeskWindow(QMainWindow)`: constructs a
  `QWebEngineView`, sets it as the central widget, loads a given URL, sets a
  reasonable default size/title.
- `src/desk/app.py` (edit) — `main()` now: starts the server (as before),
  constructs a `QApplication`, constructs `DeskWindow` loading
  `handle.url`, connects `QApplication.aboutToQuit` to `handle.stop()`,
  calls `window.show()`, and runs `app.exec()` instead of blocking on a
  `threading.Event`. Drop the manual `SIGINT`/`SIGTERM` handling — Qt's
  window-close (and Cmd+Q on macOS) becomes the normal way to exit; closing
  the last window quits the app (`QApplication.setQuitOnLastWindowClosed`,
  which is the PyQt6 default).

## Implementation approach

1. `shell/window.py`: `DeskWindow.__init__(self, url: str)` creates a
   `QWebEngineView`, calls `.load(QUrl(url))`, sets it as
   `setCentralWidget`, sets `setWindowTitle("Desk")` and a default size
   (e.g. 1280x800) via `resize()`.
2. `app.py`: import `QApplication` from `PyQt6.QtWidgets` and `DeskWindow`
   from `desk.shell.window`. In `main()`:
   - start the server as before, log the URL.
   - `app = QApplication(sys.argv)`.
   - `window = DeskWindow(handle.url)`; `window.show()`.
   - `app.aboutToQuit.connect(handle.stop)` so the server always stops when
     Qt decides to quit, regardless of what triggered it.
   - `return app.exec()`.
3. Remove the now-unused `signal`/`threading.Event` wiring from TODO 2 (it
   served as a stand-in for "something owns process lifetime" until the Qt
   event loop could take over).

## Verification

1. `python -m desk` opens a native window titled "Desk" showing the
   placeholder "Desk server is running." page (proves the `QWebEngineView`
   successfully loaded content from the local server, including the token
   query param round-tripping correctly).
2. Closing the window quits the process; confirm (via the shell) that the
   process exits and the bound port is no longer accepting connections
   (i.e. the server actually stopped, not just the window closing).
3. This step requires actually opening a window, so per
   `development-process.md` step 5, the interactive "look at the window"
   part is done via a screenshot/visual check rather than a headless
   script; the "does closing it clean up the server" part is scriptable
   and will be checked directly.

### Status (verification notes)

- `python -m desk` was run directly (not backgrounded via the harness) and
  confirmed via `ps` to launch a live process, and via the macOS menu bar
  (screenshot) to become the active foreground GUI app. A
  `QtWebEngineProcess` renderer subprocess (from this project's own venv)
  was also confirmed running, which only happens once `QWebEngineView`
  actually starts loading a URL.
- A full-screen screenshot did not show the window contents (only desktop
  wallpaper was visible, despite "Python" being the active app in the menu
  bar) — this environment's screen-capture path does not appear to reliably
  composite this app's window, so the literal "look at the rendered page"
  visual check is **skipped** per `development-process.md` step 5 — worth
  re-checking manually outside this environment if there's ever doubt.
- The lifecycle/shutdown behavior *was* verified end-to-end without relying
  on the screenshot: sent the app a `quit` Apple Event (equivalent to
  Cmd+Q/closing the app), then confirmed via `ps` that the process exited
  and via `curl` that the local server's port stopped accepting connections
  — i.e. `aboutToQuit` correctly stopped the server on shutdown.

## Key design decisions / tradeoffs

- **Qt event loop owns process lifetime, not the reverse.** Now that there's
  a real window, `app.exec()` is the natural blocking call; the manual
  signal-handling loop from TODO 2 was explicitly called out there as a
  temporary stand-in for this.
- **Single `QWebEngineView` filling the whole window, no native menu bar
  yet.** Matches the "Workspace SPA renders everything" model from the
  design doc — native chrome (menus, tray icon) is deferred until there's a
  concrete need for it; nothing here precludes adding a `QMenuBar` later.
- **Token passed via the loaded URL's query string, not `QWebChannel`.**
  Consistent with the design doc's decision to keep the Bridge API as
  plain REST/WebSocket rather than `QWebChannel` — the Shell doesn't need
  any special Qt-side bridge to get the token to the page; it's just the
  URL it navigates to.
