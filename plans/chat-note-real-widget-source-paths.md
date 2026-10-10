# [CHAT] session note names a widget's real source locations (COMPLETED)

TODO `1697645`, from
`../FEEDBACK/FEEDBACK-DESK-chat-button-session-note-wrong-widget-source-location-2026-10-09-1501.md`.

## Summary

`DeskWindow._build_widget_chat_instructions` hardcoded
`widgets/<widget_info.id>/widget.json` and
`widgets/<widget_info.id>/<entry>` in the note's "The code" section.
For a project widget under `desk_widgets/` that directory doesn't exist,
and for a promoted/source-backed `DefineWidget` the id is the PascalCase
keyword while the real source directory is kebab-case, so even swapping
the prefix would still be wrong. The note also presented the compiled
`index.html` as the entry point, though editing build output is silently
undone by the next rebuild.

## Approach

New `DeskWindow._widget_chat_code_paths(widget_info)`, resolving from
what Desk itself loaded rather than guessing from the id:

- **Source-backed custom widget** (`CustomWidgetDefinition.source_path`
  set -- the durable record TODO 13f4ad5 added precisely so nobody
  reconstructs a directory from the keyword): source directory,
  `widget.json`, `widget.html` as the source entry point (with `.ts`/
  `tsconfig.json` beside it), and `.build/index.html` explicitly labelled
  as build output not to edit.
- **Inline `DefineWidget`** (no `source_path`): says there is no editable
  source directory, names the `.desk_temp` DefineWidget file, and labels
  the decoded entry point generated.
- **Everything else** (built-in `widgets/<id>/`, `desk_widgets/<id>/`
  package): `WidgetInfo.path` is already the real directory.

Paths print project-relative when inside the project, absolute
otherwise (a built-in widget lives in Desk's checkout, not the
project's, so a relative `widgets/x` would be wrong for the new session's
cwd).

## Affected files

- `src/desk/shell/window.py` -- new helper, used by
  `_build_widget_chat_instructions`.
- `tests/verify/verify_widget_chat_button.py` -- first test now uses a
  real `desk_widgets/` layout; new cases for the three shapes, including
  the PascalCase-keyword/kebab-directory mismatch the feedback calls out.

## Not done

No tempui changelog entry: this is Desk's own generated note, not
`.desk_temp`'s DSL or Bridge API. The related, static-doc `widgets/` vs.
`desk_widgets/` confusion in
`FEEDBACK-DESK-project-widgets-directory-confusion-2026-09-19-1734.md`
is separate.

## Verification

`verify_widget_chat_button.py`: 31 passed, 0 failed (headless).
