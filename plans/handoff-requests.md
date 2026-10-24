# Cross-project task handoff MCP tools (TODO `e814eaf`) (COMPLETED)

## Summary

Four `desk` MCP tools (create / list / claim / complete a handoff request) over a pluggable `RecordStore`.
Filesystem store now; a document database would implement the same protocol later.

## Affected files

- `src/desk/record_store.py` (new): `Record`, `RecordStore` protocol, `FilesystemRecordStore`, `InMemoryRecordStore`.
- `src/desk/handoff_requests.py` (new): lifecycle (new -> in-progress -> complete), outcomes, filesystem layout.
- `src/desk/shell/desk_mcp_server.py`: four tools, `_handoff_store_factory`.
- `src/desk/temp_ui.py`: tag, changelog entry, `tempui-handoff-requests.md`, link from the overview doc.
- `design-docs/architecture.md`; `tests/verify/verify_handoff_requests.py` (new).

## Approach

1. Store protocol + two implementations; transitions are atomic (`os.rename` on files, a lock in memory).
2. Lifecycle module owns statuses/outcomes and body layout; tools only parse arguments and format results.
3. `directory` argument is relative to the current project (`..` allowed, absolute refused); default `handoff-requests`.
4. Agent-visible docs in the same commit. Verify with both stores, a legacy no-frontmatter file, a concurrent-claim race.

## Status

Verified headless only (no live Claude session exercising the tools).
