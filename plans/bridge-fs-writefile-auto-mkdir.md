# Plan: TODO ad20867 (COMPLETED) — `desk.fs.writeFile` auto-creates missing parent directories

From `../FEEDBACK/FEEDBACK-DESK-editor-widget-base-types-2026-07-30-1021.md`:
the identical bug — an unguarded `desk.fs.writeFile` to a directory that
doesn't exist yet, which rejects with no visible error — has now shipped
in four separate downstream widgets (Terrain Types Editor, Token Types
Editor, Terrain Color Initializer, Domain Analysis). This is the small,
immediately-high-leverage half of that feedback's suggested fix: close
the root cause once, server-side, with no dependency on any widget
adopting anything new.

## Design

`src/desk/server/app.py`'s `fs_write_file` (the `/api/bridge/fs/writeFile`
handler) currently does a raw `resolved.write_text(body.contents)` with
no directory creation at all. Add `resolved.parent.mkdir(parents=True,
exist_ok=True)` immediately before the write, inside the existing
`try`/`except OSError` block (so a genuine permission error, disk-full,
etc. on the `mkdir` itself still surfaces via the same existing
`HTTPException(400, str(e))` path, not a new/different failure shape).
Idempotent and safe unconditionally — `exist_ok=True` never touches an
already-existing directory, and there's no meaningful case where a
widget author *wants* a write to a missing directory to silently fail
instead of just creating it (the alternative today isn't "a helpful
error," it's total silence).

`fs_read_file` is intentionally untouched — reading a genuinely missing
file is a real, expected error case (nothing to create), unlike writing.

This is independent of, and should land before, TODO `d4368bd`'s shared
document-editor base type — that base type's own auto-save path calls
`desk.fs.writeFile` internally, so once this fix lands, the base type
can never reintroduce the missing-directory bug in the first place,
rather than needing to re-solve it itself.

Document the behavior change in `tempui-custom-widgets.md`'s Bridge API
section (`writeFile` now creates missing parent directories) —
`TEMPUI_DOC_VERSION` bump + a `_NEW_FEATURES_DOC` entry, per
`development-process.md`'s "Keep the tempui changelog docs current" rule.

## Verification

Extend `tests/verify/verify_fs_path_resolution_and_events_doc.py` (already
the home for `fs.writeFile`/`fs.readFile` Bridge route tests — real HTTP
round-trip against a real running server, not mocked, matching its own
existing `test_fs_relative_path_resolves_against_desk_directory`/
`test_fs_absolute_path_used_as_is` shape):

- A real `POST /api/bridge/fs/writeFile` to a path several directory
  levels deep, none of which exist yet, succeeds (`{"ok": true}`) and
  the file is actually readable afterward with the right contents —
  this is the exact failure mode all four cited bugs hit, reproduced
  and confirmed fixed directly, not just inferred from reading the code.
  Existing intermediate directories are left alone (a sibling file
  already there is untouched).
- A write to an existing, already-populated directory is unaffected
  (no regression to the ordinary case).
- `fs_read_file` on a genuinely missing file still returns the existing
  400 error (unchanged) — confirms the fix is scoped to writes only.
- Doc version/changelog bump checks, matching this repo's own existing
  convention for these.
- Full `tests/verify/` regression suite.
