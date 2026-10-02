# Claude (Desk) widget: structured per-entry history (TODO `dffb428`) (COMPLETED)

## Summary

Replace the widget's single `QPlainTextEdit` history (everything appended
as bracket-prefixed text; user coloring, tool folds and hover reload done
as extra-selection overlays keyed on character offsets) with a scroll area
of individually framed entries, each carrying metadata from the
`session_event` stream (TODO `20ca851`) and collapsible by default when
long, for every entry type.

## Affected files

- `src/desk/claude_history_view.py` (new): `HistoryView`, `HistoryEntry`,
  `collapse_preview`. In `desk.` proper because widget modules are loaded
  by path and can't import siblings.
- `widgets/claude_desk/widget.py`: uses `HistoryView`; removes the fold /
  user-selection / reload-hover machinery; adds `_on_session_event`.
- `tests/verify/`: `verify_claude_desk_history_fold.py` rewritten,
  new `verify_claude_desk_structured_history.py`, history-overlay checks
  removed from `verify_claude_desk_widget.py`, fake session in
  `verify_widget_chat_button.py` gains `session_event`.
- `design-docs/architecture.md` item 30, `TODO.md`.

## Design decisions

- **One framed widget per entry**, header row (fold toggle + kind tag,
  turn/time/source label, reload button for user entries) over a
  selectable body label. Chrome labels are not selectable (CLAUDE.md);
  bodies are (they are content).
- **Collapse by default for every kind**: tool kinds keep the original
  one-line/80-char rule; everything else collapses past 4 lines or 400
  chars to its first 3 lines. Short entries show no fold affordance.
- **Separation**: a heavy top rule marks a turn start (user prompts, and
  the first entry of an unsolicited turn); ordinary entries get a light
  rule. Background tint/left bar by kind (alpha colors, theme-neutral).
- **Provenance**: `session_event` is emitted immediately before the legacy
  signal for the same message, so the widget records the latest event and
  the legacy handler renders with its turn id / `unsolicited` source. User
  entries get their turn id when `turn_started` arrives (FIFO). Other
  entries (permission, question) attach to the in-flight turn.
  An unsolicited `turn_complete` doesn't clear the active turn.
- **Tradeoff**: text selection can't span entries; a "Copy all history"
  context action covers whole-history copy. `toPlainText()` keeps the old
  bracket-prefixed format.
- The one-time fold hint line is dropped; the visible ▸/▾ arrow replaces it.
- Task events still go to their own list; the structured history gives
  them no entries by construction, and provenance now makes that checkable.

## Verification

All `tests/verify/` scripts pass; offscreen screenshot reviewed. Live
browser/desktop run skipped (no GUI session). This plan was written after
the implementation rather than before it -- an ordering slip against the
process doc, noted here.
