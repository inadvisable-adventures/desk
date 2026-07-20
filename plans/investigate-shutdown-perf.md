# Plan: TODO 9d1544b (COMPLETED) — investigate shutdown performance

Create a new top-level `./investigations/` directory and a
`shutdown_perf.md` document there, investigating why Desk's shutdown
might take a long time, with recommendations. No application code
changes — a pure investigation, written up for a future Claude instance
(or the user) to act on.

## Approach

1. Trace the actual shutdown path end-to-end: `src/desk/app.py`'s
   `QApplication.aboutToQuit`-connected handlers (in connection order:
   `WidgetWatcher.stop`, `ServerHandle.stop`, `DeskWindow
   .save_current_desk`, `FileWatcherService.stop`), and what happens
   *after* `app.exec()` returns — Qt's own widget-tree destruction
   cascade at process-teardown time, which is where per-widget
   `destroyed`-signal-connected cleanup (`TerminalWidget
   ._cleanup_resources`, used by the Console and Claude widgets) runs.
2. For each candidate with a timeout/blocking wait, don't just read the
   code and speculate — measure it directly with a real, isolated
   repro (a real subprocess, a real HTTP long-poll against a real
   running server, a real `watchdog` Observer), distinguishing
   "confirmed by direct measurement" from "plausible but not measured."
3. Write `investigations/shutdown_perf.md` with: what was investigated,
   what was found (root-caused, with the exact mechanism and numbers),
   and concrete, actionable recommendations ranked by expected impact.

## Verification

No application code changes, so no new `tests/verify/` script. Confirm
the new file exists and the full regression suite still passes
(nothing should have changed, but check anyway per the standard
process).
