# Plan: TODO 996a5eb — eye button persists through `title_only`

## Summary

The 👁 eye button (`_EyeButton`, TODO 33d3e8d) claims in its own
docstring to be "always present on every titlebar regardless of
current chrome/zoom state," but `_TitleBar._refresh_button_visibility`
actually hides it along with every other button once the `title_only`
chrome-degrade state kicks in. Fix the gating so it persists (still
hidden while locked, unchanged), and widen the `title_only`/greeked
size threshold to require room for both the title and the eye button.

## `src/desk/shell/widget_frame.py`

- `_refresh_button_visibility`: `self.eye_button.setVisible(not
  self._locked)` -- no longer multiplied by `show` (the
  `not self._buttons_hidden` flag every other button is gated by).
- `min_title_only_width_px`: adds the eye button's own on-screen width
  (`_button_target_width(self.eye_button)`) plus one button-spacing gap
  when not locked, on top of the existing title-only baseline. When
  locked, unchanged (eye button doesn't show while locked either way).
- `min_full_width_px`: excludes the eye button from its own button
  -width sum, since that width is now already folded into
  `min_title_only_width_px`'s own baseline (the eye button persists in
  *both* the full and title_only states) -- without this exclusion,
  its width would be double-counted, inflating the full-chrome
  threshold above what's actually needed.

## Verification

- `_refresh_button_visibility`: with `_buttons_hidden=True` (title_only)
  and not locked, the eye button is still visible while every other
  button (close/lock/bring-to-front/send-to-back/tempui-promote/stale)
  is hidden; locked still hides it regardless of `_buttons_hidden`.
- `min_title_only_width_px`/`min_full_width_px`: confirm the former now
  includes the eye button's width (not locked) and excludes it when
  locked; confirm the latter doesn't double-count it (i.e.
  `min_full_width_px - min_title_only_width_px` equals the sum of
  every *other* currently-relevant button's width + gaps, not that sum
  plus the eye button again).
- End-to-end on a real `WidgetFrame`/`WorkspaceView`: shrinking a
  placed widget down to a width between the new thresholds shows the
  title label and the eye button but nothing else; shrinking further
  (below the new, larger `min_title_only_width_px`) greeks it, where
  it previously would have stayed in `title_only` with just the eye
  button missing.
- Full scratchpad regression suite (`git stash` before/after) --
  expect no functional regression, but this changes the on-screen
  width thresholds at which `title_only`/`greeked` kick in, so any
  existing chrome-degrade test asserting an exact pixel boundary is
  worth double-checking specifically.
