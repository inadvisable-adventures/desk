import re
import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path

TEMP_UI_DIRNAME = ".desk_temp"
DOC_FILENAME = "desk-temporary-ui.md"
# **/__pycache__/ covers what running a seeded scripts/todo_item_ids.py
# (TODO c458012) produces the first time it's invoked -- not specific
# to .desk_temp, but bundled under the same "Desk-specific patterns"
# gitignore checkbox since both are provisioned together.
GITIGNORE_ENTRIES = (".desk_temp/", "**/__pycache__/")
GITIGNORE_COMMENT = "# Desk-specific"

# desk-temporary-ui.md's *static* main content (DOC_TEMPLATE below) is
# only ever written once, the first time a directory's .desk_temp is
# provisioned -- an older Desk directory otherwise keeps whatever
# stale copy it got at creation time forever, even after this file's
# own content has since improved (a new DSL section, a correction).
# TEMPUI_DOC_VERSION (TODO f7b1611) is a plain, manually-bumped
# integer that fixes this: bump it by exactly 1 any time DOC_TEMPLATE's
# static content changes in a way that would matter to an agent
# reading it (a new section, a real correction) -- NOT for whitespace
# -only tidying, and NOT for the separate, dynamically-generated
# custom-widgets section (TODO 91b3f42), which is already kept in sync
# on its own regardless of this version. There's no reliable automatic
# way to detect "did this edit change the doc's *meaning*" (a typo fix
# and a new DSL section can touch the same number of lines) -- a human
# decides at edit time, the same spirit as this project's own
# permanent TODO item ids (assigned once, never recomputed). See
# ensure_docs_current, called before a Desk is opened.
#
# TODO e57ce5f: this one version number now stands for the *whole* set
# of tempui-*.md files (SPLIT_DOC_CONTENT below), not just this one --
# bump it for a meaningful change to any of them, and don't add a
# separate version note to any split file (there isn't one to add).
#
# TODO 6f9c51b: bumped 6 -> 7 for a new "Sending and receiving named
# messages" section in _CUSTOM_WIDGETS_DOC (the events capability).
#
# TODO f693275: bumped 7 -> 8 for a new `Capability` DefineWidget DSL
# line in _CUSTOM_WIDGETS_DOC (a DefineWidget widget can now declare
# Bridge API capabilities, e.g. to use events.*).
#
# TODO 9767c1a: bumped 8 -> 9 for a new "Inspecting another widget"
# section in _CUSTOM_WIDGETS_DOC (the introspect capability).
#
# TODO 6e731c1: bumped 9 -> 10 for a new `OpenImage` keyword (its own
# new tempui-image.md split doc, linked from the main file's intro
# list) -- a dropped image is now saved into .desk_temp and displayed
# through it, but it's a general DSL capability like every other
# keyword, not only reachable via drag-and-drop.
TEMPUI_DOC_VERSION = 10
_DOC_VERSION_PLACEHOLDER = "{{TEMPUI_DOC_VERSION}}"
_DOC_VERSION_RE = re.compile(r"<!-- desk-temporary-ui\.md version: (\d+)")

DOC_TEMPLATE = """# Temporary UI

<!-- desk-temporary-ui.md version: {{TEMPUI_DOC_VERSION}} -- do not edit this line by hand; Desk uses it to detect when this file's own main content (and the other tempui-*.md files it references) is out of date and needs refreshing. -->

This directory holds "temporary UI" files: a lightweight way for an
agent (or any external process) to ask a question through Desk's own
canvas instead of a terminal prompt.

Each file is named with a bare UUID (e.g.
`550e8400-e29b-41d4-a716-446655440000`, no extension). Desk watches
this directory: a newly-created file shows up as a clickable
notification in the app's upper-right corner; clicking it places a new
widget on the canvas, centered in the current view. There are eight
built-in file types, distinguished by their first line's keyword:

- `Question` (below) — a quick multiple-choice question, answered by
  clicking an option.
- `LightningRound` — the same multiple-choice question asked
  repeatedly over a list of items. See
  [tempui-lightning-round.md](./tempui-lightning-round.md).
- `OpenMarkdown` / `Markdown` — open an existing Markdown file, or
  render Markdown content given directly in the tempui file itself.
  See [tempui-markdown.md](./tempui-markdown.md).
- `OpenImage` — open an existing image file in the Image Viewer
  widget. See [tempui-image.md](./tempui-image.md).
- `Scratch` — arbitrary free-form notes shown in a Scratch widget. See
  [tempui-scratch.md](./tempui-scratch.md).
- `DefineWidget` — introduce a brand-new, entirely in-browser widget
  kind (invokable by a later tempui file, promotable to the Desk),
  plus the Bridge API your widget's own JS can call. See
  [tempui-custom-widgets.md](./tempui-custom-widgets.md).
- `DiscussParkingLotItem` — have Desk start a brand-new `claude`
  session to discuss one `PARKINGLOT.md` item. See
  [tempui-discuss-parking-lot-item.md](./tempui-discuss-parking-lot-item.md).

Every file named above lives in this same directory.

## Questions for the user: use QUESTIONS.md, not this DSL

If you have an open-ended question *for the user* — something you're
genuinely blocked on and need their input to resolve, as opposed to a
single quick multiple-choice decision (`Question`/`LightningRound`
below are for that) — write it to `QUESTIONS.md` at the project root
instead of creating a file here. Each entry is a `## <short summary>`
heading, the question's own text below it, then a trailing
`(Answer: )` placeholder line for the user to fill in (leave it empty;
never write your own guess into it). If `QUESTIONS.md` doesn't exist
yet, create it with a `# Questions with optional answers` title line
first.

Desk watches `QUESTIONS.md` the same way it watches this directory: a
newly-added entry surfaces as a top-right notification, which either
focuses an already-open Questions widget or opens a new one, letting
the user answer directly from the canvas. This is on top of whatever
your own working conventions already say about tracking questions
(e.g. this project's own `development-process.md`, if it has one) —
follow those for *when* to ask, use `QUESTIONS.md` as *where* the
question itself lives.

## The TempUI DSL: Question

Each line is `keyword rest-of-line...` — everything after the first
space is a single natural-language value (a question, an option label,
an answer), not further split into separate parameters.

Supported keywords (more may be added later; unrecognized keywords are
ignored, not an error):

- `Question <text>` — the question shown to the user.
- `Option <text>` — one selectable choice. Repeat for each option.
- `Answer <text>` — appended automatically once the user picks an
  option; do not write this yourself.

Example, before an answer is given:

```
Question What color should the header be?
Option Red
Option Green
Option Blue
```

After the user clicks "Green":

```
Question What color should the header be?
Option Red
Option Green
Option Blue
Answer Green
```

This file (`desk-temporary-ui.md`), and the other `tempui-*.md` files
it links to above, are themselves ignored by the file watcher — none
of their names are UUIDs, so none are ever mistaken for a temp UI
file.
"""

# The less-general DSL sections split out of DOC_TEMPLATE (TODO
# e57ce5f), each a sibling file in the same .desk_temp directory as
# desk-temporary-ui.md, linked from its intro above. None of these
# carry their own version note -- TEMPUI_DOC_VERSION covers the whole
# set (see the comment on that constant). Grouped by feature area, not
# strictly one keyword per file: OpenMarkdown/Markdown already
# cross-reference each other; DefineWidget/invocation/promotion/the
# Bridge API are one cohesive feature, not four unrelated ones.

_LIGHTNING_ROUND_DOC = """# TempUI DSL: LightningRound

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
just covers the `LightningRound` keyword.

For asking the *same* multiple-choice question repeatedly over a list of
items (e.g. classifying a batch of words, reviewing a batch of files),
one at a time, answerable by clicking a button or pressing a single
keyboard key — instead of writing one `Question` file per item.

Lines with more than one value are **tab**-separated (not
space-separated like `Question`/`Option`/`Answer`), since a name,
prompt, or description may itself contain spaces:

- `LightningRound<TAB>name<TAB>prompt` — **must be the first line**.
  `name` is a short label; `prompt` is the question asked about every
  item (e.g. "Is this word a noun, verb, or adjective?").
- `Option <character>` — reused from the `Question` type verbatim
  (space-separated, not tab-separated). The value is a single character,
  used both as the option's keyboard shortcut and its on-screen label.
  Repeat once per option — at least two. These options apply to every
  item in the file, not just one.
- `LRItem<TAB>description<TAB>answer` — one "lightning round item".
  `answer` is the literal string `unanswered` until the user picks an
  option, at which point Desk replaces it with that option's character
  — do not write anything other than `unanswered` here yourself. Repeat
  for each item; Desk shows one unanswered item at a time (in file
  order), skipping any that already have a real answer.

Example, before any answers:

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	unanswered
LRItem	quick	unanswered
```

After the user answers "run" with "V" (pressing the `V` key or clicking
its button):

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	V
LRItem	quick	unanswered
```
"""

_MARKDOWN_DOC = """# TempUI DSL: OpenMarkdown and Markdown

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
just covers the `OpenMarkdown` and `Markdown` keywords.

## OpenMarkdown

For telling Desk to open a Markdown file in the Markdown widget — a
fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file. This is a *pointer* to
an existing file elsewhere on disk — if you want to give Desk markdown
content directly instead, use `Markdown` below.

- `OpenMarkdown <path>` — the first (and normally only) line. `path`
  is the file to open, absolute or relative to the current Desk's
  directory. Like `Question <text>`, everything after the first space
  is one opaque value, so a path containing spaces needs no escaping.

Example:

```
OpenMarkdown ./diagrams.md
```

Clicking the notification opens `path` in a new Markdown widget
instance, centered in the current view.

## Markdown

For giving Desk markdown *content* directly, rendered in the Markdown
widget — unlike `OpenMarkdown` above, there is no separate target file:
this file's own content *is* the markdown. Fire-and-forget, same as
`OpenMarkdown`: there is no `Answer` line, and Desk never writes back
to this file.

- The first line is `Markdown <label>` — `label` is used for the
  notification text; it is *not* used for anything saved to disk.
- Every line after that, verbatim, is the markdown to render (not
  further parsed here — write real markdown, including fenced
  ` ```mermaid ` blocks if you want a diagram).

Example:

```
Markdown Investigation summary
# Investigation summary

Found the bug in `file_watch.py` line 42.
```

The resulting widget shows a **"Save As"** button in place of "Open"
(there's nothing to "open" — its content already comes from this
file, not a chosen path): saving defaults to the project root, with a
filename derived from the *rendered content's own first line*
(kebab-case-slugified, e.g. `# Investigation summary` becomes
`investigation-summary.md`) — not from `<label>` above. Saving opens
the new file in a separate, ordinary Markdown widget instance; this
tempui-bound instance stays open, unaffected.
"""

_IMAGE_DOC = """# TempUI DSL: OpenImage

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
just covers the `OpenImage` keyword.

For telling Desk to open an image file in the Image Viewer widget — a
fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file. This is a *pointer* to
an existing file elsewhere on disk, the same shape as `OpenMarkdown`
(see [tempui-markdown.md](./tempui-markdown.md)) — there is no
inline-content sibling keyword for images.

- `OpenImage <path>` — the first (and normally only) line. `path` is
  the file to open, absolute or relative to the current Desk's
  directory. Like `Question <text>`, everything after the first space
  is one opaque value, so a path containing spaces needs no escaping.

Example:

```
OpenImage ./screenshot.png
```

Clicking the notification opens `path` in a new Image Viewer widget
instance, centered in the current view.

Dropping an image file directly onto the Workspace Canvas uses this
same mechanism automatically: the dropped image is copied into this
directory first, then an `OpenImage` file pointing at the copy is
created and opened immediately (no notification needed for your own
just-performed drop).
"""

_SCRATCH_DOC = """# TempUI DSL: Scratch

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
just covers the `Scratch` keyword.

For giving Desk arbitrary free-form notes to show in a Scratch widget —
a fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file.

- The first line is `Scratch <label>` — `label` becomes the widget's
  title (`Scratch: <label>`).
- Every line after that, verbatim, becomes the widget's initial body
  text (not further parsed — write whatever you want here).

Example:

```
Scratch Investigation notes
Found the bug in file_watch.py line 42.
Still need to check the TempUiManager path.
```

If the user says "scratch" in conversation, this capability is almost
certainly what's meant — not some other, more generic sense of the
word — unless a clearly more pressing local meaning has already been
established earlier in the current conversation.
"""

_CUSTOM_WIDGETS_DOC = """# TempUI DSL: DefineWidget

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
covers the `DefineWidget` keyword, invoking a widget it defines,
promoting one to the Desk, and the Bridge API your widget's own JS can
call.

For introducing a brand-new *kind* of widget to the current Desk —
entirely in-browser (HTML/CSS/JS, rendered in an embedded browser
view), **never Python** — without touching the project's own
`widgets/` directory. Once defined, the new kind gets its own new
tempui DSL keyword that a *separate*, later tempui file can use to
place an instance of it (see "Invoking a defined widget" below) — this
is how the tempui DSL itself gets extended at runtime.

Lines are **tab**-separated (like `LightningRound`), since a label may
contain spaces:

- `DefineWidget<TAB>keyword<TAB>label` — **must be the first line**.
  `keyword` becomes both the new DSL keyword used to invoke this widget
  kind (see below) and its internal widget id — pick something
  CamelCase-ish with no spaces, matching the shape of this DSL's own
  built-in keywords (`LightningRound`, `OpenMarkdown`, ...). `label` is
  the human-friendly name shown in the widget's titlebar and anywhere
  else it's listed — never a UUID or the raw `keyword`.
- `Size<TAB>width<TAB>height` — optional. The new widget kind's default
  placement size in pixels.
- `Capability<TAB>name` — optional, repeatable. Grants this widget kind
  a Bridge API capability (`workspace`, `fs`, `widgets`, `events`, ...)
  — same coarse, resource-level strings a real `widgets/<id>/widget.json`
  manifest's own `capabilities` list uses. Without this, your widget's
  JS can only call the always-available `self.*` calls (see "The Desk
  Bridge API" below) — anything else (including `events.*`) fails with
  a 403 unless you declare the matching capability here.
- `Html<TAB>base64-chunk` — the widget's entire implementation: **one
  self-contained HTML document** (inline `<style>`/`<script>` cover
  CSS/JS — there's no separate CSS/JS file), **base64-encoded**. Split
  across as many `Html` lines as needed (each is just a chunk,
  concatenated in file order before decoding) — a single line doesn't
  have to hold the whole file. At least one `Html` line is required.

Example:

```
DefineWidget	KanbanBoard	Kanban Board
Size	600	400
Capability	workspace
Html	PGh0bWw+PGJvZHk+PGgxPkthbmJhbjwvaDE+PC9ib2R5PjwvaHRtbD4=
```

A `keyword` that collides with one of this DSL's own built-in keywords
(`Question`, `LightningRound`, `DefineWidget`, ...) or an existing
widget id is refused (logged, not an error) — pick something else.

## Invoking a defined widget

A separate tempui file whose **entire first line is just the
keyword**, nothing else, places one instance of that widget kind —
centered in the current view, same as every other tempui-placed
widget:

```
KanbanBoard
```

There's no per-instance content or label here — a defined widget's
titlebar always shows its *type's* own `label` from the `DefineWidget`
line above. If you need different-looking instances, define separate
widget kinds with separate keywords.

A widget placed this way **can only ever be placed via tempui** — it
never appears in the canvas's right-click "Add widget" menu, unlike
every ordinary widget in `widgets/`.

## Promoting a defined widget to the Desk

Every placed instance of a `DefineWidget`-defined widget shows a
`[TEMPUI]` button in its titlebar. Clicking it offers to **promote**
the widget: on confirm, its definition is saved permanently into the
current `.desk` file (surviving even if this `DefineWidget` file is
later deleted) and the original `DefineWidget` file here is removed —
the `.desk` file becomes the sole remaining source of truth.
Invocation (see above) keeps working exactly the same afterward,
promoted or not.

## The Desk Bridge API — what your widget's own JS can call

A `DefineWidget` widget's HTML document runs inside a real embedded
browser page with one extra thing every other web page doesn't have:
`window.desk`, a small JS client automatically injected before your
own code runs. It's how your widget talks back to Desk itself —
notably, **it's the only way to persist your widget's own state
across a Desk reload** (there is no other storage available — no
`localStorage`/`IndexedDB`/cookies persist a Chromium widget's page
across a reload the way you might expect from an ordinary browser tab,
and even if they did, they wouldn't survive the *page* itself
reloading on every Desk restart the way `window.desk.self
.getLocalStorage()` is specifically designed to).

All calls are `async` (they return a `Promise`):

- `desk.self.getLocalStorage()` → `{ data }` — call this once, early,
  when your widget's page loads, to restore whatever you last saved.
  `data` is `{}` for a brand-new instance with nothing saved yet.
- `desk.self.setLocalStorage(data)` → `{ ok: true }` — call this
  whenever your widget's own state changes (on every meaningful
  interaction, or debounced if that's too chatty for your case) —
  `data` must be JSON-serializable. This is **pull-based on Desk's
  side**: whatever you last pushed here is what actually gets written
  to the `.desk` file, at the *next* time the Desk itself is saved
  (not immediately on every call) — call it eagerly and often, don't
  wait for some separate "save" signal that doesn't exist.
- `desk.self.getManifest()` → your own widget's manifest (id, name,
  capabilities, default size).

If you're porting an existing web app/component into a `DefineWidget`
widget, it likely already has its own persistence mechanism (custom
events, a global variable, `localStorage`, whatever the original
project used) — that mechanism does **not** work here (see above: it
won't survive a reload) and porting the widget does not rewire it for
you. You need to explicitly replace it with calls to
`desk.self.getLocalStorage`/`setLocalStorage` above; don't assume the
old approach just keeps working because the rest of the port succeeded.

A few more calls exist for widgets that need them (all require
declaring the matching capability in your own manifest, unlike the
`self.*` calls above, which need none):

- `desk.workspace.getState()` (capability `workspace`) — the current
  Desk's live widget layout.
- `desk.fs.readFile(path)` / `desk.fs.writeFile(path, contents)`
  (capability `fs`) — read/write an arbitrary file on disk.
- `desk.widgets.list()` / `.open(widgetId, opts)` / `.close(instanceId)`
  (capability `widgets`) — inspect/manage placed widget instances.
- `desk.events.subscribe(names)` / `.unsubscribe(names)` /
  `.publish(name, payload)` / `.onMessage(callback)` (capability
  `events`) — send and receive named messages to/from other widgets.
  See "Sending and receiving named messages" below.
- `desk.introspect.snapshot(targetInstanceId)` (capability
  `introspect`) — get a DOM tree snapshot and console log of *another*
  widget instance. See "Inspecting another widget" below.

The calls above are almost always all a `DefineWidget` widget actually
needs.

## Sending and receiving named messages

Desk has its own built-in event message channel: a **mediator**
(a component of Desk itself) that every widget talks to instead of ever
talking to another widget directly. This is how one widget can tell
another "something happened" without either needing to know the other
exists.

- `desk.events.subscribe(names)` → `{ ok: true }` — `names` is an array
  of message names (arbitrary strings you and whatever you want to
  talk to agree on, e.g. `"todo.item_added"`) you want to receive.
- `desk.events.unsubscribe(names)` → `{ ok: true }` — stop receiving
  the given names.
- `desk.events.publish(name, payload)` → `{ ok: true }` — sends a named
  message to every *other* widget instance currently subscribed to
  `name`. `payload` is any JSON-serializable value (or omit it for
  `null`). **You never receive your own publish back**, even if you're
  also subscribed to the same name — this avoids a widget accidentally
  reacting to its own message.
- `desk.events.onMessage(callback)` — registers `callback(name,
  payload, senderInstanceId)`, called for every message you're
  currently subscribed to, for as long as your widget's page stays
  open. Call `subscribe` first, then `onMessage`; there's no way to
  unregister a single callback in this first version (your whole page,
  and its polling, is torn down when the widget closes).

Identity here is always your widget's own **instance** id — the one
specific placed copy of your widget, not "your widget's `keyword`/type"
— the same identity `self.getLocalStorage`/`setLocalStorage` already
use per instance. If two instances of the same widget kind are both
placed, they have entirely independent subscriptions.

Every published message (regardless of which widget sent or received
it) is logged to `MEDIATED-EVENT-LOG.tsv` in the current Desk's
directory — a plain, tab-separated `timestamp / event_name /
sender_instance_id / payload` history of everything sent over the
channel, viewable live in Desk's built-in **Event Log** widget (which
also has a "clear the log" action, with confirmation).

`kind: "python"` widgets can use this same channel too, just not
through this JS API — they get it via a direct Python import instead
(`desk.shell.event_broker.EventSubscription`), the same "REST for html
widgets, direct Python for python widgets" split every other Bridge API
capability already follows.

## Inspecting another widget

`desk.introspect.snapshot(targetInstanceId)` → `{ dom, console }` gets
a snapshot of *another* `kind: "html"` widget instance's own rendered
page: `dom` is a tree (`{ tag, attrs, children }` for an element,
`{ text }` for text content — bounded: max depth 12, max 50 children
per node, attribute/text values truncated to 200 characters) rooted at
that page's `<html>` element; `console` is its recent
`console.log`/`warn`/`error` output (level, message, line, source —
capped at the most recent 200 entries).

**This is the one Bridge API capability that isn't just a manifest
declaration** — the first time your widget asks to inspect a
particular target, the Desk *user* sees a confirmation dialog naming
both widgets and must approve it before you get anything back
(declining gives you a failed call, not empty/fake data). Once
approved, that specific (your widget, that target) pairing won't be
re-prompted again for the rest of the session — asking to inspect a
*different* target still prompts fresh. This is because inspecting
another widget's rendered content and console output is materially
more sensitive than anything else in the Bridge API; declaring the
`introspect` capability in your manifest is necessary but not
sufficient on its own.

`targetInstanceId` is that widget's own instance id (e.g. from
`desk.workspace.getState()`, capability `workspace`, or
`desk.widgets.list()`, capability `widgets`) — not its `kind`/type.
"""

_DISCUSS_PARKING_LOT_ITEM_DOC = """# TempUI DSL: DiscussParkingLotItem

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its shared version number -- this file
just covers the `DiscussParkingLotItem` keyword.

For having Desk kick off a **brand-new** `claude` session specifically
to discuss one item from this project's own `PARKINGLOT.md` (a parked,
not-yet-scoped idea or open question) -- rather than continuing the
current conversation, or expecting the current session to context
-switch onto it.

- The first line is `DiscussParkingLotItem <label>` — `label` is only
  used for the notification text, never sent to the new session.
- The next line is `Line <N>` — the 1-indexed line number, in the
  *current* `PARKINGLOT.md`, where the item you want discussed starts
  (its leading `- **Title**` bullet). Write the **line number**, not
  the item's own text — the new session reads `PARKINGLOT.md` itself to
  get the item's current, full text, rather than being handed a copy of
  it up front. (Don't paste the item's text into this file at all; the
  launch prompt built from a bare line number is short and reliable,
  where splicing in arbitrary, unbounded item text into the new
  session's launch command has caused real launch failures.)

Example:

```
DiscussParkingLotItem A way to end a claude widget's session
Line 533
```

Clicking the resulting notification places a **new** claude widget
with a fresh session (not the one that created this file) — its
initial prompt is the same "you're embedded in Desk" instructions
every claude widget gets, plus an instruction to read that line of
`PARKINGLOT.md` and discuss the item found there, **in this same new
session** (it's told explicitly not to kick off yet another new Desk
discussion of its own, e.g. by writing another `DiscussParkingLotItem`
file, unless the user actually asks it to). This is a one-shot trigger,
not a live-synced document like `Scratch` — there's no `Answer` line,
and once the new session starts there's nothing more Desk does with
this file.
"""

LIGHTNING_ROUND_DOC_FILENAME = "tempui-lightning-round.md"
MARKDOWN_DOC_FILENAME = "tempui-markdown.md"
IMAGE_DOC_FILENAME = "tempui-image.md"
SCRATCH_DOC_FILENAME = "tempui-scratch.md"
CUSTOM_WIDGETS_DOC_FILENAME = "tempui-custom-widgets.md"
DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME = "tempui-discuss-parking-lot-item.md"

# filename -> its static content, for every split-out doc (TODO
# e57ce5f) -- iterated by write_tempui_docs/ensure_docs_current so
# adding a future split file is a one-line addition here, not a new
# call site to remember elsewhere.
SPLIT_DOC_CONTENT: dict[str, str] = {
    LIGHTNING_ROUND_DOC_FILENAME: _LIGHTNING_ROUND_DOC,
    MARKDOWN_DOC_FILENAME: _MARKDOWN_DOC,
    IMAGE_DOC_FILENAME: _IMAGE_DOC,
    SCRATCH_DOC_FILENAME: _SCRATCH_DOC,
    CUSTOM_WIDGETS_DOC_FILENAME: _CUSTOM_WIDGETS_DOC,
    DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME: _DISCUSS_PARKING_LOT_ITEM_DOC,
}


def render_static_doc() -> str:
    """DOC_TEMPLATE with its version placeholder filled in (TODO
    f7b1611) -- plain string substitution, not str.format(): the
    template is free-form Markdown prose that could plausibly contain
    a literal `{`/`}` some day (e.g. a JSON example), which .format()
    would silently misinterpret as a field reference."""
    return DOC_TEMPLATE.replace(_DOC_VERSION_PLACEHOLDER, str(TEMPUI_DOC_VERSION))


def parse_doc_version(text: str) -> int | None:
    """Extracts the integer version from desk-temporary-ui.md's own
    version note (TODO f7b1611) -- None if the note is missing
    entirely (an unversioned file, including every file written before
    this TODO, is always treated as out of date) or malformed."""
    match = _DOC_VERSION_RE.search(text)
    return int(match.group(1)) if match is not None else None


def write_tempui_docs(temp_dir: Path) -> None:
    """Writes desk-temporary-ui.md (its *static* content only -- no
    custom-widgets section; see sync_custom_widgets_doc_section, called
    separately) plus every split-out doc in SPLIT_DOC_CONTENT, fresh
    (TODO e57ce5f). Used both for a brand-new `.desk_temp`
    (TempUiManager.provision) and by ensure_docs_current's refresh
    path below."""
    (temp_dir / DOC_FILENAME).write_text(render_static_doc())
    for filename, content in SPLIT_DOC_CONTENT.items():
        (temp_dir / filename).write_text(content)


def ensure_docs_current(temp_dir: Path) -> None:
    """Refreshes the *whole* tempui doc set in place if stale (TODO
    e57ce5f, generalizing TODO f7b1611 once the docs split across
    multiple files) -- called before opening a Desk (see
    desk.shell.temp_ui_manager.TempUiManager.provision), right
    alongside the analogous check TODO 91b3f42 already does for the
    dynamic custom-widgets section. A no-op if desk-temporary-ui.md
    doesn't exist at all (nothing to refresh -- first creation is
    `provision`'s own job, via write_tempui_docs).

    The main file's version note stands for the *entire* set, per the
    request -- so this refreshes everything (not just the main file)
    if either its version doesn't match, *or* any split file is
    missing (e.g. a user deleted one) -- there's no per-file staleness
    concept to check independently.

    Preserves the main file's custom-widgets section verbatim if
    present (extracted before rewriting, re-appended after) -- "be
    certain not to clobber the DSL extensions." A file that predates
    the custom-widgets feature too (no markers at all) has nothing to
    preserve; it's just fully rewritten, which is safe even in
    isolation since DeskWindow._sync_tempui_doc runs immediately
    afterward in the real startup/Desk-switch flow and inserts a fresh
    section regardless."""
    doc_path = temp_dir / DOC_FILENAME
    if not doc_path.is_file():
        return
    text = doc_path.read_text()
    version_current = parse_doc_version(text) == TEMPUI_DOC_VERSION
    all_split_docs_present = all((temp_dir / filename).is_file() for filename in SPLIT_DOC_CONTENT)
    if version_current and all_split_docs_present:
        return
    custom_section = None
    if CUSTOM_WIDGETS_SECTION_START in text and CUSTOM_WIDGETS_SECTION_END in text:
        start = text.index(CUSTOM_WIDGETS_SECTION_START)
        end = text.index(CUSTOM_WIDGETS_SECTION_END) + len(CUSTOM_WIDGETS_SECTION_END)
        custom_section = text[start:end]
    write_tempui_docs(temp_dir)
    if custom_section is not None:
        doc_path.write_text(doc_path.read_text().rstrip("\n") + "\n\n" + custom_section + "\n")


@dataclass
class TempUiDocument:
    question: str | None = None
    options: list[str] = field(default_factory=list)
    answer: str | None = None


LIGHTNING_ROUND_KEYWORD = "LightningRound"
OPEN_MARKDOWN_KEYWORD = "OpenMarkdown"
OPEN_IMAGE_KEYWORD = "OpenImage"
SCRATCH_KEYWORD = "Scratch"
MARKDOWN_KEYWORD = "Markdown"
DEFINE_WIDGET_KEYWORD = "DefineWidget"
DISCUSS_PARKING_LOT_ITEM_KEYWORD = "DiscussParkingLotItem"
UNANSWERED = "unanswered"

# Every built-in DSL keyword a DefineWidget can't reuse as its own
# invocation keyword (TODO 91b3f42) -- checked at registration, not
# here, but kept as one shared set so it can't drift out of sync with
# the keywords actually recognized above.
RESERVED_TEMPUI_KEYWORDS = frozenset(
    {
        "Question",
        "Option",
        "Answer",
        LIGHTNING_ROUND_KEYWORD,
        "LRItem",
        OPEN_MARKDOWN_KEYWORD,
        OPEN_IMAGE_KEYWORD,
        SCRATCH_KEYWORD,
        MARKDOWN_KEYWORD,
        DEFINE_WIDGET_KEYWORD,
        DISCUSS_PARKING_LOT_ITEM_KEYWORD,
    }
)


@dataclass
class LightningRoundItem:
    description: str
    answer: str | None = None  # None means "unanswered"


@dataclass
class LightningRoundDocument:
    name: str = ""
    prompt: str = ""
    options: list[str] = field(default_factory=list)
    items: list[LightningRoundItem] = field(default_factory=list)


@dataclass
class CustomWidgetDefinition:
    """A tempui-DSL-defined custom widget kind (TODO 91b3f42, the
    `DefineWidget` keyword) -- entirely in-browser (HTML/CSS/JS,
    `kind: "html"`), never Python. `keyword` is both the new DSL
    keyword a later tempui file invokes and the widget catalog id;
    `label` is the human-friendly name shown in the UI (never a UUID or
    the raw `keyword`); `html_b64` is the widget's entire
    implementation -- one self-contained, base64-encoded HTML
    document. `capabilities` (TODO f693275) are the Bridge API
    capabilities (`"workspace"`, `"fs"`, `"widgets"`, `"events"`, ...)
    this widget kind is allowed to use -- same coarse, resource-level
    strings a real `widgets/<id>/widget.json`'s own `capabilities`
    list already uses; defaults to none declared, same as a manifest
    with no `capabilities` key."""

    keyword: str
    label: str
    html_b64: str
    default_size: tuple[int, int] | None = None
    capabilities: list[str] = field(default_factory=list)


def parse_define_widget(text: str) -> CustomWidgetDefinition | None:
    """Extracts a CustomWidgetDefinition from a DefineWidget temp-UI
    file: `DefineWidget<TAB>keyword<TAB>label` (must be the first
    line), an optional `Size<TAB>width<TAB>height` line, zero or more
    `Capability<TAB>name` lines (TODO f693275 -- same shape as `Size`,
    repeatable, collected in file order), and one or more
    `Html<TAB>base64-chunk` lines (concatenated in file order before
    decoding -- decoding itself happens later, in
    desk.custom_widgets.materialize, not here). Returns None if the
    file doesn't start with the DefineWidget keyword, has no keyword of
    its own, or has no Html content at all."""
    lines = text.splitlines()
    if not lines:
        return None
    first = lines[0].split("\t")
    if not first or first[0] != DEFINE_WIDGET_KEYWORD:
        return None
    keyword = first[1].strip() if len(first) > 1 else ""
    if not keyword:
        return None
    label = first[2].strip() if len(first) > 2 else keyword

    size: tuple[int, int] | None = None
    capabilities: list[str] = []
    html_chunks: list[str] = []
    for line in lines[1:]:
        if line.startswith("Size\t"):
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    size = (int(parts[1]), int(parts[2]))
                except ValueError:
                    size = None
        elif line.startswith("Capability\t"):
            name = line.split("\t", 1)[1].strip()
            if name:
                capabilities.append(name)
        elif line.startswith("Html\t"):
            html_chunks.append(line.split("\t", 1)[1])

    if not html_chunks:
        return None
    return CustomWidgetDefinition(
        keyword=keyword,
        label=label,
        html_b64="".join(html_chunks),
        default_size=size,
        capabilities=capabilities,
    )


def detect_temp_ui_kind(text: str, custom_keywords: Collection[str] = ()) -> str:
    """"question" (the original, default type), "lightning_round",
    "open_markdown", "open_image", "scratch", "markdown_content",
    "define_widget", "discuss_parking_lot_item", or (if the file's own
    keyword is a currently-known custom widget -- TODO 91b3f42)
    "custom:<keyword>" -- read from the first non-blank line's
    keyword. Lets a caller
    that's seeing a temp-ui file for the first time (a notification, a
    saved Desk's widget state) know which widget kind to place without
    assuming "question". Named "markdown_content" (not "markdown") to
    stay unambiguous against the "markdown" *widget id* it happens to
    render into (TODO 9743419).

    `custom_keywords` defaults to empty so every existing call site
    that hasn't opted in still behaves exactly as before -- only
    `desk.shell.window.DeskWindow`, which actually tracks the current
    set of registered custom widgets, passes a real one."""
    for line in text.splitlines():
        if line.strip():
            keyword = line.split(None, 1)[0]
            if keyword == LIGHTNING_ROUND_KEYWORD:
                return "lightning_round"
            if keyword == OPEN_MARKDOWN_KEYWORD:
                return "open_markdown"
            if keyword == OPEN_IMAGE_KEYWORD:
                return "open_image"
            if keyword == SCRATCH_KEYWORD:
                return "scratch"
            if keyword == MARKDOWN_KEYWORD:
                return "markdown_content"
            if keyword == DEFINE_WIDGET_KEYWORD:
                return "define_widget"
            if keyword == DISCUSS_PARKING_LOT_ITEM_KEYWORD:
                return "discuss_parking_lot_item"
            if keyword in custom_keywords:
                return f"custom:{keyword}"
            return "question"
    return "question"


def parse_open_markdown(text: str) -> str | None:
    """Extracts the target Markdown path from an OpenMarkdown temp-UI
    file's first line (`OpenMarkdown <path>`) -- same "everything after
    the first space is one opaque value" shape as Question, so a path
    containing spaces doesn't need escaping. Returns None if the file
    doesn't actually start with the OpenMarkdown keyword."""
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if parts[0] == OPEN_MARKDOWN_KEYWORD and len(parts) > 1:
            return parts[1].strip()
        return None
    return None


def parse_open_image(text: str) -> str | None:
    """Extracts the target image path from an OpenImage temp-UI file's
    first line (`OpenImage <path>`) -- identical shape to
    parse_open_markdown. Returns None if the file doesn't actually
    start with the OpenImage keyword."""
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if parts[0] == OPEN_IMAGE_KEYWORD and len(parts) > 1:
            return parts[1].strip()
        return None
    return None


def parse_scratch(text: str) -> tuple[str, str] | None:
    """Extracts `(label, body)` from a Scratch temp-UI file: the first
    line is `Scratch <label>`; every line after it, verbatim (not
    further parsed), is the initial body text. Returns None if the file
    doesn't actually start with the Scratch keyword."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split(None, 1)
    if not parts or parts[0] != SCRATCH_KEYWORD:
        return None
    label = parts[1].strip() if len(parts) > 1 else ""
    body = "\n".join(lines[1:])
    return label, body


def parse_discuss_parking_lot_item(text: str) -> tuple[str, int] | None:
    """Extracts `(label, line_number)` from a DiscussParkingLotItem
    temp-UI file: the first line is `DiscussParkingLotItem <label>`;
    the next non-blank line is `Line <N>`, the 1-indexed line number in
    PARKINGLOT.md where the item to discuss starts. `label` is for
    notification text only; `line_number` is what a new claude session
    is told to go read for itself (TODO 624ff3a -- previously this
    embedded the item's full text instead, which could break the new
    session's launch). Returns None if the file doesn't start with the
    DiscussParkingLotItem keyword, or has no valid `Line <N>` line."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split(None, 1)
    if not parts or parts[0] != DISCUSS_PARKING_LOT_ITEM_KEYWORD:
        return None
    label = parts[1].strip() if len(parts) > 1 else ""
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        line_parts = stripped.split(None, 1)
        if line_parts[0] != "Line" or len(line_parts) < 2:
            return None
        try:
            line_number = int(line_parts[1].strip())
        except ValueError:
            return None
        return label, line_number
    return None


def parse_markdown_tempui(text: str) -> tuple[str, str] | None:
    """Extracts `(label, content)` from a Markdown temp-UI file (TODO
    9743419): the first line is `Markdown <label>`; every line after
    it, verbatim, is the markdown content to render. Same shape as
    parse_scratch -- `label` is for notification text only, never used
    for the eventual saved filename (that's derived from `content`'s
    own first line, at save time). Returns None if the file doesn't
    actually start with the Markdown keyword."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split(None, 1)
    if not parts or parts[0] != MARKDOWN_KEYWORD:
        return None
    label = parts[1].strip() if len(parts) > 1 else ""
    content = "\n".join(lines[1:])
    return label, content


def is_temp_ui_filename(name: str) -> bool:
    try:
        uuid.UUID(name)
        return True
    except ValueError:
        return False


def parse_temp_ui(text: str) -> TempUiDocument:
    doc = TempUiDocument()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        keyword = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        if keyword == "Question":
            doc.question = rest
        elif keyword == "Option":
            doc.options.append(rest)
        elif keyword == "Answer":
            doc.answer = rest
        # Unrecognized keywords are ignored -- forward-compatible with
        # future DSL additions, not an error.
    return doc


def append_answer(path: Path, answer: str) -> str:
    """Appends an Answer line and returns the full resulting file text,
    so a caller can record it for self-write suppression (see
    desk.shell.temp_ui_manager.TempUiManager) without a second read."""
    with path.open("a") as f:
        f.write(f"Answer {answer}\n")
    return path.read_text()


def parse_lightning_round(text: str) -> LightningRoundDocument:
    doc = LightningRoundDocument()
    for line in text.splitlines():
        if not line.strip():
            continue
        if line == LIGHTNING_ROUND_KEYWORD or line.startswith(LIGHTNING_ROUND_KEYWORD + "\t"):
            parts = line.split("\t")
            doc.name = parts[1] if len(parts) > 1 else ""
            doc.prompt = parts[2] if len(parts) > 2 else ""
        elif line.startswith("Option"):
            # Reused verbatim from the Question DSL -- space-separated,
            # not tab-separated, since its value is a single character
            # with no internal spaces to disambiguate.
            parts = line.split(None, 1)
            if len(parts) > 1:
                doc.options.append(parts[1].strip())
        elif line.startswith("LRItem"):
            parts = line.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            raw_answer = parts[2] if len(parts) > 2 else UNANSWERED
            doc.items.append(
                LightningRoundItem(description, None if raw_answer == UNANSWERED else raw_answer)
            )
        # Unrecognized keywords are ignored, same as parse_temp_ui.
    return doc


def record_lightning_round_answer(path: Path, item_index: int, character: str) -> str:
    """Rewrites the item_index-th LRItem line's answer field in place
    (item_index counts only LRItem lines, in file order -- matching
    parse_lightning_round's doc.items indexing) and returns the full
    resulting file text, same self-write-suppression shape as
    append_answer. Every other line, including other LRItem lines, is
    left byte-for-byte untouched."""
    lines = path.read_text().splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if not stripped.startswith("LRItem"):
            continue
        if seen == item_index:
            parts = stripped.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = f"LRItem\t{description}\t{character}{newline}"
            break
        seen += 1
    text = "".join(lines)
    path.write_text(text)
    return text


CUSTOM_WIDGETS_SECTION_START = "<!-- BEGIN: registered custom widgets (auto-generated, do not edit by hand) -->"
CUSTOM_WIDGETS_SECTION_END = "<!-- END: registered custom widgets -->"


def render_custom_widgets_section(entries: list[tuple["CustomWidgetDefinition", str]]) -> str:
    """The dynamic "currently registered custom widgets" section (TODO
    91b3f42) -- every `DefineWidget` definition currently known,
    whether its source is a still-live `.desk_temp` file (`"tempui"`)
    or this Desk's own saved `.desk` file (`"desk"`), so an agent
    reading this doc always sees the real, current set instead of just
    the six built-in DSL keywords documented statically above.
    Delimited by CUSTOM_WIDGETS_SECTION_START/END so
    sync_custom_widgets_doc_section can patch just this section in
    place without touching anything else in the file."""
    lines = [CUSTOM_WIDGETS_SECTION_START, ""]
    if not entries:
        lines.append("*(none registered yet)*")
    else:
        for definition, source in sorted(entries, key=lambda pair: pair[0].label.lower()):
            source_text = (
                "this Desk's saved `.desk` file" if source == "desk" else "a `DefineWidget` tempui file"
            )
            size_text = (
                f"{definition.default_size[0]}x{definition.default_size[1]}"
                if definition.default_size
                else "default"
            )
            lines.append(
                f"- **{definition.label}** -- invoke with `{definition.keyword}`, "
                f"default size {size_text}, defined by {source_text}."
            )
    lines.append("")
    lines.append(CUSTOM_WIDGETS_SECTION_END)
    return "\n".join(lines)


def sync_custom_widgets_doc_section(
    doc_path: Path, entries: list[tuple["CustomWidgetDefinition", str]]
) -> None:
    """Keeps desk-temporary-ui.md's dynamic custom-widgets section
    current (TODO 91b3f42) -- called at startup and whenever a new
    DefineWidget item is registered. Patches the section in place
    (between CUSTOM_WIDGETS_SECTION_START/END) rather than overwriting
    the whole file, so any of the user's own edits elsewhere in the doc
    are never clobbered -- matching this codebase's general "never
    silently overwrite existing content" posture (e.g.
    ensure_gitignore_entry above). A no-op if the doc doesn't exist yet
    at all (nothing to patch into -- the doc's own first-creation path,
    desk.shell.temp_ui_manager.TempUiManager.provision, writes
    DOC_TEMPLATE, and this gets called again once that exists)."""
    if not doc_path.is_file():
        return
    section = render_custom_widgets_section(entries)
    text = doc_path.read_text()
    if CUSTOM_WIDGETS_SECTION_START in text and CUSTOM_WIDGETS_SECTION_END in text:
        before = text.split(CUSTOM_WIDGETS_SECTION_START)[0]
        after = text.split(CUSTOM_WIDGETS_SECTION_END)[1]
        text = before + section + after
    else:
        # Predates this feature (or this is the very first sync right
        # after DOC_TEMPLATE's own first write) -- append once.
        text = text.rstrip("\n") + "\n\n" + section + "\n"
    doc_path.write_text(text)


def _missing_entries(text: str) -> list[str]:
    """Which of GITIGNORE_ENTRIES aren't present yet -- checked
    independently (an existing project that already ignores
    `.desk_temp/` but not `**/__pycache__/`, from before TODO c458012,
    gets just the missing one appended, not a duplicate)."""
    present = {line.strip().rstrip("/") for line in text.splitlines()}
    return [entry for entry in GITIGNORE_ENTRIES if entry.rstrip("/") not in present]


def ensure_gitignore_entry(git_root: Path, ask: Callable[[], bool]) -> None:
    """Adds whichever of GITIGNORE_ENTRIES are missing to `.gitignore`
    (creating the file if it doesn't exist), preceded by a blank line
    and a `# Desk-specific` comment -- in both the create-from-nothing
    and append-to-existing cases (TODO 4716585), so a brand-new file
    created by this path does start with one blank line before the
    comment, a deliberate stylistic choice for consistency, not an
    oversight."""
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    missing = _missing_entries(existing)
    if not missing:
        return
    if not ask():
        return
    # Re-read immediately before writing: ask() can pump a modal
    # dialog's own nested event loop for an arbitrary amount of time,
    # during which something else could already have added the entry
    # -- re-verify against a fresh read rather than blindly overwriting
    # with a now-stale in-memory copy (TODO 4716585).
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    missing = _missing_entries(existing)
    if not missing:
        return
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    block = "\n".join(missing)
    gitignore_path.write_text(f"{prefix}\n{GITIGNORE_COMMENT}\n{block}\n")
