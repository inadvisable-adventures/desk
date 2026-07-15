# Plan: TODO 2da314f (COMPLETED) — expose open-editor-or-scrap over the Bridge API

## Summary

TODO da4f9c0 built `DeskWindow.open_editor_or_scrap` and a
`current_context` hook for `kind: "python"` widgets. Expose the same
service to `kind: "html"` widgets over the real HTTP Bridge API, so
either widget kind can reach it -- exposing an existing service through
a second binding mechanism, not building new fallback logic.

## Bridge API (`src/desk/server/app.py`)

- New capability string: `"editor"`.
- New request model: `class OpenEditorOrScrapRequest(BaseModel): path: str`.
- `POST /api/bridge/editor/openOrScrap` (`require_caller("editor")`):
  resolves `body.path` the same way `desk.fs.*` already does (TODO
  c892403's `_resolve_fs_path` -- a relative path resolves against the
  current Desk's own directory, an absolute path is used as-is), then
  `await run_on_gui(lambda: gui_bridge.window.open_editor_or_scrap
  (resolved))`. Returns `{"ok": True}`.
- `bridge_client.py`'s `BRIDGE_CLIENT_TEMPLATE` gains an `editor`
  namespace: `openOrScrap: (path) => call("POST",
  "/api/bridge/editor/openOrScrap", { path })`.

## Docs

Add this new capability to `_CUSTOM_WIDGETS_DOC`'s Bridge API
capability list (`tempui-custom-widgets.md`), bump
`TEMPUI_DOC_VERSION`, and -- per TODO 1a96c9f's own new instruction in
`development-process.md`'s "When working on Desk itself" section --
add a corresponding entry to `tempui-new-features.md` in the same
commit as the bump, the first real exercise of that convention.

## Verification

- Over real HTTP (a running server + a real `GuiBridge` attached to a
  fake window double, the established pumped-event-loop pattern):
  `POST /api/bridge/editor/openOrScrap` with a relative path resolves
  against the fake Desk's directory and calls `open_editor_or_scrap`
  with the resolved path; an absolute path is used as-is; a caller
  lacking the `editor` capability gets a 403.
- `bridge_client.py` declares the new `editor.openOrScrap` call.
- Doc: the new capability is listed, `TEMPUI_DOC_VERSION` bumped, and
  `tempui-new-features.md` has a corresponding entry.
- Full scratchpad regression suite (`git stash` before/after).
