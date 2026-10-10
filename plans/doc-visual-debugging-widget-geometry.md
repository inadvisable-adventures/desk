# Teach visual debugging of widget geometry in tempui-custom-widgets.md (COMPLETED)

TODO `b9c7828`, from
`../FEEDBACK/FEEDBACK-DESK-visual-debugging-techniques-for-widget-geometry-bugs-2026-10-09-1606.md`.

## Summary

The feedback is a worked example: a canvas widget's hit-testing was
offset, two plausible guesses failed, and a build marker plus a
hit-test trace layer with ground-truth crosshairs (drawn via the same
projection function that renders) found the real cause --
`isPointInPath()`'s query point not being subject to the current
transform -- in one screenshot round. It asks that the technique be a
named pattern in `tempui-custom-widgets.md`.

## Approach

- New section "Debugging a widget's own rendering/geometry visually" in
  `_CUSTOM_WIDGETS_DOC` (`src/desk/temp_ui.py`), right after "Authoring
  from real source": the four pieces (build marker; real-outcome debug
  layer; ground-truth markers via the same function; agent closes the
  loop with `desk_screenshot_widget`/`desk_reveal_widget`) plus the
  `isPointInPath` worked example.
- Per the development process, a guidance change counts as a feature:
  minted tag `visual debugging of widget geometry guidance #733899`,
  added to `CURRENT_TAGS` and `_NEW_FEATURES`.
- The doc states honestly that there is currently no way to synthesize
  pointer/keyboard events against a placed widget.

## Affected files

- `src/desk/temp_ui.py`
- `tests/verify/verify_tempui_visual_debugging_doc.py` (new)

## Parked, not done here

The feedback's smaller second suggestion -- a `deskproc`-style
`synthesize_pointer_event(instance_id, ...)` so an agent can drive the
interaction as well as observe it -- is a real feature needing design,
so it is a `PARKINGLOT.md` entry. Its feedback file therefore stays in
`../FEEDBACK/` until that entry is resolved.

## Verification

`verify_tempui_visual_debugging_doc.py` (10 checks), plus the existing
`verify_tempui_changelog_docs.py`, `verify_tempui_custom_widgets.py`,
`verify_tempui_doc_versioning.py`,
`verify_tempui_doc_upgrade_notification.py` and
`verify_tempui_subjective_visual_callout.py` all pass.
