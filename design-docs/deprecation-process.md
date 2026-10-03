# Desk — Deprecation by tombstone

TODO `df8138a`. How Desk replaces a widget-facing API without carrying the old
behavior forever. (Widget *kinds* retired from the picker, such as the old Markdown
widget, are a different, display-only mechanism and are not covered here.)

## The model

When a widget-facing API is replaced, Desk keeps the **old name** but puts
**nothing behind it except**:

1. a **report** to Desk that the old API was used, and
2. an **error** that says what to use now and carries a short command to give an
   agent.

There is no grace period and no old behavior to maintain. Where a mechanical rewrite
is possible, Desk offers to apply it; Desk always also offers a short command to
paste into an agent console, or to launch an agent console to do the fix.

"Widget-facing" means everything an author of widgets, jobs, services or tempui
files writes against: the Bridge JS (`window.desk.*`), python-widget hooks
(`current_context.*`), tempui DSL keywords and their fields, `widget.json` /
`service.json` fields, and wire-level behavior of the Bridge.

## The registry

`src/desk/deprecations.py` holds one `Deprecation` per replaced API:

| Field | Meaning |
|---|---|
| `id` | `DEPR-NNN`; what runtime messages and reports refer to |
| `surface` | `bridge_js`, `python_hook`, `tempui_keyword`, `manifest_field` or `wire_path` |
| `old` / `replacement` | the old name (a dotted path for Bridge JS) and what to use now |
| `message` | one or two sentences: what changed and what to do. It must be complete on its own |
| `since` | the date it was replaced |
| `detector` / `rewriter` | optional: what to scan for, and a mechanical rewrite (used by the scan and rewrite follow-ups; nothing runs them yet) |

`format_error` builds the message every tombstone carries (old API, replacement,
the `message`, the id, and `paste: <agent command>`); `agent_command` builds the
short command. Neither ever refers to documentation of the old API, because none is
needed.

## What a tombstone does, per surface

| Surface | Old name becomes |
|---|---|
| Bridge JS | a stub installed by the injected client: it posts to `/api/bridge/deprecations/report` (the instance's own credential says which instance) and rejects with the returned message (`err.deprecated` holds the id) |
| python hook | `tombstone(dep_id)`: reports the caller's file and line, raises `DeprecatedApiError`; takes any arguments |
| tempui keyword | `detect_temp_ui_kind` returns `deprecated:<id>`; `DeskWindow` reports the file and does not act on it (not a widget, and not silently a Question) |
| manifest field | `check_manifest(...)`: the manifest fails to load (`DeprecatedManifestError`, also a `ValueError`); `service.json` services are listed but inert |
| wire path | the Bridge identity dependency refuses the request (403) with the message |

## Reporting

`DeprecationRegistry.report` records a use **once per instance and API**, then
notifies listeners. `DeskWindow` listens (hopping to the GUI thread) and: lights the
widget's `[ERROR]` titlebar marker with the full message for a placed instance --
independent of whether the widget catches the exception; offers the fix actions straight
away for a tempui file or a manifest (which have no frame); and only logs a python hook
(its caller is already getting the exception).

**Fix actions** (clicking the marker, or straight away when there is no frame): *Copy
command* puts the short `agent_command` on the clipboard; *Launch agent console* opens a
Claude (Desk) widget (the way the `[CHAT]` button does) seeded with `agent_instructions`
-- the id, old API, replacement and message from the registry, where Desk saw the use
(widget kind, instance, source directory, the file or manifest), and "find the code,
switch it to the replacement, check it works; do not go looking for documentation of the
old API"; or *Dismiss*. A removed instance's reports are
forgotten, so a re-placed one reports again.

## Preserving the old documentation

The documentation of a replaced API is **not** kept in the current docs. It is moved
verbatim into the isolated history store, which exists for deep-dive investigations
only, is never linked from current docs, and must never be loaded as a consequence of
normal operation (see the guard line in `CLAUDE.md` for where it is). Current docs and
the docs Desk writes into projects describe only the current API; runtime messages
refer to a deprecation by id only. The checklist for preserving a replaced API's docs
lives with that store, and `tests/verify/verify_deprecated_docs_isolation.py` enforces
the no-leak rules.

## Adding a deprecation (the code side)

1. Register a `Deprecation` in `src/desk/deprecations.py` (id next in sequence).
2. Install the tombstone on its surface (the table above): add the old name as a
   stub, or register the keyword/field/path -- the surface hooks are already wired.
3. Replace the old API's description in the current docs with the new API only.
4. Move the old description into the history store and run the isolation test (see
   the store's own checklist).
5. If agents inside Desk are affected (tempui DSL, Bridge API), mint the tempui
   changelog tag/entry; it describes the new way only.
6. Add tests: the tombstone throws and reports (see `verify_deprecations.py`), and
   any detector/rewriter has before/after fixtures.

## Status

Built (TODO `df8138a`): the registry, the tombstones for all five surfaces, once-per
-instance reporting, the `[ERROR]`-marker handling and the fix actions (copy command / launch
agent console, TODO `18fa45f`), and the first real
deprecation, DEPR-001 (the shared per-launch Bridge token as caller identity), which is
now a tombstone. Planned follow-ups: a scan for deprecated usage before it runs (TODO
`284bfbd`), and previewed/confirmed rewriters (TODO `cc78e9d`). Direction on what happens to the old *documentation*
later: "micro-tombstoning" -- it is removed from the tree in one commit and an immediate
follow-up commit records that commit's id with keywords so it stays findable in git history
(details parked in `PARKINGLOT.md`). Whether the tombstone stubs themselves are ever removed
is still open.
