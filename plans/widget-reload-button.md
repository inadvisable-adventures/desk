# Generic `[RELOAD]` titlebar button (TODO `fd2c1ba`) (COMPLETED)

## Summary

A `[RELOAD]` button on every placed `ChromiumWidget` (`kind: "html"`) titlebar that re-navigates just that
instance's page (`frame.content.reload()`): no rebuild, no content-hash check, no confirmation. It occupies the
slot `[STALE]` uses; when the instance is stale `[STALE]` is shown instead (never both). Python widgets have no
page, so they don't get it.

## Affected files

- `src/desk/shell/widget_frame.py` -- `_ReloadButton`; `_TitleBar.reload_button`, `set_reloadable`,
  `_refresh_button_visibility`, `_visible_button_widgets_for_full_state`, `_button_target_width`, `apply_scale`;
  `WidgetFrame.__init__` sets reloadable when `content` has a callable `reload`.
- `src/desk/shell/canvas.py` -- import, `_BUTTON_KINDS`, `_hit_test_chrome`, `widget_reload_clicked`, dispatch.
- `src/desk/shell/window.py` -- connect signal; `_on_widget_reload_clicked`.
- `src/desk/temp_ui.py` -- new-features entry + tag.
- `design-docs/widget-ux.md`; `tests/verify/verify_widget_reload_button.py` (new).

## Steps

1. Add `_ReloadButton`, titlebar wiring (visible iff `show and reloadable and not stale`).
2. Canvas hit-test/signal/dispatch.
3. Window handler calling `frame.content.reload()`.
4. Tempui new-features entry; design doc.
5. Verify script: visibility rules (reloadable, stale swap, locked, popup, title_only), button kind recognized,
   click handler reloads only the clicked frame.

## Status

Verification ran headless (offscreen); launching the real app was skipped. `[RELOAD]` stays visible while locked, like `[STALE]`.
