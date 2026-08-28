# Shared project-scoped state store: non-validated core (TODO `f68383f`) (COMPLETED)

## Summary

A shared, capability-gated, project-scoped state store --
`desk.state.get(key)` / `set(key, value, edit?)` / `getHistory(key,
limit)` -- closing `widget-extraction-communication-gaps` gaps 1-4/6
and the concrete two-widget case in `shared-state-with-semantic-edits`.
Full design context, already had: `investigations/app_structure_dsl_design.md`'s
"Shared state store design" and "Semantic edits" sections. This plan
covers the **non-validated core only** -- schema declaration/
validation, conflict resolution, built-in/top-level schema files, and
the schema/state-management widget are TODO `6e1c2fe`, explicitly
blocked on this item landing first.

## Affected files

- `src/desk/desks.py` -- `StateHistoryEntry`/`StateEntry` dataclasses,
  a new `Desk.state` field, `load_desk`/`save_desk`/`desk_state_dict`
  updated.
- `src/desk/server/app.py` -- `SetStateRequest` model, three new
  routes, a new `state` capability.
- `src/desk/server/bridge_client.py` -- `desk.state.{get,set,
  getHistory}`.
- `src/desk/shell/window.py` -- `get_state`/`set_state`/
  `get_state_history`, `STATE_HISTORY_MAX_ENTRIES`.
- `src/desk/temp_ui.py` -- Bridge API doc section, capability list,
  `TEMPUI_DOC_VERSION` bump + changelog entry.
- `tests/verify/` -- new coverage.

## Design decisions

- **One `state` capability, covering both `get`/`getHistory` and
  `set`** -- matches every other Bridge namespace's own one
  -capability-per-namespace precedent (`workspace`, `fs`, `events`,
  ...); no existing namespace splits read/write into separate
  capabilities, and nothing about this one warrants being the first.
- **`edit` is opaque to Desk** -- stored and relayed exactly as given,
  the same way `desk.events` payloads already are; Desk has no way to
  run arbitrary widget-authored interpretation logic, and isn't meant
  to (see the investigation doc's own reasoning).
- **Change notification is a single, well-known event name**,
  `desk.state.changed`, payload `{key, value, edit}` -- not a
  per-key event name -- reusing `desk.events`' existing
  subscribe-to-a-set-of-names shape (a subscriber that only cares
  about one key filters by `key` in its own handler) rather than
  inventing a dynamic per-key event-name convention. `set()` publishes
  via the same `EventMediator.publish` every `events.publish` Bridge
  route already calls, with the calling widget's own `instance_id` as
  `sender_instance_id` -- so a widget never gets its own writes echoed
  back, the same standard pub/sub default `desk.events` already has.
- **`get(key)` returns `{value, edit}`**, not just `value` -- `edit`
  from the same *last write* to that key. An unset key returns
  `{"value": None, "edit": None}`, matching `getLocalStorage`'s own
  "empty/default for nothing-yet" convention rather than a 404.
- **`getHistory(key, limit)`**: a fixed-size-N FIFO per key -- for a
  cap of N (`STATE_HISTORY_MAX_ENTRIES`, a plain module constant, 50
  for this pass), the stored history always holds exactly the N most
  recent `(value, edit)` pairs, oldest evicted as new ones arrive.
  Returned **latest-first**; `limit` (default N) is clamped to
  `min(limit, len(history))`, never an error for asking for more than
  exists.
- **Persistence mirrors `Desk.custom_widgets`/`Desk.file_type_registry`
  exactly** -- a new `Desk.state: dict[str, StateEntry]` field, no new
  persistence mechanism. The history persists alongside the current
  value for the same reason the value itself does (a reload shouldn't
  show a value with no explanation of how it got there).
- **No schema/validation in this pass at all** -- every `value`/`edit`
  is opaque JSON, no type checking, no capability-scoped-per-key
  concept. This item's own get/set/history/events core is genuinely
  useful standalone (confirmed against `shared-state-with-semantic-edits`'s
  real two-widget case: get/set/history alone already deletes 3 of
  its 4 hand-rolled pain points with no schema concept needed at all).

## Step-by-step implementation

1. `desks.py`: `StateHistoryEntry(value: object, edit: object | None =
   None)`, `StateEntry(value: object, edit: object | None = None,
   history: list[StateHistoryEntry] = field(default_factory=list))`;
   `Desk.state: dict[str, StateEntry] = field(default_factory=dict)`;
   `load_desk`/`desk_state_dict`/`save_desk` read/write it, mirroring
   the existing `custom_widgets` round-trip shape exactly (a small
   `_load_state_entry`/`_state_entry_dict` pair).
2. `window.py`: `STATE_HISTORY_MAX_ENTRIES = 50`;
   `get_state(self, key: str) -> dict` (`{"value":..., "edit":...}`,
   defaulting both to `None`); `set_state(self, key: str, value,
   edit, instance_id: str) -> None` (creates/updates
   `self.current_desk.state[key]`, appends to history with the FIFO
   eviction, publishes `desk.state.changed` via
   `self._event_mediator.publish(...)`); `get_state_history(self,
   key: str, limit: int) -> list[dict]` (latest-first, clamped).
3. `app.py`: `SetStateRequest(BaseModel): key: str; value: object;
   edit: object | None = None`; three routes --
   `GET /api/bridge/state/get?key=...`,
   `POST /api/bridge/state/set`,
   `GET /api/bridge/state/getHistory?key=...&limit=...` (default
   `limit` to `STATE_HISTORY_MAX_ENTRIES`-shaped default via a query
   param default) -- each gated by `require_caller("state")` +
   `require_instance_id`, calling the new `DeskWindow` methods via
   `run_on_gui`.
4. `bridge_client.py`: `state: { get: (key) => ..., set: (key, value,
   edit) => ..., getHistory: (key, limit) => ... }` in the
   `window.desk` object, same `call()` helper every other namespace
   already uses.
5. `temp_ui.py`: a new "self.\*"-adjacent Bridge API doc section for
   `desk.state.*` (in `_CUSTOM_WIDGETS_DOC`, alongside the existing
   capability list -- `workspace`, `fs`, `widgets`, `events`, ...
   gains `state`); `TEMPUI_DOC_VERSION` bump + matching comment block
   + `_NEW_FEATURES_DOC` entry.
6. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- No schema/type safety at all in this pass -- deliberately deferred
  to TODO `6e1c2fe`, not a gap being silently ignored.
- `STATE_HISTORY_MAX_ENTRIES` is a single fixed default, not
  per-key configurable -- matches the investigation doc's own "not
  per-key configurable in v1" decision.
- `desk.state.changed`'s single event name means every subscriber
  receives every key's changes and filters client-side -- simpler
  than a dynamic per-key event-name scheme, at the cost of a chattier
  subscription for a widget that only cares about one key in a
  project with many.

## Verification

New checks, real (no mocking), mirroring
`verify_bridge_api_editor_or_scrap.py`/`verify_html_widget_local_storage.py`'s
own established real-server-plus-pumped-event-loop pattern:
- `tests/verify/verify_state_store.py`:
  - `get` on a never-set key returns `{"value": None, "edit": None}`.
  - A real `set` then `get` round trip returns the same `value`/`edit`.
  - `set` with no `edit` given defaults it to `None`, not an error.
  - `getHistory` after more than `STATE_HISTORY_MAX_ENTRIES` writes to
    one key holds exactly `STATE_HISTORY_MAX_ENTRIES` entries, oldest
    evicted, returned latest-first; a `limit` smaller than the full
    history is honored; a `limit` larger than what exists returns
    everything without error.
  - A real second widget instance, subscribed to `desk.state.changed`
    via a real `desk.events.subscribe` call, actually receives the
    `{key, value, edit}` payload after another instance's real `set`
    call -- and the *setting* instance itself does not receive its own
    change back (`sender_instance_id` exclusion).
  - A real save-then-load round trip (`save_desk`/`load_desk` against
    a real temp file) preserves both the current value and the full
    history.
  - Missing the `state` capability on the calling widget's manifest
    gets a real 403 from both `get` and `set`.
- Full `tests/verify/` regression suite.
