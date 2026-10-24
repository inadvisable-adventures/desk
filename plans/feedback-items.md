# Feedback management MCP tools (TODO `540e886`) (COMPLETED)

## Summary

`desk_create_feedback` / `desk_list_feedback` / `desk_get_feedback` over the `RecordStore` from TODO `e814eaf`,
backed for now by `../FEEDBACK/` with its existing naming and placement conventions. Read/create only.

## Affected files

- `src/desk/record_store.py`: `FilesystemRecordStore` takes an optional `codec` and `id_factory`.
- `src/desk/feedback_items.py` (new): statuses/placement, plain-markdown codec, filename scheme.
- `src/desk/shell/desk_mcp_server.py`: three tools; path/store resolution shared with the handoff tools.
- `src/desk/temp_ui.py`: tag, changelog entry, `tempui-feedback-items.md`, overview link.
- `design-docs/architecture.md`; `tests/verify/verify_feedback_items.py` (new).

## Approach

Existing files have no frontmatter, so the codec treats the file text as the body and recovers the title from the
first heading and the timestamp from the filename. New items are written as `# Feedback: <title>` + body. Verify
against a temp `FEEDBACK` tree (open/parkinglot/implemented) and an in-memory store.

## Status

Verified headless only.
