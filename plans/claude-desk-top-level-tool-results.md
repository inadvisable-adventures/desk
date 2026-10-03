# Claude (Desk) widget: show top-level tool results (TODO `10b4d7d`)

## Summary
Real tool results arrive as top-level `UserMessage`s (`ToolResultBlock`s) which
`ClaudeSession` dropped, so `[tool result]`/`[tool error]` entries never
appeared. Surface them, flatten their (string | list-of-dicts | None) content
readably, and keep any images behind a clickable `[image]` placeholder.

## Affected files
- `src/desk/claude_tool_result.py` (new): `flatten_tool_result`, `ImageAttachment`,
  the image-placeholder sentinel, image persistence helper.
- `src/desk/claude_session.py`: top-level `UserMessage` branch.
- `src/desk/claude_history_view.py`: entries carry `images`, render links.
- `widgets/claude_desk/widget.py`: flatten in `_on_tool_result`, open images.
- `tests/verify/verify_claude_desk_tool_results.py` (new), `TODO.md`.

## Design
- **Session**: a `UserMessage` with list content: each `ToolResultBlock` emits
  the `tool_result` `session_event` and the legacy `tool_result` signal
  (parent id set -> event only, as before). The `AssistantMessage`
  `ToolResultBlock` branch stays but is documented as not occurring on the real
  wire (verified against a live transcript).
- **Flattening** (`flatten_tool_result(content) -> (text, images)`): `None` or
  empty -> `(no output)`; a string verbatim; a list -> text blocks joined by
  newlines, each image block replaced by one sentinel char (U+FFFC) and its
  data kept as an `ImageAttachment(media_type, data | url)`; unknown block types
  become `[<type>]`. A sentinel (not the literal text `[image]`) so a result
  that literally contains "[image]" can't be mistaken for a placeholder;
  `HistoryEntry.plain_text()`/`toPlainText()` render it as `[image]`.
- **Images stay in memory** on the entry (base64 decoded once). A `url` source
  is shown as a link-less `[image: <url>]` -- never fetched.
- **Link**: entries with images render their body as rich text, escaping the
  text and turning the i-th sentinel into `<a href="image:i">[image]</a>`
  (collapsed previews link the placeholders they contain). `linkActivated`
  -> `HistoryView.on_image(entry, i)` -> the widget saves the bytes to
  `.desk_temp/claude_desk_images/<session>/<sha>.<ext>` (idempotent; under
  the disposable, gitignored `.desk_temp`, so no extra cleanup beyond that
  directory's own lifecycle) and opens `image_viewer` on the file via the
  centered widget opener.
- Sub-agent (routed) results use the same flattener but task logs are plain
  dicts over the mediator, so images there degrade to a literal `[image]` --
  noted limitation.

## Verification
Real-shaped `UserMessage`s through `_handle_message` (the gap that let this go
unnoticed), flattener cases, entry rendering/links, image save + opener.
