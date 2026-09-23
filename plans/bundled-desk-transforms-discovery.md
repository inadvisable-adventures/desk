# Discover Desk's own bundled desk_transforms/ (TODO 05f2222) (COMPLETED)

## Summary

`desk.transforms.discover_transforms_with_errors` only scans the
current project's `.desk_temp/transforms/` and `desk_transforms/` --
Desk's own two built-in transforms (`mermaid_flowchart_svg`,
`mermaid_state_svg`, which the Markdown widget's Mermaid rendering
already depends on unconditionally) physically live in *this* repo's
own `desk_transforms/`, which is only "the current project" when the
current project happens to be Desk's own dogfood checkout. Any other
project has neither directory, so Mermaid rendering fails there with
no project-level fix short of manually copying two directories out of
Desk's own source tree -- confirmed directly, and explicitly not asking
for auto-scaffolding (copying them into the project) since that would
break "a brand-new project ends up with nothing it didn't specifically
ask for." Cites
`../FEEDBACK/FEEDBACK-DESK-mermaid-rendering-fails-silently-without-project-transforms-2026-09-18-2000.md`
(suggestions 2 and 3).

## Approach

A third, lowest-precedence discovery location: Desk's own installed
`desk_transforms/` directory, resolved relative to `transforms.py`
itself (`Path(__file__).resolve().parents[2] / PROJECT_TRANSFORMS_DIRNAME`
-- the exact pattern `temp_ui._repo_shared_components_dir` already
uses), scanned *first* so a project's own same-id transform still wins
-- mirrors the existing `desk_temp` < `project` precedence
(`discover_transforms_with_errors`'s own docstring: "the promoted/
authoritative location takes precedence over the local scratch copy"),
now `bundled` < `desk_temp` < `project`. Nothing is ever copied into
the project; the bundled directory is scanned in place, every time.

- `TransformInfo.location` gains `"bundled"` alongside `"desk_temp"`/
  `"project"`. The existing "no Python in `.desk_temp`" restriction is
  untouched -- it checks `location == "desk_temp"` specifically, and a
  bundled transform is first-party Desk code, the same trust level as
  a project's own committed `desk_transforms/` (`location == "project"`
  already allows Python).
- Transform Manager widget: a third display label ("Bundled with
  Desk"), and no Promote button for it (unaffected -- the button only
  ever shows for `location == "desk_temp"`, since there is nothing to
  move for a transform that was never in this project's own
  `.desk_temp` to begin with).
- No caller-facing signature change: `discover`/
  `discover_transforms_with_errors` still take exactly
  `(desk_temp_dir, project_dir)` -- the bundled directory is a fixed
  constant, not something that varies per project, so every existing
  call site (`DeskWindow._refresh_transforms`,
  `TransformManagerWidget.refresh`) is unaffected.
- Docs: `tempui-markdown.md`'s "Supported Mermaid subset" section
  (added by TODO 9fe03a1) is corrected -- Mermaid rendering now works
  in every project with nothing copied into it, so its "no transform
  found in this project" note becomes the rare case (a non-source/
  frozen install with no bundled `desk_transforms/`, or a project
  deliberately missing/overriding it), not the default expectation.
  `desk-temporary-ui.md`'s overview gets the same one-line correction
  wherever it already implies a project needs its own transform.
  `design-docs/transforms.md`'s "Storage & discovery" section
  documents the third location and the full precedence order. New
  tempui changelog tag + `_NEW_FEATURES` entry.

## Affected files

- `src/desk/transforms.py` -- `_repo_desk_transforms_dir`,
  `discover_transforms_with_errors`, `TransformInfo.location`'s comment.
- `widgets/transform_manager/widget.py` -- three-way location label.
- `src/desk/temp_ui.py` -- `_MARKDOWN_DOC`, `DOC_TEMPLATE` (if it
  mentions the dependency), tag, `_NEW_FEATURES`.
- `design-docs/transforms.md` -- "Storage & discovery" section.
- `tests/verify/verify_transforms_service.py` (or a new
  `verify_transforms_bundled_discovery.py`) -- new coverage; update
  anything asserting exactly two locations.

## Verification

Real filesystem, no mocks: `discover_transforms_with_errors` finds
`mermaid_flowchart_svg`/`mermaid_state_svg` from Desk's own real
`desk_transforms/` even when both `desk_temp_dir`/`project_dir` are
empty temp directories (the actual fix, proven against the repo's own
real bundled transforms, not a synthetic stand-in); a project's own
same-id transform overrides the bundled one; a `.desk_temp`-located
same-id transform overrides bundled but is overridden by the project's
own; `location="bundled"` on the discovered `TransformInfo`; a Python
`kind` is allowed at the bundled location (unlike `desk_temp`). Markdown
widget real end-to-end: `_build_mermaid_widget` renders a real SVG with
*no* `desk_transforms/`/`.desk_temp/transforms/` copied into the temp
project at all (this is the actual bug from the FEEDBACK report,
reproduced and fixed) -- update/extend
`verify_markdown_mermaid_transforms.py`'s own
`test_real_end_to_end_via_a_real_transforms_service` and
`test_missing_transform_names_what_is_missing` (the latter's premise --
"nothing discovered" -- no longer holds for Mermaid specifically once
bundled discovery exists; needs a project excluding/shadowing it
instead, or dropping down to a still-genuinely-undiscoverable transform
id). Transform Manager widget: real `TransformManagerWidget`, a bundled
row shows "Bundled with Desk" and no Promote button. Doc/tag checks.
Full `tests/verify/` sweep. No browser launch needed.

## Status

Implemented as planned, no deviations from the design. Also documented
in `desk-temporary-ui.md`'s own overview (the `OpenMarkdown`/`Markdown`
bullet now notes Mermaid works out of the box), completing all three
files the TODO named.

Verified: extended `verify_transform_discovery.py` (bundled discovery
with no project directories at all, project/`.desk_temp` each
overriding a bundled transform, nonexistent/None-directory tests
updated for the new baseline of two always-present bundled transforms),
`verify_transform_manager_widget.py` (a bundled row's "Bundled with
Desk" label and missing Promote button; two existing tests' expected
row counts corrected for the same new baseline), and
`verify_markdown_mermaid_transforms.py` (the actual bug, fixed and
proven: a real `TransformsService` discovering from a genuinely empty
project renders both Mermaid diagram kinds with nothing copied in at
all; a project's own override still wins; the pre-existing "missing
transform" test moved to a fake-runner unit test, since
`mermaid_flowchart_svg`/`mermaid_state_svg` specifically can no longer
be made genuinely undiscoverable -- which is the fix working as
intended, not a gap in coverage). All three files' new/changed tests
run twice for flakiness. Full `tests/verify/` sweep (159 scripts)
passes. Browser launch not needed.

Both feedback files this and TODO 9fe03a1 cite are now fully resolved
(every citing TODO item complete, no open PARKINGLOT.md entries) --
moved
`../FEEDBACK/FEEDBACK-DESK-mermaid-rendering-fails-silently-without-project-transforms-2026-09-18-2000.md`
to `../FEEDBACK/implemented/`.
