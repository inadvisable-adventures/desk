# Claude (Desk) widget: fold/collapse tool invocations in the history view (TODO `ed5c62f`) (COMPLETED)

## Summary

`ClaudeDeskWidget._history` (`widgets/claude_desk/widget.py`) is a
single `QPlainTextEdit`; `_on_tool_use`/`_on_tool_result` each append
one line (`_append_history`) with no way to hide it, so a session with
several tool calls — each potentially carrying a large `input`/
`content` payload (a `Write`'s full file contents, a long `Bash`
command's stdout) — makes the transcript hard to scan for the actual
conversation.

Adds real collapsed/expanded folding for tool-invocation entries only
(`[tool]`/`[tool result]`/`[tool error]` lines), collapsed by default:
each such entry becomes a short, always-visible header line (tool
name + a short, single-line preview of the input/content) plus a
"detail" block holding the full text, hidden by default and toggled by
clicking the header. Assistant text, user prompts, permission/error
lines are entirely unchanged.

**Confirmed directly before designing around it** (not assumed):
`QTextBlock.setVisible(False)` + `QTextDocument.markContentsDirty(...)`
genuinely collapses a block to zero height in `QPlainTextEdit`'s own
layout (a small script confirmed `blockBoundingRect(...).height()`
goes from `15.0` to `0.0`), and — critically — doesn't touch the
document's character positions/count at all (`characterCount()` and
every other block's own `position()` were unchanged after hiding).
That second fact is what makes this safe to add on top of the
*existing* `_history_user_entries` reload-hover feature (TODO
`a4c3dec`), which caches absolute character offsets at append time and
never adjusts them afterward — toggling a fold must never be able to
invalidate those.

## Affected files

- **Modified: `widgets/claude_desk/widget.py`** — the only file. No
  other widget/module touches `_history`.
- **New: `tests/verify/verify_claude_desk_history_fold.py`**.

## Design

### What gets folded, and how the header is built

`_truncate_for_header(text: str, max_chars: int = 80) -> str`: returns
`text` unchanged if it's a single line and `len(text) <= max_chars`
(nothing to hide); otherwise returns a truncated, single-line preview
(first line, capped at `max_chars`, `rstrip()`ped) with a trailing
`"…"`. Comparing the return value against the original input is how
callers decide whether there's anything to fold at all — a short,
single-line tool call/result stays exactly as compact as it is today
(a single plain `_append_history` line, no fold affordance, no
behavior change).

`_on_tool_use`: `preview = _truncate_for_header(_format_tool_input(tool_input))`
(empty string if no args); header = `f"[tool] {name}({preview})"`. If
the full formatted args differ from `preview` (there's more to show),
appends as a fold entry (header + the full args as the hidden detail);
otherwise appends the header as a single plain line, unchanged from
today.

`_on_tool_result`: same shape — `f"[{marker}] {preview}"` where
`marker` is `"tool error"`/`"tool result"` as today, folding the full
`content` (coerced to `str`, same as today) as the detail when it
differs from the preview.

### Storage: `_FoldEntry`

```python
@dataclass
class _FoldEntry:
    header_start: int
    header_end: int
    first_detail_block: int
    last_detail_block: int
    expanded: bool = False
```

`header_start`/`header_end` are absolute character offsets, computed
exactly the same way `_append_history` already computes a user line's
own start/end (`end = document.characterCount() - 1; start = end -
len(text)`) — the same established idiom, not a new one.
`first_detail_block`/`last_detail_block` are `QTextBlock` numbers
(stable identifiers once appended — see "Confirmed directly" above),
captured via `document.blockCount()` immediately before and after
appending the detail text (the detail may itself span several blocks,
e.g. multi-line `Write` content or multi-line `Bash` stdout — all of
them get hidden/shown together as one group).

`self._history_fold_entries: list[_FoldEntry]` — appended to, never
reordered/removed (matches `_history_user_entries`'s own append-only
lifetime for the life of one widget instance).

### Toggling: `QTextBlock.setVisible` + a header-only extra-selection tint

`_set_fold_detail_visible(entry, visible)`: walks
`document.findBlockByNumber(entry.first_detail_block)` through
`entry.last_detail_block` via `.next()`, calling `.setVisible(visible)`
on each, then one `document.markContentsDirty(...)` call covering that
whole span (required for `QPlainTextDocumentLayout` to actually redo
line-height layout — confirmed directly, not assumed, per "Confirmed
directly" above), then `self._history.viewport().update()`.

No glyph/prefix is ever inserted into the header's own *text* to show
collapsed-vs-expanded state — deliberately (see "Key design
decisions"). Instead, a collapsed header gets a translucent background
tint via `QTextEdit.ExtraSelection`, the exact mechanism TODO
`78d6207` already established for user-message coloring, cleared when
expanded. Since both features write to `_history.setExtraSelections`
(which always *replaces* its whole argument — same gotcha
`_history_user_selections`'s own existing comment already documents),
both lists get combined through one new shared method,
`_refresh_history_extra_selections()` (`_history_user_selections +
self._history_fold_header_selections`), replacing `_append_history`'s
existing direct `setExtraSelections(self._history_user_selections)`
call.

### Click-to-toggle

Extends the *existing* `eventFilter` (already installed on
`self._history.viewport()` for the reload-hover feature, TODO
`a4c3dec`) rather than adding a second filter: also watches
`MouseButtonPress`/`MouseButtonRelease`. A press records which fold
entry (if any) the press landed on (`_fold_entry_at(pos)`, the same
`cursorForPosition(...).position()` -> linear-scan-for-containing
-range shape `_update_reload_button` already uses for
`_history_user_entries`); a release only actually toggles if it lands
on that *same* entry — guards against a click-and-drag text selection
that happens to start on a header line from being misread as a toggle.
Like the reload-hover handling already does, this **never calls
`event.accept()`/returns `True`** — normal click-drag text selection
inside `_history` (including selecting/copying a header line's own
text) is completely unaffected; the toggle is a side effect of an
ordinary click Qt still processes normally.

### One-time hint

The first time `_append_foldable_history` is ever called on a given
widget instance, it first appends one plain (non-foldable) history
line: `"(tool call/result details are collapsed by default -- click a
line to expand/collapse)"` — discoverability for a UI affordance
nothing else in this widget currently has, shown once per session
rather than every time (a `self._shown_fold_hint: bool` flag).

## Key design decisions

- **No collapsed/expanded glyph (▸/▾) prefixed into the header text
  itself.** Considered it — it's the most standard visual convention
  for this kind of affordance — and rejected it specifically because
  of the reload-hover feature's existing correctness assumption:
  `_history_user_entries` caches *absolute character offsets* at
  append time and is never adjusted afterward. Inserting or removing
  even one character into an *earlier* header's text when its fold is
  toggled would silently invalidate every later-appended entry's own
  cached offsets (both fold entries and reload-hover entries) by
  exactly the size of that edit — a real, demonstrable bug, not a
  theoretical one, since folding can happen interactively at any point
  arbitrarily long after later entries already exist. A translucent
  background tint (a pure `ExtraSelection` overlay, confirmed to never
  touch document text/character count, matching TODO `78d6207`'s own
  established precedent) gets the same "this state differs" signal
  with zero risk to that existing feature.
- **Folding only kicks in when there's actually something to hide.**
  A short, single-line tool call/result (the common case for many
  tools — `Read`, `Glob`, a short `Bash` command) stays exactly as
  compact as it already is today, with no header/detail split and no
  click affordance for something that wouldn't hide anything anyway.
- **Detail blocks are hidden via `QTextBlock.setVisible`, not removed
  or truncated.** `toPlainText()` (confirmed directly) still returns
  the *full* text regardless of fold state — collapsing is a pure
  display-layer decision, so nothing about copy/paste, or any future
  code that reads `_history`'s full text, needs to know folding exists
  at all.
- **Click detection extends the existing `eventFilter`, not a second
  installed filter.** One mouse-event dispatch point for `_history`'s
  viewport, matching how the reload-hover feature already works —
  avoids two independent listeners racing to interpret the same click.

## Verification

`tests/verify/verify_claude_desk_history_fold.py` (a real
`ClaudeDeskWidget` instance, offscreen `QApplication`, no live
session needed — `_on_tool_use`/`_on_tool_result` are called directly,
the same way the widget's own signal handlers would be invoked):

- `_truncate_for_header`: returns the input unchanged for a short
  single-line string; truncates a long single-line string with a
  trailing "…"; truncates a short-but-multi-line string down to its
  first line + "…" even though the first line alone would fit.
- A short tool call (`_on_tool_use` with small `tool_input`) produces
  no fold entry — `_history_fold_entries` stays empty, and
  `_history.toPlainText()` contains the plain, un-split header line
  exactly as before this change.
- A tool call with a large `tool_input` produces exactly one fold
  entry; the detail blocks start `isVisible() == False`; the header's
  own text contains the truncated preview, not the full args; the full
  args are still present somewhere in `toPlainText()` (nothing lost,
  just hidden).
- Same for `_on_tool_result` with a long/multi-line `content`, for
  both the `is_error=True` and `is_error=False` markers.
- Clicking the header (`eventFilter` press+release at a position
  inside `header_start..header_end`) toggles `expanded` and flips the
  detail blocks' `isVisible()`; a second click toggles it back.
- A click-and-drag that *starts* on a header but *releases* elsewhere
  (simulated press at the header, release at an unrelated position)
  does **not** toggle — confirms the press/release-same-entry guard.
- Toggling one entry's fold state leaves every other entry's own
  `header_start`/`header_end` (and, for a real reload-hover entry
  recorded before or after it) numerically unchanged — the concrete
  regression this design was built to prevent, checked directly rather
  than only inferred from the mechanism.
- The one-time hint line appears exactly once in `toPlainText()` even
  after several foldable entries are appended.
- `_history_fold_header_selections` has exactly one entry per
  currently-*collapsed* fold entry, zero for an expanded one.

Full `tests/verify/` regression suite run after, to confirm nothing
else in this widget (reload-hover, background-tasks panel, queueing)
regressed.
