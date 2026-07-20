# Plan: TODO 1c7d5b9 — split SVG Editor's Hex Preview into flat-top/pointy-top buttons

Follow-up to TODO `d1d176f` (the original hex preview mask). The single
`"Hex Preview"` toggle only ever built a pointy-top hexagon
(`_hexagon_path`'s `60*i - 90` angle offset, hardcoded). Splitting into
two buttons — flat-top and pointy-top hex tiles are both real,
distinct conventions (`necro-4x`'s own consumer could plausibly use
either) — mutually exclusive with each other, but **neither selected
is also a valid state** (the mask can be off entirely, as it already
could be).

## Design

Not a `QButtonGroup(exclusive=True)` — that enforces "at most one
checked" but its exact behavior around manually unchecking the
currently-checked button (clicking it again) isn't something to lean
on without verifying, and explicit control is simpler to reason about
and test directly anyway. Two independent checkable `QPushButton`s,
each wired to a single state-setting method that keeps both buttons'
checked state in sync with the actual state:

- `self._hex_preview_orientation: str | None` replaces
  `self._hex_preview_enabled: bool` — `None` (off), `"flat"`, or
  `"pointy"`.
- `self._hex_preview_flat_button`/`self._hex_preview_pointy_button`
  (both `setCheckable(True)`), each `clicked.connect`ed to a lambda
  calling `self._set_hex_preview_orientation("flat"/"pointy" if
  checked else None)` — `clicked(checked)` already reports the
  button's own just-toggled state, so clicking a checked button again
  naturally reports `checked=False`, giving "neither" for free.
- `_set_hex_preview_orientation(orientation)`: stores it, then calls
  `setChecked(...)` on *both* buttons to match (`.setChecked()` doesn't
  re-emit `clicked`, only `toggled` — connecting to `clicked` specifically
  avoids any feedback loop), then `_refresh_hex_preview()`.
- `_hexagon_path(bounds, flat_top: bool)` gets a new parameter:
  `angle_offset = 0 if flat_top else -90` (0° starting angle → vertices
  at 0/60/120/180/240/300°, no vertex at top/bottom → flat top edge;
  the existing `-90` offset is the already-implemented pointy-top
  case). `_refresh_hex_preview` passes `flat_top=(self._hex_preview_orientation
  == "flat")` and returns early (no mask) when the orientation is `None`.
- `_rebuild_scene_from_root` (which already resets `_hex_preview_item`
  to `None` before `_refresh_document_guides()` re-adds it) needs no
  change beyond that — the orientation itself isn't scene-item state,
  it survives a reload already since it's a plain widget attribute.

## Verification

Extend the existing hex-preview checks in
`tests/verify/verify_svg_editor_widget.py` (same file the original
TODO `d1d176f` tests live in):

- Clicking the flat-top button adds a mask whose path differs from the
  pointy-top one (different vertex positions for the same bounds --
  confirm via each path's own bounding box/vertex set, not just "some
  item exists").
- Clicking pointy-top while flat-top is active switches to pointy-top
  and unchecks the flat-top button (mutual exclusion).
- Clicking the currently-active button again turns the mask off
  entirely and unchecks both buttons (neither-selected is reachable).
- The toggle state (including "off") still persists correctly across
  `_rebuild_scene_from_root`.
- Full `tests/verify/` regression suite.
