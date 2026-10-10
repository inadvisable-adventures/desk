# HUD Manager widget (TODO `93f79ca`) (COMPLETED)

Depends on `plans/hud-render-mode.md`.

`widgets/hud_manager/` (`kind: "python"`, no capabilities): a schematic of
the viewport (a rectangle) with a tinted rectangle per HUD-pinned widget at
its fixed on-screen rect, titled when large enough. Clicking one calls
`DeskWindow.leave_hud(instance_id)`. A hint line says how, or that nothing is
pinned. Polls `DeskWindow.get_hud_layout()` every 200 ms only while visible
(same shape as the Minimap; HUD state emits a Qt signal but widgets reach
the window, not the view). Verified in `verify_hud_mode.py`.
