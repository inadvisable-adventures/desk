# Plan: TODO 06fa070 (COMPLETED) — investigate `disabled_verify_bridge_api_editor_or_scrap.py`

## Investigation

The only failing assertion is `check("TEMPUI_DOC_VERSION bumped to 16",
TEMPUI_DOC_VERSION == 16)` (line 191) — a hardcoded exact version number
from when this script was written (TODO `2da314f`, doc version 16 at
the time). `TEMPUI_DOC_VERSION` has since bumped to 17 (TODO `029047b`)
for an unrelated reason (moving `build_widget.py` into `.desk_temp`) —
nothing about this script's own subject (the `editor.openOrScrap`
Bridge API route) changed or regressed.

## Resolution

Fix it: loosen the assertion to `TEMPUI_DOC_VERSION >= 16` (this
script's own subject only cares that the version was bumped *at least*
once for its own change, not the exact current number, which will keep
moving for unrelated reasons forever) rather than deleting or rewriting
the whole script — every other check in it still reflects real,
current behavior.

## Verification

Re-run the script standalone (passes); re-run the full
`tests/verify/` suite and confirm the failing set drops from 17 to 16
with no new failures.
