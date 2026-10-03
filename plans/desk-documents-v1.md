# `desk.documents` v1: virtualized, Desk-cached reads (TODO `8e4711e`) (COMPLETED)

## Summary
`desk.documents.open(path)` -> handle; `.read(handle, {offset, length})` ->
`{data: base64, eof}` (raw, binary-safe byte ranges); `.close(handle)`. Reads are
cached Desk-side under `.desk_temp/`, keyed by `(path, mtime, size)`, so repeats
don't re-hit disk and a changed file invalidates instead of serving stale bytes.
For `kind: "html"` widgets (Bridge API) and `kind: "python"` widgets.

## Affected files
- `src/desk_services/documents/{__init__,service}.py` (new): Qt-free, thread-safe.
- `src/desk/server/app.py`: `/api/bridge/documents/{open,read,close}`.
- `src/desk/server/bridge_client.py`: `desk.documents.*` JS.
- `src/desk/shell/window.py` + `current_context.py`: service wiring for python
  widgets (`get_documents_service`).
- `src/desk/temp_ui.py`: new capability documented, changelog tag + entry.
- `tests/verify/verify_documents_service.py`, `verify_documents_bridge_api.py`.

## Design
- **Handles** are server-side random ids mapped to a resolved path plus the
  opening widget instance; content is not read at `open` (the file must exist
  and be a regular file). A relative path resolves against the current Desk's
  directory, like `desk.fs.*`. At most 256 handles are live (oldest dropped) so
  a widget that never closes can't leak without bound. A bad/closed handle is a
  clear error.
- **read**: `offset >= 0`, `length` clamped to 8 MiB per call; reading at or past
  the end returns `{data: "", eof: true}`; `eof` is true when the returned range
  reaches the file's current end. Binary-safe from the start (raw bytes,
  base64 over the wire; `desk.fs.readFile` decodes UTF-8 and throws on binary).
- **Cache** (on disk under `<desk dir>/.desk_temp/documents_cache/<key>/`, where
  `key = sha1(path|mtime_ns|size)`): one file per distinct `(offset, length)`
  range, written atomically. Every read stats the file first; a different
  `(mtime_ns, size)` yields a different key (so stale bytes are never served)
  and the previous key's directory for that path is deleted. Each document's
  cache is bounded to 64 MiB (oldest-by-mtime entries evicted). No format
  awareness in v1 -- raw ranges only; editing and live change notifications
  (v2) stay parked in `PARKINGLOT.md`.
- **Capability** `documents` (a new coarse string; manifests/tempui widgets
  declare it like `fs`).
- **Python widgets** reach the same singleton via
  `current_context.get_documents_service()` (Qt-free, so synchronous calls are
  fine for ranges this size).
- Tempui changelog: new tag + `_NEW_FEATURES` entry; the Bridge API list in the
  tempui docs gains `desk.documents.*`.

## Verification
Service unit tests (ranges, eof, binary bytes, clamp, cache hit without disk,
invalidation on mtime/size change with old dir removed, close, bad handle,
handle cap, cache bound, relative resolve) and an HTTP-level test through the
real server (`start_server`) like the `desk.fs` path-resolution script.
