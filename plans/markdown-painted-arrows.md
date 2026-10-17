# Markdown widget painted arrows (COMPLETED)

TODO 333bebf, from `../FEEDBACK/FEEDBACK-DESK-markdown-widget-collapse-arrow-scaling-2026-10-15-1100.md`
and `...-section-toggle-arrow-size-2026-10-15-1130.md`.

## Summary
The Markdown widget's TOC tree branch arrows are native-style painted and detach/oversize under canvas
zoom (same class as TODO b927389). Its section toggle arrows (`setArrowType`) ignore heading level.

## Affected files
`src/desk/shell/painted_branches.py` (new, extracted from Project Files), `widgets/project_files/widget.py`,
`widgets/markdown/widget.py`, `LEARNINGS.md`, `tests/verify/verify_markdown_painted_arrows.py`.

## Approach
1. Extract `_FileTreeView.drawBranches` into shared `PaintedBranchTreeView`/`PaintedBranchTreeWidget`.
2. Markdown TOC uses `PaintedBranchTreeWidget`.
3. Section toggle: painted triangle `QIcon`, `setIconSize` from the level's font height.

## Verification
Headless script above. Live zoomed-out check in real macOS Desk skipped (offscreen can't reproduce native style).
