# Rotating file log for Desk's own logging (TODO aa0ce76) (COMPLETED)

## Summary

`src/desk/app.py` only calls `logging.basicConfig(...)` to stderr, so a
traceback or warning is lost unless it happened to be visible in whatever
terminal launched Desk, and there is no documented place to look. Add a
rotating file log. Cites
`../FEEDBACK/FEEDBACK-DESK-html-widget-getusermedia-crash-2026-09-11-1735.md`
(suggested fix 3).

## Affected files

- `src/desk/logging_setup.py` -- new: `log_path()` and
  `configure_logging()`.
- `src/desk/app.py` -- replace the bare `basicConfig` with
  `configure_logging()`, and log the log-file path at startup.
- `src/desk/crash_handler.py` -- also record an uncaught exception's
  traceback in the log (additive, inside its existing broad try/except).
- `design-docs/architecture.md` -- a short "Logging" note naming the path.
- `tests/verify/verify_rotating_file_log.py` -- new.

## Approach

1. Location: `~/.desk/logs/desk.log`, next to `~/.desk/recent_desks.json`
   (Desk-wide, not per-project, since the process is not tied to one
   project). `configure_logging(log_dir=None)` takes an override for tests.
2. Stdlib `logging.handlers.RotatingFileHandler` (no new dependency), 1 MB
   per file, 5 backups, UTF-8, format with a timestamp
   (`%(asctime)s %(levelname)s %(name)s: %(message)s`).
3. Keep the existing stderr handler and INFO level. Idempotent: calling it
   twice never adds a second handler of either kind.
4. Best-effort: if the log directory cannot be created or opened, fall
   back to stderr-only and log a warning -- logging setup must never stop
   Desk from starting.
5. `crash_handler._handle_exception` additionally calls
   `logging.getLogger("desk").critical("Uncaught exception", exc_info=...)`
   so the traceback also lands in the rotating log, still never raising.
6. Not a tempui DSL/Bridge API change; no tempui changelog entry.

## Verification

New script using a temp directory as `log_dir`: the file is created and
receives a record with a timestamp; `configure_logging` twice yields one
file handler and one stream handler; rotation happens (tiny `maxBytes`
override produces `.1` backups and never more than the backup count); an
unwritable location falls back without raising; the crash handler's
uncaught-exception path writes the traceback to the log. Re-run existing
crash-handler verify scripts. No browser launch needed.

## Status

Implemented as planned. Verified with the new script plus the existing
`verify_crash_handler.py` and `verify_crash_log.py`. The feedback file
stays in `../FEEDBACK/` because TODOs 2dbfd55, b89cf17 and 5abf5a0 from the
same report are still open. Browser launch not needed.

## Revision (per user request): per-project log under `.desk_temp/logs/`

The log moved from `~/.desk/logs/desk.log` to
`<project>/.desk_temp/logs/desk.log`: each Desk instance (project
directory) keeps its own local log, and agents may read it.

- `configure_logging()` is now stderr-only and runs at import time;
  `set_log_directory(temp_dir)` attaches/re-points the rotating file
  handler (closing the previous one) and is called from
  `DeskWindow._provision_temp_ui`, i.e. at startup and on every Desk switch.
- It is called *after* `TempUiManager.provision`, and never creates
  `.desk_temp`: provision treats an existing `.desk_temp` as consent (it
  skips the "create it?" prompt and seeds the docs), so pre-creating it for
  logs would bypass that consent. A declined `.desk_temp` means stderr-only.
- Known limitation: records emitted before the first provisioning (a few
  startup lines) reach stderr only.
- `.desk_temp/` is already gitignored by the provisioning flow.
- Verification: `verify_rotating_file_log.py` rewritten for the new API
  (per-instance logs, switching, detach, no `.desk_temp` creation, rotation,
  fallback, crash-handler path) plus a wiring check on
  `_provision_temp_ui`. Full `tests/verify/` sweep re-run.
