# Report any GUI-thread exception with its type and message (TODO b89cf17) (COMPLETED)

## Summary

`run_on_gui` and `run_on_gui_async` (`src/desk/server/app.py`) only
translated a few exception types (`RuntimeError`/`KeyError`/`ValueError`
and `RuntimeError`/`TimeoutError` respectively); anything else became a
bare, detail-free 500 (e.g. `introspect.snapshot` against a crashed
widget). Add a final catch-all to each that raises
`HTTPException(500, "<ExceptionType>: <message>")`.

## Affected files

- `src/desk/server/app.py`
- `tests/verify/verify_run_on_gui_any_exception.py` (new)
- `TODO.md`

## Approach

1. Append `except Exception` after the existing specific handlers (order
   matters: the specific mappings must still win).
2. Verify with a stubbed `gui_bridge` window that raises an arbitrary
   exception on both the sync (`fs.writeFile`) and async
   (`transforms.run`) paths.

## Notes

- `run_on_gui_async` deliberately re-raises `ValueError` untouched: the
  `installedJobs/run` route catches it itself to return a 400. (The first
  version of the catch-all swallowed it into a 500 and broke
  `verify_installed_jobs_bridge_api.py`.)

- No tempui changelog entry: no DSL/Bridge API change, only a more
  informative error body.
- `GuiBridge.call`/`call_async` already re-raise arbitrary exceptions
  from the GUI thread, so nothing changed there.
- Browser verification not needed (server-side only).
