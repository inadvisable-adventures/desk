# Claude (Desk) history: "Markdown View" hover button on agent-turn items (TODO `6ff3be8`) (COMPLETED)

## Summary
A right-aligned hover button on each `assistant` history entry that renders the
whole turn to a markdown file and opens it in the Markdown widget, with real
images.

## Affected files
- `src/desk/claude_turn_markdown.py` (new): pure turn -> markdown rendering.
- `src/desk/claude_history_view.py`: `on_markdown` callback + hover button.
- `widgets/claude_desk/widget.py`: gather the turn's entries, write files, open.
- `tests/verify/verify_claude_desk_markdown_view.py` (new), `TODO.md`,
  `design-docs/architecture.md`.

## Decisions
- **"Agent-turn item"** = an `assistant` entry; **"that turn"** = every entry
  sharing its `turn_id` (user prompt, assistant text, tool calls, results,
  errors), in order -- the TODO's recommended default. The prompt is included
  as a leading blockquote for context since it carries the same turn id. An
  entry with no turn id (direct/unit use) renders alone.
- **Format**: `# Turn N` plus the local time; the prompt as a blockquote;
  assistant text as-is (it is already markdown); each tool call as a
  `**Tool**` line plus a fenced block; each result as `**Result**`/`**Error**`
  plus a fenced block, the fence one backtick longer than any run inside the
  text. A result's images break the fence and are emitted as
  `![image](images/<hash>.<ext>)` between the fenced text segments, so they
  render. A result image with no bytes (url source) is a plain link.
- **Files**: `.desk_temp/claude_desk_turns/<session>/turn-<id>.md`, images in
  an `images/` subdirectory next to it, written via `save_image` (TODO
  `10b4d7d`). The markdown widget resolves relative image paths against the
  file's directory (markdown-rendering.md). `.desk_temp` is disposable and
  gitignored, so no extra cleanup; the file is overwritten per click so a
  re-click shows the turn as it now stands. A new viewer opens per click (the
  centered opener returns the widget, not an instance id, so there is no
  zoom-to-existing as the task-log widget has). SVG images would need the Image
  Viewer, as markdown-rendering.md notes -- noted, not handled.
- Button placement: in the header row, right-aligned beside the reload button
  (assistant entries never have reload, so they never both show). Hover-revealed
  like the reload button; `enterEvent`/`leaveEvent`.

## Verification
Renderer unit checks (fences, images, prompt, ordering, backtick safety);
entry button visibility/callback; widget gathering by turn id, file contents,
opener call. Whole suite.
