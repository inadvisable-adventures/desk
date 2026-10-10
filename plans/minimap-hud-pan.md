# Minimap uses HUD render mode (TODO `1ce5130`) (COMPLETED)

Depends on `plans/hud-render-mode.md`.

`MinimapWidget.hud_trigger()` returns the map view (`_map`) -- not the
button row. A press on the map pins it at its current screen position and
the drag then pans 1:1, because the pointer's overlay-local coordinates no
longer change as the canvas moves. After the drag the map stays pinned
(decided with the user) until returned via right-click or the HUD Manager.
`_MapView`'s own mouse handling is unchanged: it receives forwarded events
in its own local coordinates.

Verified in `tests/verify/verify_hud_mode.py` (stationary pointer keeps
targeting the same scene point; buttons still work and don't pin).
