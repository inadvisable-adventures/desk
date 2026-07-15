# Plan: TODO b5d52c0 (COMPLETED) — file type registry service

## Summary

A registry mapping file types (extension and/or MIME type) to the
widget(s) that can view/edit/consume/produce them, generalizing the
hardcoded `EXTERNAL_DROP_WIDGET_BY_SUFFIX` map in `desk/shell/window.py`
into something dynamic and editable. Persisted on the `Desk`
dataclass/`.desk` file. A new Bridge API service (`kind: "html"`
widgets) backs a new `filetype_registry_editor` widget; a
`current_context` hook + the existing generic event-mediator binding
back a `kind: "python"` Project Files' own consumption -- see the
clarifying question resolved this session: python widgets reach Desk
services in-process, matching every other python widget, not via real
HTTP Bridge API calls (that mechanism is `kind: "html"`-only).

## Data model (`src/desk/file_type_registry.py`, new module)

```python
@dataclass
class FileTypeHandler:
    widget_id: str
    role: str  # "view" | "edit" | "consume" | "produce"

@dataclass
class FileTypeRegistryEntry:
    extensions: list[str] = field(default_factory=list)   # e.g. [".svg"]
    mime_types: list[str] = field(default_factory=list)   # e.g. ["image/svg+xml"]
    handlers: list[FileTypeHandler] = field(default_factory=list)

FILE_TYPE_REGISTRY_UPDATED_EVENT = "desk.file_type_registry.updated"

def entry_to_dict(entry) -> dict: ...
def entry_from_dict(data: dict) -> FileTypeRegistryEntry: ...
```

Mirrors `desk.temp_ui.CustomWidgetDefinition`'s own to/from-dict shape
(see `desks.py`'s `_custom_widget_dict`/`_load_custom_widget`) closely
enough to reuse that same pattern, not invent a new one.

## Persistence (`src/desk/desks.py`)

- `Desk.file_type_registry: list[FileTypeRegistryEntry] = field(default_factory=list)`.
- `desk_state_dict`: add `"file_type_registry": [entry_to_dict(e) for e
  in desk.file_type_registry]`.
- `load_desk`: add `file_type_registry=[entry_from_dict(d) for d in
  data.get("file_type_registry", [])]` (missing key -> `[]`, same
  old-file-compatibility posture as `custom_widgets`).

## Bridge API (`src/desk/server/app.py`)

- New capability string: `"filetypes"` (same coarse, resource-level
  shape as `workspace`/`fs`/`widgets`/`events`/`introspect`).
- `GET /api/bridge/filetypes/get` (`require_caller("filetypes")` +
  `require_instance_id`): subscribes the caller to
  `FILE_TYPE_REGISTRY_UPDATED_EVENT` via the mediator directly (cheap,
  no `run_on_gui` needed -- same reasoning `events/subscribe` already
  uses), then returns `{"entries": [...]}` via `run_on_gui(lambda:
  gui_bridge.window.get_file_type_registry_dicts())`. One call does
  both "read" and "start watching for future edits," per the original
  request.
- `POST /api/bridge/filetypes/set` (same deps, new
  `SetFileTypeRegistryRequest(BaseModel): entries: list[dict]`): calls
  `run_on_gui(lambda: gui_bridge.window.set_file_type_registry(body
  .entries, instance_id))`.
- `bridge_client.py`'s `BRIDGE_CLIENT_TEMPLATE` gains a `filetypes`
  namespace: `get: () => call("GET", ".../filetypes/get")`, `set:
  (entries) => call("POST", ".../filetypes/set", { entries })`.

## `DeskWindow` (`src/desk/shell/window.py`)

- `get_file_type_registry_dicts(self) -> list[dict]`: converts
  `self.current_desk.file_type_registry` to dicts.
- `set_file_type_registry(self, entries: list[dict], sender_instance_id:
  str) -> None`: replaces `self.current_desk.file_type_registry` (from
  dicts), `self.save_current_desk()`, then
  `self._event_mediator.publish(FILE_TYPE_REGISTRY_UPDATED_EVENT,
  {"entries": entries}, sender_instance_id)` -- the event payload
  carries the new registry directly, so a subscriber never needs a
  separate re-fetch call to learn what changed.
- `_refresh_picker` (already the place `current_context
  .set_current_desk_directory` gets refreshed on startup/Desk-switch)
  also calls a new `current_context.set_file_type_registry_provider
  (self.get_file_type_registry_dicts)`.

## `current_context.py`

New get/set pair, `_file_type_registry_provider: Callable[[], list[dict]]
| None`, mirroring every other hook here (`set_widget_opener`-style),
for a `kind: "python"` widget's one-time initial read.

## Project Files (`widgets/project_files/widget.py`)

- `__init__`: `provider = current_context.get_file_type_registry_provider();
  self._file_type_registry = provider() if provider else []`.
- New `bind_event_mediator(self, instance_id, mediator)` (duck-typed,
  called generically by `DeskWindow._bind_event_mediator` for every
  placed python widget, TODO 6f9c51b): constructs a
  `desk.shell.event_broker.EventSubscription(mediator, instance_id,
  names=[FILE_TYPE_REGISTRY_UPDATED_EVENT], parent=self)`, connects its
  `message_received` to a handler that replaces `self
  ._file_type_registry` with the event payload's `"entries"` -- no
  Bridge API involved, no re-fetch, matching the "never re-fetching
  from scratch on every event" requirement directly.
- Not consumed for dispatch logic yet -- that's TODO efdad99, which
  depends on this registry existing but is a separate item.

## New widget: `widgets/filetype_registry_editor/`

(TODO's own text used the hyphenated name "filetype-registry-editor";
translated to this project's actual directory/id convention --
lowercase, underscore-separated, matching every other widget id, e.g.
`project_files`/`event_log` -- rather than introducing the first
hyphenated widget id in the catalog.)

- The first genuinely hand-authored `kind: "html"` widget under
  `widgets/` in this project (every other `kind: "html"` widget is a
  runtime-materialized `DefineWidget` one) -- plain HTML/CSS/JS, no
  build step, matching this project's existing "Chromium/HTML kind:
  plain code, no framework" posture (see design-docs/architecture.md).
- `widget.json`: `{"name": "File Type Registry Editor", "kind": "html",
  "entry": "index.html", "capabilities": ["filetypes"], "default_size":
  {"width": 560, "height": 480}}`.
- `index.html`: on load, calls `window.desk.filetypes.get()`, shows the
  registry as pretty-printed JSON in a `<textarea>`. A Save button
  parses the textarea's JSON and calls `window.desk.filetypes.set
  (entries)`, showing a status message on success/parse-error. A
  Reload button re-fetches. Deliberately minimal UI (not a structured
  per-entry editor) -- the TODO's ask is the read/edit/event-plumbing,
  not a polished editing experience.

## Verification

- `FileTypeRegistryEntry`/`FileTypeHandler` to/from-dict round-trip;
  `Desk`/`desk_state_dict`/`load_desk` persistence round-trip; an old
  `.desk` file with no `file_type_registry` key defaults to `[]`.
- Bridge API, over real HTTP (a running server + a real `GuiBridge`
  attached to a fake window double, matching the established
  background-thread-request-while-pumping-the-event-loop pattern):
  `GET .../filetypes/get` returns the current registry and the calling
  instance ends up subscribed (confirmed via the mediator's own
  `list_subscriptions`); `POST .../filetypes/set` updates the Desk,
  persists it, and publishes the update event to every *other*
  subscribed instance (not the sender, matching `EventMediator.publish`
  's own documented behavior) with the new entries as payload; a caller
  lacking the `filetypes` capability gets a 403.
- `current_context.get_file_type_registry_provider()`'s initial read;
  `Project Files`'s `bind_event_mediator` updates its local
  `_file_type_registry` when a real published event arrives, without
  making any further calls.
- Full scratchpad regression suite (`git stash` before/after).
