# tempui-hmsvc.md: `desk.hmsvc.list()` shape (TODO `650713d`) (COMPLETED)

## Summary

The worked example did `const services = await desk.hmsvc.list();
services.find(...)`, but the route returns `{"services": [...]}` (as it
has since the first hmsvc commit), so a copy-paste author got
`TypeError: services.find is not a function`. Source feedback:
`FEEDBACK-DESK-tempui-hmsvc-md-s-worked-example-treats-desk-hmsvc-list-as-a-2026-11-06-2216.md`.

## Decision

Fix the docs, not the route: the object shape matches `logs` (`{lines}`),
the action routes (`{ok, message}`) and the `desk.hmsvc.changed` event
payload, and changing it would break any widget already written against
the real behavior.

## Changes (`src/desk/temp_ui.py`, docs only)

- Worked example destructures `{ services }`; a `desk.state` variant for
  the URL-only case is shown first.
- Networking section now opens with "Only need a service's URL? Use
  `desk.state`" (the report's secondary finding: the lighter pattern was
  buried), and states every `desk.hmsvc.*` return shape; the Bridge API
  bullet in `tempui-custom-widgets.md` does too.
- Tag `#650713d` + changelog entry.

## Verification

`verify_tempui_hmsvc_doc.py` gains checks that start the real server and
GET `/api/bridge/hmsvc/list` and `/logs` for their shapes, assert the doc
text matches, and execute the doc's JS blocks under node against the real
list response (the pre-fix example throws there). 32 checks pass.
