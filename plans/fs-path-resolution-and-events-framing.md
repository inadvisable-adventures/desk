# Plan: TODO c892403 (COMPLETED) — desk.fs.* path resolution + events framing

See design-docs/custom-widget-authoring.md section 4 for the full
rationale.

## Summary

Two independent fixes: `desk.fs.readFile`/`writeFile` resolve a relative
path against the server process's ambient working directory (not the
current Desk's own directory), silently writing/reading somewhere the
user never sees; and `tempui-custom-widgets.md`'s Bridge API section
doesn't tell a widget author that `desk.events.*` is usually a much
better fit than `desk.fs.*` for cross-widget signaling until they've
already reached for the wrong one.

## `desk/server/app.py` changes

- New helper (defined after `run_on_gui`, alongside the other route
  closures): `async def _resolve_fs_path(raw_path: str) -> Path` --
  returns `Path(raw_path)` unchanged if already absolute; otherwise
  resolves it against `gui_bridge.window.current_desk.directory`
  (fetched via the existing `run_on_gui` helper, the same GUI-thread
  -crossing convention `workspace_get_state` already uses -- Qt state
  isn't safe to read from the server's own thread directly).
- `fs_read_file`/`fs_write_file`: call `await _resolve_fs_path(...)`
  first, then operate on the resolved `Path` exactly as before. No
  behavior change for an already-absolute path (existing callers that
  happened to pass one keep working identically); a relative path now
  resolves against the right directory instead of wherever the server
  process happened to start.
- `self_get_manifest`: add a `directory` field (the current Desk's own
  directory, as a string) to the returned dict, via the same
  `_resolve_fs_path`-style `run_on_gui` fetch -- lets a widget that
  genuinely needs to construct its own project-relative path do so
  correctly, without needing the `fs` capability just to find out where
  it is.

## Documentation changes

In `_CUSTOM_WIDGETS_DOC`'s Bridge API section:

- `desk.self.getManifest()`'s bullet gains the new `directory` field to
  its description.
- Reorder the "a few more calls" list so `desk.events.*` comes **first**,
  with an explicit callout: most of the other calls in this list are
  single-widget-scoped (read your own file, manage widget instances,
  inspect one specific other widget) -- `events` is the one built for
  "tell other widgets something happened," and should be reached for
  first whenever that's the actual goal.
- `desk.fs.readFile`/`writeFile`'s bullet documents the new resolution
  behavior: a relative path resolves against the current Desk's own
  directory (not any particular working directory), and an absolute
  path is used as-is.

Bump `TEMPUI_DOC_VERSION` by 1.

## Verification

- `_resolve_fs_path`: absolute path returned unchanged (no GUI-thread
  call at all needed -- verify it doesn't even attempt one, e.g. with
  `gui_bridge=None` and an absolute path still succeeding); relative
  path resolves against a fake window's `current_desk.directory`.
- `fs_read_file`/`fs_write_file` end-to-end through a real `TestClient`
  (FastAPI's `httpx`-backed test client, already a `fastapi` dependency
  so this doesn't add a new one) with a real `GuiBridge` wired to a
  minimal fake window double: writing a relative path lands under the
  fake Desk's directory; an absolute path lands exactly where given.
- `self_get_manifest` includes the correct `directory` string.
- Doc: confirm the reordering, the callout text, and the version bump.
- Full scratchpad regression suite (`git stash` before/after).
