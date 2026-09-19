import re
import shutil
import time
import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path

from desk.git_utils import find_git_root
from desk.installed_jobs import INSTALLED_JOBS_DIRNAME

TEMP_UI_DIRNAME = ".desk_temp"
DOC_FILENAME = "desk-temporary-ui.md"
# **/__pycache__/ covers what running a seeded scripts/todo_item_ids.py
# (TODO c458012) produces the first time it's invoked -- not specific
# to .desk_temp, but bundled under the same "Desk-specific patterns"
# gitignore checkbox since both are provisioned together.
GITIGNORE_ENTRIES = (".desk_temp/", "**/__pycache__/")
GITIGNORE_COMMENT = "# Desk-specific"

# TODO 59c5a70: where a DefineWidget widget's authoring source (see
# "Authoring from real source" in _CUSTOM_WIDGETS_DOC,
# scripts/build_widget.py) lives across its lifecycle -- authored under
# .desk_temp/widgets/<name>/ (gitignored, matching .desk_temp's own
# disposable-support-territory posture) until promoted, at which point
# DeskWindow._on_tempui_promote_requested moves it to
# desk_widgets/<name>/ at the project root (permanent, non-gitignored,
# matching the promoted definition's own move into the .desk file).
CUSTOM_WIDGET_SRC_DIRNAME = "widgets"
PROMOTED_WIDGET_SRC_DIRNAME = "desk_widgets"

# TODO 13f4ad5: where desk.custom_widgets.build_from_source writes a
# source-backed promoted widget's rebuilt-on-demand HTML -- gitignored,
# regenerated fresh every time Desk registers the widget. Defined here
# (not in custom_widgets.py, which already imports from this module)
# so ensure_desk_widgets_gitignore_entry/DESK_WIDGETS_BUILD_GITIGNORE_
# ENTRY below can reference it without an import cycle.
SOURCE_BUILD_CACHE_DIRNAME = ".build"

# TODO 3b1ef3d: shared-components/ (this repo's own root, checked into
# git -- see its own README.md) is the source of truth for a small
# library of reusable, dependency-free UI mini-components for
# DefineWidget/browser-kind widget authors. Mirrored into every
# project's own .desk_temp/shared-components/ on every Desk open/switch
# (sync_shared_components below) -- real multi-file component sources
# (.ts + template.html + README.md per component), so embedding them as
# Python string constants the way SPLIT_DOC_CONTENT/_BUILD_WIDGET_SCRIPT
# do doesn't scale the way it does for one script; a real directory copy
# instead.
SHARED_COMPONENTS_DIRNAME = "shared-components"

# TODO 48e3b39: the app-structure DSL's own schema/parser/codegen
# tool (see app_dsl/README.md at this repo's own root) -- mirrored
# into every project's own .desk_temp/app_dsl/ the same always-fresh
# way SHARED_COMPONENTS_DIRNAME is (sync_app_dsl_tool below), for the
# same reason: real, multi-file, actively-developed Python source,
# not a single script small/stable enough to embed as one string
# constant the way _BUILD_WIDGET_SCRIPT is.
APP_DSL_DIRNAME = "app_dsl"

# desk-temporary-ui.md's *static* main content (DOC_TEMPLATE below) is
# only ever written once, the first time a directory's .desk_temp is
# provisioned -- an older Desk directory otherwise keeps whatever
# stale copy it got at creation time forever, even after this file's
# own content has since improved (a new DSL section, a correction).
#
# TODO 6839365: this used to be tracked with a single, manually-bumped
# integer, TEMPUI_DOC_VERSION (TODO f7b1611) -- see git history before
# this TODO for the old mechanism and its own ~280-line bump-log
# comment, kept immediately above the constant itself. That scheme had
# a real structural problem: it's one global counter, so two
# workstreams bumping it independently on separate branches (e.g. TODO
# 63bfd42 and TODO 4eb3d9e, both starting from version 43 and both
# bumping to "44") collide, and merging silently renumbers one side --
# with nothing recording that it happened. That's exactly what
# happened here: the bump-log comment (and TODO.md's own "bumped to
# 44"/"bumped to 45" prose for those two items) still says 44, two
# behind the real, post-merge 46.
#
# Replaced with **tags** (Tag/generate_tag below): each meaningful
# change to this doc set gets its own tag -- a short, human-written
# summary suffixed with a 6-digit, non-semantic hash generated from
# the tag's creation timestamp, so two tags minted concurrently on
# different branches never collide and there's nothing to reconcile at
# merge time. CURRENT_TAGS is the full set of tags a fully up-to-date
# .desk_temp has -- the tag-based replacement for "the current
# version." A project's own doc set records which tags *it* has seen
# as one `<!-- desk-temporary-ui.md tag: ... -->` comment per tag,
# right under the title (see DOC_TEMPLATE) -- ensure_docs_current
# diffs the two sets, rather than comparing two integers, so "what's
# new" for a given project is always the literal set of tags it's
# missing, never a full historical range it has to re-read from
# scratch (see also TempUiManager._notify_docs_upgraded/
# render_new_tags_digest, which turn that missing set directly into
# the doc-upgrade notification's own content).
#
# A group of tags can later be **collapsed** into one new tag, to keep
# this doc set's own footprint from growing forever: fold the
# collapsed tags' descriptions (in _BREAKING_CHANGES/_NEW_FEATURES
# below) into the new tag's own entry, delete the old entries, remove
# the old tag ids from CURRENT_TAGS and add the new one, and record
# each old id -> new id in TAG_COLLAPSES -- a project that already has
# every tag that got collapsed is then recognized (via
# _canonicalize_tags) as already having the tag they collapsed into,
# so it never shows up as newly missing, and the next time that
# project's doc set is refreshed it's written with the new id, not the
# old ones ("an instance no longer 'has' the removed tags").
#
# TODO 6839365: every version 1-46 from the old scheme was migrated
# once, in bulk, into five coarse decade-bucket tags (version-00 ..
# version-40, each covering ten consecutive old version numbers) --
# not because a decade is a good scope for a *new* tag (a new tag
# should be small and specific, one change), but because that's what
# the old per-version entries already were: dozens of them, most a
# short paragraph, not worth re-litigating individually one by one.
# See plans/tempui-doc-tags.md for the exact mapping. A project that
# only ever had the old integer version tracked (no tag comments at
# all) is migrated the same way, lazily, the next time it's opened --
# see _legacy_version_tags: versions were cumulative, so a project at
# (say) version 25 already implies version-00/version-10, but NOT its
# own version-20 bucket (TODO ee1a474) -- being somewhere inside a
# bucket doesn't mean being at its top, and old version numbers
# weren't reliably unique besides, so a project's own bucket is always
# reported missing rather than assumed already known.
@dataclass(frozen=True)
class Tag:
    """A single tempui doc-set tag (TODO 6839365) -- `id` is what's
    actually stored/compared everywhere (CURRENT_TAGS, a project's own
    doc comments, _BREAKING_CHANGES/_NEW_FEATURES dict keys);
    `summary`/`hash` are kept only for introspection, never compared
    directly."""

    summary: str
    hash: str = ""

    @property
    def id(self) -> str:
        return f"{self.summary} #{self.hash}" if self.hash else self.summary


def generate_tag(summary: str, *, now: float | None = None) -> Tag:
    """Mints a fresh tag: `summary` must be a concise, 10-50 character
    description of the change (raises ValueError otherwise). The
    6-digit hash is derived from `now` (real wall-clock time by
    default; injectable for tests) purely to make the id unique --
    it's not meant to be decoded back into a timestamp, and two tags
    generated in the same millisecond can still collide (astronomically
    unlikely for genuinely separate workstreams in practice, and
    harmless even then beyond a cosmetic duplicate id)."""
    if not 10 <= len(summary) <= 50:
        raise ValueError(f"tag summary must be 10-50 characters, got {len(summary)}: {summary!r}")
    timestamp = now if now is not None else time.time()
    tag_hash = f"{int(timestamp * 1000) % 1_000_000:06d}"
    return Tag(summary=summary, hash=tag_hash)


def _legacy_version_tags(version: int) -> frozenset[str]:
    """Migration path (TODO 6839365, corrected by TODO ee1a474) for a
    project whose doc set predates tag-tracking entirely and only has
    the old integer TEMPUI_DOC_VERSION-era `version: N` comment.
    Versions were cumulative (a project at version 42 had already
    incorporated everything through version 42), so every decade
    -bucket tag *strictly below* `version`'s own bucket is safely
    already known -- but NOT that bucket itself: a bucket covers ten
    version numbers (e.g. version-40 covers 40-49), and being
    somewhere inside it doesn't mean being at its top, so a project at
    version 42 hasn't necessarily seen whatever changed at versions
    43-46. Old version numbers also weren't reliably unique (the exact
    TODO 6839365 root cause: two branches both bumped to "44" on
    different content), so a project's own bucket can never be trusted
    as fully known regardless of which number inside it it reports --
    it's always left out, so it always comes back missing and its real
    changelog content surfaces in the doc-upgrade notification. E.g.
    version 25 -> {version-00, version-10} only, not version-20."""
    bucket = (version // 10) * 10
    return frozenset(f"version-{b:02d}" for b in range(0, bucket, 10))


def _canonicalize_tags(tags: Collection[str]) -> frozenset[str]:
    """Resolves every tag in `tags` through TAG_COLLAPSES (chained, in
    case an already-collapsed tag is collapsed again later) to its
    current, non-collapsed id -- used to compare a project's own
    known-tags set against CURRENT_TAGS without the comparison being
    thrown off by an old id a since-performed collapse retired."""
    result = set()
    for tag in tags:
        current = tag
        seen: set[str] = set()
        while current in TAG_COLLAPSES and current not in seen:
            seen.add(current)
            current = TAG_COLLAPSES[current]
        result.add(current)
    return frozenset(result)


# TAG_COLLAPSES: old tag id -> the tag id it was collapsed into (TODO
# 6839365, see the design comment above) -- empty until the first real
# collapse happens.
TAG_COLLAPSES: dict[str, str] = {}

# CURRENT_TAGS: every tag a from-scratch .desk_temp is created with --
# the tag-based replacement for the old single TEMPUI_DOC_VERSION
# integer's role as "the current baseline." Order is chronological
# (oldest first); it doesn't affect staleness comparisons (a plain
# set, via CURRENT_TAG_SET below), only display order (newest-first)
# in _BREAKING_CHANGES/_NEW_FEATURES and the doc-upgrade notification.
CURRENT_TAGS: tuple[str, ...] = (
    "version-00",
    "version-10",
    "version-20",
    "version-30",
    "version-40",
    "tagged changelog, no version numbers #252348",
    "rust installed jobs + declared state needs #739624",
    "job-to-job invocation via RUN_INSTALLED_JOB #181226",
)
CURRENT_TAG_SET: frozenset[str] = frozenset(CURRENT_TAGS)
_DOC_TAGS_PLACEHOLDER = "{{TEMPUI_DOC_TAGS}}"
_TAG_LINE_RE = re.compile(r"<!-- desk-temporary-ui\.md tag: (.+?) -->")
_LEGACY_VERSION_RE = re.compile(r"<!-- desk-temporary-ui\.md version: (\d+)")

DOC_TEMPLATE = """# Temporary UI

<!-- desk-temporary-ui.md tags -- do not edit these lines by hand; Desk uses them to detect which tempui doc-set tags this project has already seen, and to refresh this file's own main content (and the other tempui-*.md files it references) when it's missing any. -->
{{TEMPUI_DOC_TAGS}}

This directory holds "temporary UI" files: a lightweight way for an
agent (or any external process) to ask a question through Desk's own
canvas instead of a terminal prompt.

Each file is named with a bare UUID (e.g.
`550e8400-e29b-41d4-a716-446655440000`, no extension). Desk watches
this directory: a newly-created file shows up as a clickable
notification in the app's upper-right corner; clicking it places a new
widget on the canvas, centered in the current view. There are ten
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
- `Job` — run a one-time script with real widget-context capabilities
  (notably Bridge API access), without building a full `DefineWidget`/
  `widgets/<id>/` registration for it. See
  [tempui-jobs.md](./tempui-jobs.md).
- `DeskProc` — run a one-time Python script with real, in-process
  access to Desk's own live shell (e.g. reveal or screenshot a placed
  widget instance), notified distinctly from every other kind above.
  See [tempui-desk-proc.md](./tempui-desk-proc.md).

Every file named above lives in this same directory.

A few more files live here too, but aren't DSL file types (nothing
writes one directly): [tempui-breaking-changes.md](./tempui-breaking-changes.md)
and [tempui-new-features.md](./tempui-new-features.md) — the complete,
unfiltered changelogs of this doc set itself, one section per tag, every
tag Desk has ever introduced, the same for every project regardless of
which tags that particular project has already seen (see the tag
comments right under this file's own title for *this* project's own
list). A tag's section simply existing in these two files is not itself
a signal that it's new to you — most of them aren't. If you're picking
up a project that was built against an older Desk, a doc-upgrade
notification (if you got one) is the actual, project-specific signal: it
names exactly which tags are new to this project, with their own
descriptions included directly in the notification itself — read that
first, and only open these two files yourself if you want the fuller,
permanent record instead of re-reading this whole doc set and diffing it
against memory. There's also
`build_widget.py` — not a doc at all, but a ready-to-run script; see
"Authoring from real source" in `tempui-custom-widgets.md`. Likewise
`build_job_or_desk_proc.py` — packages a plain script into a
ready-to-drop `Job`/`DeskProc` tempui file (base64-encoding and
chunking it for you); see either of those files' own docs for how to
invoke it. There's also
[tempui-installed-jobs.md](./tempui-installed-jobs.md) — Installed
Jobs, a durable, versioned alternative to `Job` for a script you expect
to run repeatedly: install it once from real source at
`desk-installed-jobs/<name>/main.py` (one approval prompt), then run
it as many times as you like via an MCP tool call with no further
prompt. Not a dropped-tempui-file DSL keyword like the ones above --
installation happens via an MCP tool call against a directory you
already wrote, never via a file dropped in this directory.

## Environment variables

If you're running as the agent behind a `claude`/`Claude (Desk)`
widget (as opposed to a script invoked via `Job`/`DeskProc`/an
Installed Job), a few static, launch-time facts about your own placed
widget instance are available as environment variables rather than
folded into your prompt -- check for these directly (e.g. `echo
$DESK_WIDGET_INSTANCE_ID`) rather than assuming one is absent just
because this document doesn't call it out by name at launch:

- `DESK_WIDGET_INSTANCE_ID` -- this widget instance's own instance id
  (the same id used internally as your session id for `--resume`/
  reconnection across a Desk reload).

## Questions for the user: use QUESTIONS.md, not this DSL

If you have an open-ended question *for the user* that's blocking a
specific TODO.md item -- something you're genuinely blocked on and
need their input to resolve, as opposed to a single quick
multiple-choice decision (`Question`/`LightningRound` below are for
that) -- write it to `QUESTIONS.md` at the project root instead of
creating a file here. This mechanism is specifically for questions
tied to one or more TODO.md items -- there's no supported way to add a
general, free-standing question with no TODO id attached.

Each entry's heading **must start with the literal word `TODO`**,
followed by one or more backtick-wrapped TODO.md item ids (separated
by `/` if more than one), then a colon and a short summary:

```
## TODO `9743419`: What should the save-a-copy filename be?
```

A heading in any other shape (no leading `TODO`, an id that isn't
backtick-wrapped, etc.) is not recognized at all -- it's silently
treated as ordinary prose above the first real entry, not as a
question, with nothing shown to the user. Below the heading: the
question's own text, then a trailing `(Answer: )` placeholder line for
the user to fill in (leave it empty; never write your own guess into
it). If `QUESTIONS.md` doesn't exist yet, create it with a `#
Questions with optional answers` title line first.

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
# carry their own tag comments -- CURRENT_TAGS covers the whole set
# (see the comment on that constant). Grouped by feature area, not
# strictly one keyword per file: OpenMarkdown/Markdown already
# cross-reference each other; DefineWidget/invocation/promotion/the
# Bridge API are one cohesive feature, not four unrelated ones.

_LIGHTNING_ROUND_DOC = """# TempUI DSL: LightningRound

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
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
directory's own overview and its current set of tags -- this file
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
directory's own overview and its current set of tags -- this file
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
directory's own overview and its current set of tags -- this file
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
directory's own overview and its current set of tags -- this file
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

**A `DefineWidget` file only registers the new widget *kind* — it does
not, by itself, place an instance of it on the canvas, whether the
keyword is brand-new or you're only redefining an already-registered
one (e.g. re-saving one to fix a mistake).** Always use a separate,
keyword-only tempui file afterward to actually see it (see "Invoking a
defined widget" below) — the same two-step dance every use of a
`DefineWidget` keyword requires, with no auto-placed exception.

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
- `StateSchema<TAB>key<TAB>type_expr` — optional, repeatable (TODO
  af7898b). Declares a validated schema for one `desk.state.*` key --
  `type_expr` is a TypeScript type expression string (see "Shared,
  project-scoped state" below for the supported subset and what
  declaring a schema actually does). Requires the `state` capability
  too, the same as any other `desk.state.*` access.
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

## Authoring from real source (TypeScript + a build script)

Hand-writing a `DefineWidget` file's inline `<script>` as plain JS with
markup assembled via `innerHTML` works, but it's a poor fit for a project
whose own conventions ask for more (e.g. strict-mode TypeScript,
`<template>`/`<slot>` instead of string-built HTML — see this project's
own `CLAUDE.md` if it has such rules). Author once from real source, then
mechanically repackage it into the format above with
`.desk_temp/build_widget.py` (generated here the same way this doc set
itself is, kept fresh automatically rather than seeded once) any time
it changes — never hand-edit the generated `DefineWidget` file itself.

Per widget, a source directory at `.desk_temp/widgets/<name>/` —
deliberately **not** under the project's own top-level `widgets/`, since
*that* directory is scanned by Desk's own widget discovery, which expects
every `widget.json` there to have a `kind` of `"python"` or `"html"`;
this directory's `widget.json` has a different shape and would break
that scan if placed there instead. `.desk_temp` is already
Desk-specific/gitignored support territory (see `TEMP_UI_DIRNAME`
elsewhere in this doc), which is exactly the right home for a
not-yet-promoted widget's source too. Four files:

- `<name>.ts` — the widget's logic as a custom element (`class Foo
  extends HTMLElement`), in normal strict TypeScript. No knowledge of
  base64/tempui/Desk belongs in this file at all — it just clones a
  `<template>`'s `.content` into a shadow root; the only Desk-specific
  surface it touches is the Bridge API below, guarded by `if
  (window.desk)` so the file still works opened as a plain page.
- `widget.html` — the eventual self-contained document, with a
  `<template id="<name>-template">` holding the real markup and a scoped
  `<style>`, a `<script>` whose entire content is the one-line marker
  comment `/* BUILD:COMPILED_JS */`, and the `<name-tag></name-tag>`
  element instantiation.
- `tsconfig.json` — whatever strictness the project wants; must set
  `compilerOptions.outDir`. For a widget split across more than one
  `.ts` file (e.g. a shared base class alongside the widget's own
  subclass), also set a top-level `"files"` array listing them in
  the order they must be concatenated in — base classes before the
  subclasses that `extends` them. These files compile as global
  scripts (no `import`/`export`), so load order matters exactly like
  script tags on a page; `build_widget.py` respects this array when
  present instead of an alphabetical directory sort, which cannot be
  relied on to put a base class first. A `tsconfig.json` with no
  `"files"` key (the common, single-file case) is unaffected.
- `widget.json` — `{"keyword", "label", "width", "height"}`, exactly the
  fields a `DefineWidget`/`Size` line above needs, plus an optional
  `"capabilities": [...]` (a list of the same coarse, resource-level
  strings a real `widgets/<id>/widget.json`'s own `capabilities` list
  already uses -- `workspace`, `fs`, `widgets`, `events`, ...) — the
  build script emits one `Capability<TAB>name` line per entry, so
  `widget.json` is the one place a defined widget's capabilities need
  to be declared, the same way a real `kind: "python"`/`"html"`
  widget's manifest already works. Omit it entirely for a widget that
  needs none (the default). Also accepts an optional `"state_schema":
  {"<key>": "<type expression>", ...}` (TODO af7898b) declaring which
  `desk.state.*` keys this widget kind's schema covers -- the build
  script emits one `StateSchema<TAB>key<TAB>type_expr` line per entry,
  the same real widget.json field a `kind: "python"`/`"html"` widget
  declares one in. See "Shared, project-scoped state" below.

Then `python3 .desk_temp/build_widget.py .desk_temp/widgets/<name>`
compiles it (`tsc -p <dir>`), concatenates the compiled JS, substitutes
it into `widget.html`'s marker, base64-encodes the result, and writes a
fresh `DefineWidget` tempui file under `.desk_temp/` — printing the
path it wrote. That file also records a `SourcePath` line naming
`<name>`'s directory (TODO 13f4ad5) — Desk uses this durable record to
find the real source directory later, rather than guessing it back
from the `DefineWidget` line's own `keyword`, which is almost never
the same string as this (kebab-case) directory name.

Once promoted (see "Promoting a defined widget to the Desk" below), the
source directory moves to `desk_widgets/<name>/` at the project root —
a permanent, non-gitignored location, matching the promoted
definition's own move into the `.desk` file. **Do not** re-run
`build_widget.py` against it for further edits — that produces a
`DefineWidget` tempui file, and a promoted widget's `.desk` file entry
is no longer sourced from tempui files at all, so nothing would ever
pick it up. Instead, just edit the files under `desk_widgets/<name>/`
directly (`<name>.ts`, `widget.html`, ...) and save — Desk watches
that directory itself and marks every already-placed instance
`[STALE]`, exactly like a still-`.desk_temp`-sourced `DefineWidget`'s
own live edits already do; click it to rebuild (`tsc`, same as before)
and reload.

## Reusable UI components

`.desk_temp/shared-components/` holds a small library of ready-made,
dependency-free UI components for exactly this kind of real-source
authoring — check here before building something non-trivial from
scratch, whether that's a UI control (a color picker) or a whole
widget's file lifecycle (a title-to-path, auto-load/auto-save document
editor). Refreshed automatically alongside the rest of `.desk_temp`,
same as `build_widget.py` above — never a stale one-time copy. Each
component lives in its own subdirectory with its own `README.md`
explaining what it does and how to use it — either import its file
directly, or copy+paste+modify it into your own widget file, whichever
suits the component. Importing a base class a widget's own file
`extends` needs its own `tsconfig.json` `"files"` entry ahead of the
widget's own file (see "Authoring from real source" above) so
`build_widget.py` concatenates it first.

If your widget is actually several wired-together components (a
multi-pane layout, an event-wiring table between them, shared
app-level state) rather than one self-contained custom element,
`.desk_temp/app_dsl/` is a separate, real (if smaller-scoped so far)
tool for exactly that -- see `app_dsl/README.md` (same directory) for
the DSL format. It supports two output modes: `--mode=module` (real ES
modules, for a standalone build outside Desk) and `--mode=global`
(plain global scripts, no `import`/`export` at all -- for feeding into
this `build_widget.py` pipeline above, the same concatenation
convention "Authoring from real source" already uses for a multi-file
`DefineWidget` source). `--mode=global` requires your component/
handler source to also avoid module syntax -- see `app_dsl/README.md`
for the full constraint.

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
the `.desk` file becomes the sole remaining source of truth. If the
widget was authored from real source (see "Authoring from real source"
above), its `.desk_temp/widgets/<name>/` source directory moves to
`desk_widgets/<name>/` at the project root at the same time, for the
same reason — a promoted widget is now a permanent part of the
project, so its source shouldn't keep living in `.desk_temp` either.
Invocation (see above) keeps working exactly the same afterward,
promoted or not.

A source-backed promoted widget (TODO 13f4ad5) does **not** keep a
baked copy of its compiled HTML in the `.desk` file — instead Desk
rebuilds it fresh from `desk_widgets/<name>/` into a gitignored
`desk_widgets/<name>/.build/` cache every time it registers this
widget (startup, Desk switch, or right after promotion itself), the
same compile-and-package step `build_widget.py` runs by hand. This
means `tsc` (and anything else that widget's own build needs) must be
available wherever a Desk containing it is subsequently opened, not
just on the machine it was authored/promoted on — see
`tempui-breaking-changes.md`. A hand-authored, inline-only
`DefineWidget` (no source directory) is unaffected: there's nothing to
rebuild from, so it keeps today's baked-`html_b64` behavior.

## The Desk Bridge API — what your widget's own JS can call

A `DefineWidget` widget's HTML document runs inside a real embedded
browser page with one extra thing every other web page doesn't have:
`window.desk`, a small JS client automatically injected before your
own code runs. It's how your widget talks back to Desk itself —
notably, **it's the recommended way to persist your widget's own
state across a Desk reload**: `window.desk.self.getLocalStorage()`
/`.setLocalStorage()`'s data lives inside the project's own `.desk`
file, so it travels with the project (copy/share the `.desk` file and
your widget's saved state comes with it). Each instance's page *does*
also get its own real, persistent browser storage now (cookies,
`localStorage`, `IndexedDB` — a separate profile per widget instance,
under `.desk_temp/`), so it's no longer true that nothing else
persists — but that storage is tied to this specific project checkout
(not portable the way the `.desk` file is) and is deleted outright the
moment the widget instance is permanently removed from the canvas.
Prefer `getLocalStorage`/`setLocalStorage` for anything you actually
want to keep.

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
  capabilities, default size, content hash, and the current Desk's own
  `directory` — the last two exist specifically so you can tell which
  version of your widget's code is currently registered, and construct
  a correct project-relative path yourself if you ever need to, without
  declaring the `fs` capability just to find out where you are).
- `desk.self.setSubtitle(text)` → `{ ok: true }` — puts your own
  instance's state into its own titlebar, next to its kind's static
  label (e.g. `"My Widget — some-document.md"`). Every instance of
  your widget's kind otherwise shows the identical label, so this is
  how one particular instance shows *which* thing it's currently
  pointed at. Call it again whenever that changes; pass `null` (or an
  empty string) to clear it back to the bare label. Not persisted —
  call it again after restoring your own state (e.g. right after
  `getLocalStorage`) on every fresh page load, the same way you'd
  re-render your own content.

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
`self.*` calls above, which need none). **If what you actually want is
"tell other widgets something happened," reach for `desk.events.*`
first** — every other call in this list is scoped to your own widget or
to one other widget you already know the id of, but `events` is the one
built for genuine cross-widget signaling:

- `desk.events.subscribe(names)` / `.unsubscribe(names)` /
  `.publish(name, payload)` / `.onMessage(callback)` (capability
  `events`) — send and receive named messages to/from other widgets.
  See "Sending and receiving named messages" below.
- `desk.workspace.getState()` (capability `workspace`) — the current
  Desk's live widget layout.
- `desk.state.get(key)` / `.set(key, value, edit)` / `.getHistory(key,
  limit)` (capability `state`) — a shared, project-scoped key/value
  store any widget can read or write. See "Shared, project-scoped
  state" below.
- `desk.fs.readFile(path)` / `desk.fs.writeFile(path, contents)`
  (capability `fs`) — read/write an arbitrary file on disk. A relative
  `path` resolves against the current Desk's own directory (not any
  particular process's working directory); an absolute path is used as
  -is. `writeFile` creates any missing parent directories first (like
  `mkdir -p`) — a widget author never needs to separately ensure a
  target directory exists before writing into it. This is
  same-directory file I/O, not a way to signal another widget — see the
  `events` callout above if that's what you're after.
- `desk.widgets.list()` / `.open(widgetId, opts)` / `.close(instanceId)`
  (capability `widgets`) — inspect/manage placed widget instances.
- `desk.introspect.snapshot(targetInstanceId)` (capability
  `introspect`) — get a DOM tree snapshot and console log of *another*
  widget instance. See "Inspecting another widget" below.
- `desk.filetypes.get()` / `.set(entries)` (capability `filetypes`) —
  read/edit the file type registry (which widget(s) can view, edit,
  git-diff, consume, or produce which file type, by extension and/or
  MIME type).
  `get()` also subscribes you to future edits, delivered as a
  `"desk.file_type_registry.updated"` message via `desk.events
  .onMessage` (declare the `events` capability too if you want to
  receive it) — one call does both "read" and "start watching," not
  two separate ones.
- `desk.editor.openOrScrap(path)` (capability `editor`) — open an
  appropriate editor for `path` (falling back to the built-in text
  Editor for a genuinely text file with no registered editor), or
  place an explanatory Scratch note if nothing can open it — the same
  service a `kind: "python"` widget reaches via `current_context
  .get_editor_or_scrap_opener()`. A relative `path` resolves against
  the current Desk's own directory, same as `desk.fs.*`.
- `desk.popups.show(title, message, buttons, default)` (capability
  `popups`) — shows a desk-internal popup (a small `WidgetFrame` placed
  on the canvas, not a real OS window) with `message` and one button
  per label in `buttons`; blocks until the Desk user clicks one (or
  returns `null` if dismissed via its close button/Escape). `default`
  (optional) names which button is the pre-selected/Enter-triggered
  one. The same service a `kind: "python"` widget reaches via
  `current_context.get_popup_opener()`. **Use this, not the browser's
  own `alert()`/`confirm()`/`prompt()`**, for any alert or confirmation
  your widget shows — those are real, separate OS-level dialogs with no
  connection to Desk's own canvas chrome (wrong styling, no
  zoom/pan-aware positioning, and blocking in a way that can behave
  surprisingly inside an embedded `ChromiumWidget`).
- `desk.transforms.run(transformId, input, config)` (capability
  `transforms`) — runs a transform (a separate entity from a widget:
  converts data of one named type into another, e.g. a Mermaid
  diagram's source into SVG) and returns `{ output, error }` (exactly
  one is non-`null`). `config` is optional, only meaningful to a
  transform that declares `has_config: true`. The same service a
  `kind: "python"` widget reaches via
  `current_context.get_transform_runner_blocking()`.
- `desk.installedJobs.run(name, configPath)` (capability
  `installed_jobs`) — runs an already-Installed Job (see
  [tempui-installed-jobs.md](./tempui-installed-jobs.md)) by name,
  same as the agent-facing `desk_run_installed_job` MCP tool — no
  approval prompt either way, since a declared capability is itself
  the trust boundary here (the same way it already is for every other
  call in this list). `configPath` is optional (`null`/omitted if not
  given); returns `{ ok, stdout, stderr, traceback }`. **Bounded to
  120 seconds**, unlike the MCP tool's unbounded wait — this is a
  synchronous HTTP request/response and can't wait forever; a job
  expected to genuinely run longer belongs on the agent/MCP path
  instead (the run itself isn't cancelled by the timeout, only this
  call's own wait for its result is).

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

## Shared, project-scoped state

Desk also keeps a shared, project-scoped key/value store — every widget
with the `state` capability can read or write any key, with no
per-widget ownership. Use this instead of hand-rolling your own
cross-widget persistence scheme (e.g. one widget writing to a file the
other polls); it also gets you change notification and a short history
for free. The built-in **State Manager** widget (TODO `6330249`) gives
a Desk user a live view/edit UI over every registered schema and the
data stored under it — reach for that instead of building your own
inspector when you just need to see or tweak what's currently there.

- `desk.state.get(key, typeHint)` → `{ value, edit }` — the current
  value for `key`, and the `edit` that was passed alongside the write
  that produced it (see below). A key nothing has ever written to
  returns `{ value: null, edit: null }`, not an error. `typeHint` is
  optional and only meaningful for a **non-validated** key (see below)
  — ignored entirely for a key that currently has a schema.
- `desk.state.set(key, value, edit, typeHint)` → `{ ok: true }` —
  writes `value` (any JSON-serializable value) as the new current value
  for `key`. `edit` is optional (omit or pass `null`) and is never
  interpreted by Desk — it's stored and handed back verbatim from
  `get`/`getHistory`, meant for widgets that want to describe *what
  changed* (e.g. a structured patch or a human-readable description)
  alongside the new full value, without Desk needing to understand that
  description's format at all. `typeHint` is optional, and only
  meaningful for a non-validated key.
- `desk.state.getHistory(key, limit)` → `{ history: [{ value, edit },
  ...] }` — up to the most recent `limit` `(value, edit)` pairs written
  to `key`, **newest first**. Desk keeps only the 50 most recent writes
  per key (older ones are dropped as new ones arrive); asking for a
  `limit` larger than what's kept just returns everything available,
  never an error. Omit `limit` for the full kept history.

Every `set` also publishes `desk.state.changed` with payload `{ key,
value, edit }` over the same `desk.events` channel described above —
subscribe to it (`desk.events.subscribe(["desk.state.changed"])`,
capability `events`, in addition to `state`) to react to another
widget's writes live rather than polling `get`. As with any
`desk.events` message, you never receive your own `set` echoed back to
you.

### Validated vs. non-validated keys (TODO af7898b)

A key is **validated** if some widget currently declares a schema for
it (a `state_schema` entry in that widget's own manifest — see
`StateSchema<TAB>key<TAB>type_expr` above for a `DefineWidget`, or the
`"state_schema"` field of a real `widgets/<id>/widget.json`), or if a
**top-level schema file** declares it (see below), and **non-validated**
otherwise — this is a property of the key itself, not of any individual
`get`/`set` call.

- A schema (`type_expr`) is a string in a small, intentionally
  -constrained subset of TypeScript type syntax: primitives (`string`,
  `number`, `boolean`, `null`), literal unions (`"a" | "b"`, `1 | 2`),
  arrays (`string[]`, `number[][]`), and simple object shapes (`{ a:
  string; b?: number }`, extra keys beyond those declared are always
  allowed). No generics, tuples, or intersections in this version.
- **`set` on a validated key**: `value` is checked against the active
  schema. A mismatch is a real error (the call fails, nothing is stored
  or published) — this holds even if *you* didn't declare the schema
  yourself; whichever widget's manifest currently owns `key`'s schema
  governs every write to it. `typeHint` is ignored.
- **`set`/`get` on a non-validated key**: `typeHint` (the same small
  type-expression syntax as a schema) is optional and purely
  call-site-local — `set` best-effort-coerces `value` to it before
  storing; `get` best-effort-coerces the *returned* value only (the
  stored value itself is untouched). Coercion never fails the call —
  a hopeless coercion just returns the value unchanged. Omitting
  `typeHint` entirely (the common case) stores/returns exactly what was
  given, no coercion at all.
- **Declaring a schema that conflicts with an already-active one for
  the same key** means your widget doesn't load at all — no placement,
  not even a normal placement notification. Instead, a clickable
  notification appears explaining the conflict, and
  `self.getManifest()`'s response gains a `desk_widget_loading_errors`
  array with the same message, for as long as the conflict is still
  live.
- **Top-level schema files** (TODO `9aef267`) declare a schema
  independent of any widget's manifest — for state that should have a
  canonical schema without tying its lifecycle to any one widget's own
  placement. A schema file is a plain JSON file, `{"<key>": "<type
  expression>", ...}` (the same syntax as a manifest's own
  `state_schema`), placed in either of two watched locations:
  `.desk_temp/schemas/` (ephemeral — created automatically alongside
  the rest of `.desk_temp`, not git-tracked), or `./desk-schemas/` (a
  real, git-tracked project-root directory Desk never creates itself —
  create it yourself and it's picked up automatically, no restart
  needed). Only `*.json` files are read; the filename itself carries no
  meaning beyond that extension, so name it for what it holds (e.g.
  `document-state.json`). A key declared this way is **permanently
  enforced** from the moment the file is picked up — unlike a
  tempui-placed widget's own schema, it's never tied to any widget
  being placed and never goes dormant. Editing the file live-updates
  its registrations; deleting it clears them. A conflicting file (or a
  file conflicting with an already-active widget-declared schema) gets
  the same clickable-notification treatment as a widget-vs-widget
  conflict above, just with no `desk_widget_loading_errors`-equivalent
  to write into (there's no manifest to attach it to) — the live
  notification is authoritative while the conflict lasts.

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
directory's own overview and its current set of tags -- this file
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

_JOBS_DOC = """# TempUI DSL: Job

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `Job` keyword.

For running a **one-time script** with real widget-context
capabilities -- notably Bridge API access, which nothing else lets you
reach outside a real `kind: "html"` widget's own JS -- without
building a full `DefineWidget` (a reusable, promotable widget *kind*)
or a `widgets/<id>/` registration just for one throwaway task. If what
you actually want is a reusable widget *kind* placeable many times, or
something that stays running (a background service, a long,
checkpointed pipeline), a `Job` is the wrong tool -- it's a single
one-shot run, no more.

- The first line is `Job<TAB>kind<TAB>summary` -- `kind` is `python`
  or `html`; `summary` is shown in the notification and the placed Job
  Runner widget, never executed.
- Zero or more `Capability<TAB>name` lines -- only meaningful for
  `kind: "html"` (ignored, but harmless, for `kind: "python"`): the
  same coarse Bridge API capability names a `DefineWidget`'s own
  `Capability` lines use (`workspace`, `fs`, `widgets`, `events`,
  `filetypes`, `editor`, `popups`, `transforms`, `introspect`,
  `installed_jobs` -- see "The Desk Bridge API" in
  `tempui-custom-widgets.md` for what each one actually grants).
  Declare only what your script actually calls
  -- an undeclared capability's Bridge call gets a real HTTP 403, not
  silent success.
- One or more `Script<TAB>base64-chunk` lines -- your script's entire
  source, base64-encoded (chunk it across several `Script` lines for a
  long script; they're concatenated in file order before decoding,
  the same convention `DefineWidget`'s own `Html` lines use). For
  `kind: "html"`, this is a complete, self-contained HTML document
  (same shape as a `DefineWidget`'s own content) -- your page's JS gets
  `window.desk.*` injected automatically, scoped to exactly the
  `Capability` lines you declared above. For `kind: "python"`, this is
  a plain Python script, executed directly (no `desk` package import
  needed beyond what you'd already use in any other Python code in
  this environment) -- there is no capability scoping for `kind:
  "python"` at all; it runs with the same access any other code
  already running in this process has.

Clicking the resulting notification places a **Job Runner** widget,
showing your declared summary, a "View Code" button (opens your
script's own source in a real editor), and a "Start" button --
**nothing runs until Start is clicked**. Once started, Start becomes
disabled and stays that way (even across a Desk reload) -- a `Job` is
a one-shot run, not a repeatable tool; write a new `Job` file for a
second run.

**"Done" means the page finished loading, not that every async Bridge
call your script's own JS kicked off has resolved.** There is no
generic way for Desk to know an arbitrary web page's own async work
has actually finished -- if your `kind: "html"` script fires off a
Bridge call and returns immediately, the Job Runner widget may show
"Done" before that call's effect is visible elsewhere. If you need to
know a specific call actually completed, have your own script make
that visible some other way (e.g. render its own result in the page),
rather than relying on the Job Runner's status display as a strict
completion signal.

You don't have to hand-write the base64/`Script` line(s) below
yourself -- `.desk_temp/build_job_or_desk_proc.py` (mirroring
`build_widget.py`'s convenience for `DefineWidget`) builds a real `Job`
file for you from a plain script file:

```
python3 .desk_temp/build_job_or_desk_proc.py job python "Delete .desk_temp/jobs/ entries older than 7 days" cleanup.py
python3 .desk_temp/build_job_or_desk_proc.py job html "Talk to the Bridge API" widget.html --capability workspace
```

prints the path of the tempui file it wrote, ready to be picked up the
same as any other `.desk_temp/` file.

Example (`kind: "python"`, script shown decoded/unwrapped for
readability -- the real file's `Script` line(s) would carry it
base64-encoded):

```
Job	python	Delete .desk_temp/jobs/ entries older than 7 days
Script	<base64-encoded script text>
```

```python
import time
from pathlib import Path

cutoff = time.time() - 7 * 24 * 60 * 60
jobs_dir = Path(".desk_temp/jobs")
for entry in jobs_dir.iterdir() if jobs_dir.is_dir() else []:
    if entry.stat().st_mtime < cutoff:
        print(f"would remove {entry}")
```
"""

_DESK_PROC_DOC = """# TempUI DSL: DeskProc

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `DeskProc` keyword.

For running a **one-time Python script** with real, in-process access
to Desk's own live shell -- reveal a specific already-placed widget
instance (the same action as clicking its titlebar eye button), take a
real pixel screenshot of one, or list what's currently placed --
instead of just a `kind: "html"` widget's own capability-scoped Bridge
API, which has no equivalent of any of that. If your script only needs
Bridge API access (`workspace`, `fs`, `state`, ...), reach for `Job`
(see `tempui-jobs.md`) instead -- that's the general-purpose one-time
-script mechanism; `DeskProc` exists specifically for the subset of
actions that require touching Desk's shell directly, which a
sandboxed `kind: "html"` page structurally cannot do. Like `Job`, this
is a single one-shot run, not a reusable, promotable widget *kind*.

- The first line is `DeskProc<TAB>summary` -- `summary` is shown in the
  notification and the placed Desk Proc Runner widget, never executed.
- One or more `Script<TAB>base64-chunk` lines -- your script's entire
  source, base64-encoded (chunk it across several `Script` lines for a
  long script; concatenated in file order before decoding, the same
  convention `Job`'s own `Script` lines and `DefineWidget`'s own `Html`
  lines already use). Always a plain Python script -- there is no
  `html`-kind variant of `DeskProc` at all. Executed directly (no
  `desk` package import needed beyond what you'd already use in any
  other Python code in this environment) -- there is no capability
  scoping here, the same "no sandboxing" trust level `Job`'s own
  `python` kind already has. "View Code is the only review step" for
  this mechanism too.

Your script's exec namespace also gets a `deskproc` global -- the
*documented*, safe way to act on Desk's own shell from your script
(which runs on a background thread; touching a Qt widget directly from
there is unsafe, so use these methods rather than trying to reach into
`desk.shell.window`/`desk.shell.canvas` yourself):

- `deskproc.reveal_widget(instance_id: str) -> bool` -- zooms/pans the
  Workspace Canvas so the given placed widget instance fills the view,
  the same action as clicking that instance's own titlebar eye button.
  Returns whether a matching instance was found.
- `deskproc.screenshot_widget(instance_id: str, path: str) -> bool` --
  saves a real PNG screenshot of that instance's own placed frame
  (titlebar and content, exactly as it looks on the canvas) to `path`.
  A relative `path` resolves against the current Desk's own directory,
  same as `desk.fs.writeFile`; missing parent directories are created
  automatically. Returns whether the instance was found and the file
  was saved successfully.
- `deskproc.screenshot_desk(path: str) -> bool` -- saves a real PNG
  screenshot of the whole Workspace Canvas viewport (not any native
  window chrome around it) to `path`, same path-resolution rules as
  above.
- `deskproc.list_widget_instances() -> list[dict]` -- the current
  Desk's live placed-widget layout (instance ids, widget kind,
  position, size) -- the same data `desk.workspace.getState()` already
  exposes to a `kind: "html"` widget with the `workspace` capability,
  provided here so a script has a real way to discover an instance id
  rather than needing one handed in from outside.

Clicking the resulting notification places a **Desk Proc Runner**
widget, showing your declared summary, a "View Code" button (opens
your script's own source in a real editor), and a "Start" button --
**nothing runs until Start is clicked**. Once started, Start becomes
disabled and stays that way (even across a Desk reload) -- a
`DeskProc` is a one-shot run, not a repeatable tool; write a new
`DeskProc` file for a second run.

**This notification looks different from every other tempui kind's
own notification on purpose** -- a distinct border color and a bold
"DESK PROC" caption above the summary -- specifically so a Desk Proc
(real, in-process shell access) is never mistaken at a glance for an
ordinary tempui placement (a widget instance, a question, ...).

You don't have to hand-write the base64/`Script` line(s) below
yourself -- `.desk_temp/build_job_or_desk_proc.py` (mirroring
`build_widget.py`'s convenience for `DefineWidget`) builds a real
`DeskProc` file for you from a plain Python script file:

```
python3 .desk_temp/build_job_or_desk_proc.py desk-proc "Reveal and screenshot the Editor widget" reveal_and_shoot.py
```

prints the path of the tempui file it wrote, ready to be picked up the
same as any other `.desk_temp/` file.

Example (script shown decoded/unwrapped for readability -- the real
file's `Script` line(s) would carry it base64-encoded):

```
DeskProc	Reveal and screenshot the Editor widget
Script	<base64-encoded script text>
```

```python
result = deskproc.screenshot_widget("some-instance-id", "screenshots/editor.png")
print(f"screenshot saved: {result}")
```
"""

_INSTALLED_JOBS_DOC = """# Installed Jobs

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
covers Installed Jobs, which are **not** a tempui-DSL file type (there
is no dropped-file keyword for this -- see that overview's own "a few
more files" paragraph).

A `Job` (see `tempui-jobs.md`) is a one-shot script, re-approved every
single time you drop a fresh tempui file for it. An **Installed Job**
is the durable, versioned alternative for a script you expect to run
*repeatedly*: install it once (one approval prompt), then run it as
many times as you like with no further prompt at all.

## Installing

Two kinds, told apart purely by which file is present:

- **`python`** -- write your script to
  `desk-installed-jobs/<name>/main.py` (project-root-relative, a
  sibling of `.desk_temp/`, not inside it -- this is real, durable
  source, not disposable cache). You can add other files alongside it
  and `import` them from `main.py` -- the job's own directory is put on
  `sys.path` for the duration of a run. There is no capability list and
  no `html` variant: `main.py` runs with the same unrestricted,
  no-sandboxing in-process access any other Python code already running
  in this process has (the same trust level a `Job`'s own
  `kind: "python"` already has).
- **`rust`** -- write a real Cargo project to
  `desk-installed-jobs/<name>/` (`Cargo.toml` + `src/`), same
  project-root-relative, durable-source placement. For
  computationally-intensive work, or anything that wants the GPU -- see
  "Rust jobs and the GPU" below. Same trust level as `python`: no
  sandboxing, your `Cargo.toml` can depend on whatever crates it needs
  (`cargo build` fetches and compiles them, no separate install step).
  Having both `main.py` and `Cargo.toml` present (or neither) is a
  install-time error, not a guess.

Then call the `desk_install_job` MCP tool with `name` (the directory
name under `desk-installed-jobs/`). This computes a version hash over
your job's current source and registers it -- **this is the only
approval prompt you'll see for this job.** For a `rust`-kind job, this
does **not** build it yet (a first build can be slow -- see below); it
only validates and registers.

## Running

Call the `desk_run_installed_job` MCP tool with `name` and, optionally,
`config_path` -- a path to a config file your job wants to read. A
relative `config_path` resolves against the current Desk's own
directory. There's no fixed default filename Desk invents on your
behalf -- if you want a config file, put it wherever makes sense for
your job and pass its path; it should generally live under
`.desk_temp/` (ephemeral, per-project scratch space) unless there's a
specific reason for it to live elsewhere. How your job reads it depends
on its kind:

- **`python`**: the `CONFIG_PATH` global (a plain string, or `None` if
  you didn't pass one).
- **`rust`**: the `DESK_JOB_CONFIG_PATH` environment variable, only set
  at all when a `config_path` was actually given (read it as
  `std::env::var("DESK_JOB_CONFIG_PATH").ok()`).

**This never prompts for approval.** That's the entire point of
installing a job instead of dropping a fresh `Job` file every time you
want to run it. It does mean the tool refuses to run if your job's
on-disk source no longer matches the version that was actually
approved at install time (someone edited it after installing) -- call
`desk_install_job` again first in that case, which re-approves the new
version. For a `rust`-kind job, `cargo`'s own `target/` build output
doesn't count as "source" for this check -- rebuilding never requires
re-approval.

The tool returns `{"ok": ..., "stdout": ..., "stderr": ..., "traceback": ...}` as JSON --
your job's captured stdout/stderr, plus a Python traceback if a
`python`-kind job raised (for `rust`, `traceback` is just a plain
"process exited with code N" note when `ok` is `false` -- a compiled
binary has no Python traceback to give back; put your own diagnostics
on stderr).

## Rust jobs and the GPU

A `rust`-kind job is built with `cargo build --release` the first time
it's run (not at install time -- a first build can take a while, see
below), then cached: a later run only rebuilds if a source file
(`Cargo.toml`/`Cargo.lock`/anything under `src/`) is newer than the
last compiled binary. The compiled binary is then run directly as a
real subprocess, `cwd` set to the job's own directory -- no timeout on
either the build or the run, so a genuinely long, computationally
-heavy job is free to actually take that long.

For GPU access, use the [`wgpu`](https://crates.io/crates/wgpu) crate
(add it to `[dependencies]` in your `Cargo.toml`) -- confirmed directly
working on this machine: a real WGSL compute shader was authored,
dispatched, and its output read back correctly against the real GPU
(`Metal` backend). `wgpu` is cross-platform (Metal/Vulkan/DX12/GL) and
is this ecosystem's most widely used GPU-compute crate, but it's a
recommendation, not a requirement -- your `Cargo.toml` can depend on
anything on crates.io; `cargo build` fetches and compiles it, no
separate install step. A minimal, confirmed-working shape:

```rust
let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
    backends: wgpu::Backends::all(),
    ..Default::default()
});
let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
    power_preference: wgpu::PowerPreference::HighPerformance,
    compatible_surface: None,
    force_fallback_adapter: false,
})).expect("no adapter");
let (device, queue) = pollster::block_on(adapter.request_device(&Default::default(), None))
    .expect("no device");
// device.create_shader_module(...) with a WGSL compute shader,
// device.create_compute_pipeline(...), dispatch, then read a result
// buffer back -- see wgpu's own compute example for the full pipeline
// setup (bind groups, buffers, encoder, submit).
```

## Declaring what a job needs (`desk.state.*`)

A `python`-kind job's own code runs inside this same process, so it
can, incidentally, reach this app's live Python state via whatever it
imports -- undocumented, fragile, and not something to rely on. A
`rust`-kind job is a genuinely separate OS process and structurally
*can't* reach any of that at all. Either way, the supported way for a
job to receive data it doesn't already have is to **declare** which
"Shared, project-scoped state" (see `tempui-custom-widgets.md`) keys it
needs, and let Desk resolve them for you:

Add `desk-installed-jobs/<name>/job.json`:

```json
{"needs": ["some_state_key", "another_state_key"]}
```

On every run, Desk resolves each listed key via the same lookup
`desk.state.get` itself uses, and writes `{"some_state_key": {"value":
..., "edit": ...}, "another_state_key": {"value": ..., "edit": ...}}`
to a fresh file (a key nothing has ever `set()` comes back as `{"value":
null, "edit": null}`, same as `desk.state.get` itself) -- handed to your
job the same way `config_path` is:

- **`python`**: the `NEEDS_PATH` global (a plain string, or `None` if
  `job.json` is absent or declares no `needs`).
- **`rust`**: the `DESK_JOB_NEEDS_PATH` environment variable, only set
  when there's actually something to read.

No `job.json` at all is the common case and needs no change -- every
job written before this existed keeps working exactly as it did.

## Invoking another job from a `python`-kind job

A `python`-kind job's own code gets one more global: `RUN_INSTALLED_JOB(name,
config_path=None) -> {"ok", "stdout", "stderr", "traceback"}` -- the
exact same shape `desk_run_installed_job` itself returns. Call it to
run another already-installed job (`python`- or `rust`-kind, uniformly
-- your own code never needs to know or care which) as part of your
own job's work, e.g. a `python`-kind job doing scene setup that wants
to hand its GPU-heavy inner loop off to a `rust`-kind job:

```python
result = RUN_INSTALLED_JOB("gpu_inner_loop", config_path="/path/to/config.json")
if result["ok"]:
    print(result["stdout"])
else:
    print("nested job failed:", result["stderr"])
```

Same no-reapproval/stale-source-refusal rules apply to the nested job
as to any other run -- a failure there (not installed, or its source
changed since its own install) comes back as `{"ok": false, ...}`,
never as a Python exception raised into your own code. Nesting is
unrestricted -- a `python`-kind job invoked this way gets its own
`RUN_INSTALLED_JOB` too, so it can invoke a further job in turn, to
whatever depth you actually write.

**Only `python`-kind jobs can invoke another job.** A `rust`-kind job
has no equivalent -- it's a real, separate OS process with no path
back into Desk's own state to make this call at all. If you need a
`rust`-kind job's own inner work broken into steps, structure that
inside the Rust program itself.

## Running from a `kind: "html"` widget

An unrelated `kind: "html"` widget (declaring the `installed_jobs`
capability) can run an Installed Job too, via
`desk.installedJobs.run(name, configPath)` -- see "The Desk Bridge
API" in `tempui-custom-widgets.md` for its exact call shape. Same
no-reapproval-on-run/stale-hash-refusal behavior as the MCP tool
above, but bounded to 120 seconds (a synchronous HTTP request/response
can't wait forever the way an agent's own `await` can) -- a job
expected to run longer than that belongs on the MCP/agent path
instead.

## The Installed Jobs widget

Placeable like any other widget: lists every installed job (name, kind,
+ version hash), with a "View Source" button (opens each of the job's
own files in a real editor widget -- a `rust`-kind job's `target/`
build output is skipped, not opened one file at a time) and an
"Uninstall" button (behind a confirmation) per row. Uninstalling only
removes the registration -- your source under
`desk-installed-jobs/<name>/` is left on disk, so installing the same
name again later just re-approves it.
"""

# TODO 6839365: reverse-chronological-by-tag changelogs for the whole
# tempui doc set -- _BREAKING_CHANGES/_NEW_FEATURES below are dicts
# (tag id -> markdown body, no leading heading), not opaque strings:
# this is what lets render_new_tags_digest build a real excerpt for
# exactly the tags a given project is missing, instead of a pointer
# telling the reader to go read the whole file themselves.
# _render_changelog_doc turns each dict into the actual
# tempui-breaking-changes.md/tempui-new-features.md file content
# (SPLIT_DOC_CONTENT below), one `## <tag id>` section per entry,
# newest-first per CURRENT_TAGS order.
#
# Going forward: any new tag that reflects a breaking change or a new
# capability should add a matching entry to whichever of these two
# dicts applies (or both), in the same commit that adds the tag to
# CURRENT_TAGS -- see also development-process.md's "When working on
# Desk itself" section, which makes this an explicit instruction for
# anyone working on Desk, not just a habit to remember from this
# comment alone.
#
# TODO 6839365: versions 1-46 from the old TEMPUI_DOC_VERSION scheme
# were migrated in bulk into five decade-bucket tags (version-00 ..
# version-40) -- see plans/tempui-doc-tags.md for why buckets-of-ten
# rather than a real per-tag migration, and _legacy_version_tags for
# how an old project's own single `version: N` comment maps onto these
# same buckets. Every original bullet is preserved verbatim, nested
# under its own `### Version N` sub-heading where a bucket holds more
# than one old version -- not rewritten/summarized, to avoid silently
# dropping something in translation.
_BREAKING_CHANGES: dict[str, str] = {
    "version-40": """### Version 44
- "Authoring from real source"'s post-promotion instructions changed:
  do **not** re-run `build_widget.py` against `desk_widgets/<name>/`
  for further edits anymore -- it never actually worked there (it
  writes a `DefineWidget` tempui file, and a promoted widget isn't
  sourced from tempui files at all, so nothing ever picked the rebuilt
  file up, silently). Just edit `desk_widgets/<name>/`'s own files
  directly and save instead -- see the Version 44 new-features entry.

### Version 43
- A promoted, source-backed `DefineWidget` (see "Authoring from real
  source" in `tempui-custom-widgets.md`) no longer bakes its compiled
  `html_b64` into the `.desk` file at promote time -- it's rebuilt
  fresh into a gitignored `desk_widgets/<name>/.build/` cache every
  time Desk registers it (startup, Desk switch, or right after
  promotion) instead. This means `tsc` (and anything else that
  widget's own build needs) must be available wherever a Desk
  containing one is subsequently opened, not just the machine it was
  originally authored/promoted on. A hand-authored, inline-only
  `DefineWidget` (no source directory) is unaffected -- it still bakes
  `html_b64` exactly as before.
""",
    "version-10": """### Version 18
- `DefineWidget` no longer auto-places one instance the first time a
  brand-new keyword is registered (this reverts the Version 12 new
  -features entry below) -- it now behaves like every other tempui
  kind always has: registering a kind never places an instance by
  itself, whether the keyword is brand-new or you're only redefining
  an existing one. If your project/agent had come to rely on the
  auto-placed instance, invoke the keyword explicitly afterward (a
  separate tempui file whose entire first line is just the keyword --
  see "Invoking a defined widget" in `tempui-custom-widgets.md`).

### Version 17
- The "Authoring from real source" build script moved from a one-time
  -seeded `scripts/build_widget.py` to `.desk_temp/build_widget.py`,
  refreshed automatically alongside this doc set from now on instead
  of going stale forever after a single copy. If your project has an
  existing `scripts/build_widget.py`, switch to invoking
  `.desk_temp/build_widget.py` instead (it always has the current
  content; `scripts/build_widget.py` will not be updated further).

### Version 14
- `DefineWidget` widget authoring source moved from a project-root
  `custom_widget_src/<name>/` to `.desk_temp/widgets/<name>/` (see
  "Authoring from real source" in `tempui-custom-widgets.md`). Move any
  existing `custom_widget_src/<name>/` directory to
  `.desk_temp/widgets/<name>/` accordingly -- `scripts/build_widget.py`
  itself needs no change, it already takes an arbitrary directory
  argument. Promoting a widget (the `[TEMPUI]` titlebar button) now also
  moves its source directory again, to `desk_widgets/<name>/` at the
  project root.
""",
}

_NEW_FEATURES: dict[str, str] = {
    "job-to-job invocation via RUN_INSTALLED_JOB #181226": """- A `python`-kind Installed Job's own code can now invoke another
  Installed Job -- `python`- or `rust`-kind, uniformly, your own code
  never needs to know or care which -- via a new global,
  `RUN_INSTALLED_JOB(name, config_path=None) -> {"ok", "stdout",
  "stderr", "traceback"}` (the exact shape `desk_run_installed_job`
  itself returns). A failure in the nested job (not installed, or its
  source changed since its own install) comes back as `{"ok": false,
  ...}`, never a raised exception. Nesting is unrestricted -- an
  invoked `python`-kind job gets its own `RUN_INSTALLED_JOB` too. Only
  `python`-kind jobs can invoke another job -- a `rust`-kind job has no
  equivalent, being a real, separate OS process with no path back into
  Desk's own state to make this call at all. See "Invoking another job
  from a `python`-kind job" in `tempui-installed-jobs.md`.
""",
    "rust installed jobs + declared state needs #739624": """- Installed Jobs (`tempui-installed-jobs.md`) gained a second kind,
  `rust`: `desk-installed-jobs/<name>/Cargo.toml` (+ `src/`) instead of
  `main.py`, built on demand (`cargo build --release`, cached until
  source changes) and run as a real subprocess -- for
  computationally-intensive work, or anything that wants the GPU (the
  `wgpu` crate is confirmed working on this machine, Metal backend --
  see the doc's own "Rust jobs and the GPU" section for a minimal
  example). Kind is detected from which file is present, nothing new
  to pass when installing/running.
- Both kinds can now declare what they need from the shared
  `desk.state.*` store instead of a `python`-kind job's only previous
  option (an undocumented, fragile `import` into this process's own
  live state, unavailable at all to a `rust`-kind job's separate
  process): an optional `desk-installed-jobs/<name>/job.json` with
  `{"needs": [<state key>, ...]}` gets each key's current value
  resolved and handed to the job -- the `NEEDS_PATH` global for
  `python`, the `DESK_JOB_NEEDS_PATH` environment variable for `rust`.
  See "Declaring what a job needs" in `tempui-installed-jobs.md`.
""",
    "tagged changelog, no version numbers #252348": """- Replaced `TEMPUI_DOC_VERSION` (a single, manually-bumped integer) with
  a tag-based scheme: a tag is a short, human-written summary plus an
  appended 6-digit, non-semantic hash generated from its creation
  timestamp (`generate_tag`), so two tags minted concurrently on
  different branches never collide the way two `TEMPUI_DOC_VERSION`
  bumps from the same base version once did in practice. A
  `.desk_temp` project now tracks which tags it has seen (a set), not
  a single version number; groups of tags can later be collapsed into
  one new tag (`TAG_COLLAPSES`) to keep this changelog's own footprint
  bounded. The doc-upgrade notification (when a project is missing
  tags this Desk already has) is now a single notification -- never
  more than one, and never zero
  unless there's genuinely nothing new -- and clicking it opens a
  Markdown widget with the real descriptions of exactly the missing
  tags, not a static pointer telling you to go read this file
  yourself. Every version 1-46 from the old scheme was migrated in
  bulk into five decade-bucket tags, `version-00` (versions 1-9)
  through `version-40` (40-46) -- see those tags' own entries above/
  below for the changes they cover.
""",
    "version-40": """### Version 46
- `desk_run_pipeline`'s pipeline DSL gains a `map` stage: `map +| verb1
  | verb2 |+` -- everything between the `+|`/`|+` delimiters is itself
  a full sub-pipeline in this same syntax (including a nested `map`).
  `map` requires a list/array piped value, runs the sub-pipeline once
  per item (each item, not the outer pipeline's own value, is what the
  sub-pipeline's first stage receives), and recombines the per-item
  results into a new list. The first item whose sub-pipeline doesn't
  succeed fails the whole `map` stage, naming which item and why -- no
  partial results.

### Version 45
- A new `desk_run_pipeline` MCP tool: runs a pipe-chained verb DSL
  pipeline (a single `|`-separated string of built-in verb calls --
  `reveal_widget`, `screenshot_widget`, `screenshot_desk`,
  `list_widget_instances`, `open_image` -- plus a `py:`-prefixed
  base64-encoded Python-expression escape hatch) in one round trip,
  each stage receiving the previous stage's real return value, instead
  of chaining several separate MCP tool calls by hand. Not a tempui-DSL
  file type -- see the tool's own description for its syntax.

### Version 44
- A promoted, source-backed widget's `desk_widgets/<name>/` source
  directory is now watched directly for changes. Editing it (and
  saving) marks every already-placed instance `[STALE]` -- the same
  titlebar button a still-`.desk_temp`-sourced `DefineWidget`'s own
  live edits already show -- with no rebuild step needed first;
  clicking it asks for confirmation and, if confirmed, rebuilds
  (`tsc`) and reloads. See "Authoring from real source" in
  `tempui-custom-widgets.md`.

### Version 43
- A source-backed `DefineWidget`'s authoring source directory is now
  recorded durably at build time (a new `SourcePath` line / the
  `source_path` field), surviving promotion, save/reload, and even a
  restart -- fixes a bug where promoting a widget silently failed to
  relocate its source directory whenever the real (kebab-case)
  directory name didn't match the DSL `keyword` (typically CamelCase),
  which is the common case. See "Authoring from real source" in
  `tempui-custom-widgets.md`.

### Version 42
- A new "Environment variables" section: the agent behind a `claude`/
  `Claude (Desk)` widget can now read its own placed widget instance
  id directly from its environment as `DESK_WIDGET_INSTANCE_ID`,
  instead of having no supported way to learn it. A static,
  launch-time fact only -- not a live query; the in-process Desk MCP
  server's own tools (e.g. `desk_reveal_widget`) remain the way to
  answer anything dynamic (current placements, live state).

### Version 41
- A new Bridge API capability, `installed_jobs`:
  `desk.installedJobs.run(name, configPath)` lets a `kind: "html"`
  widget run an already-Installed Job too (see `tempui-installed-jobs.md`),
  the same as the agent-facing `desk_run_installed_job` MCP tool --
  no approval prompt either way (a declared capability is itself the
  trust boundary here). Bounded to 120 seconds (unlike the MCP tool's
  unbounded wait) since this is a synchronous HTTP request/response --
  a job expected to run longer belongs on the MCP/agent path instead.
  `Job`'s own closed capability-name list gained `installed_jobs` too.

### Version 40
- Installed Jobs: a durable, versioned alternative to the ephemeral
  `Job` mechanism for a script you expect to run repeatedly. Write real
  source to `desk-installed-jobs/<name>/main.py`, then call the new
  `desk_install_job` MCP tool once (the only approval prompt) --
  afterward, `desk_run_installed_job(name, config_path=None)` runs it
  as many times as you like with **no further approval prompt**, and
  refuses to run if the on-disk source no longer matches the version
  that was actually installed. A new "Installed Jobs" widget lists what
  you've installed, with per-row "View Source" and "Uninstall" (source
  is kept on disk either way). Not a tempui-DSL file type -- see
  `tempui-installed-jobs.md`.
""",
    "version-30": """### Version 39
- A new authoring convenience script,
  `.desk_temp/build_job_or_desk_proc.py` (mirroring `build_widget.py`):
  packages a plain script into a ready-to-drop `Job`/`DeskProc` tempui
  file, doing the base64-encode-and-chunk work for you instead of
  hand-writing it every time. No DSL/API change -- `Job`/`DeskProc`
  files themselves are unchanged, this just removes the authoring
  ceremony. See `tempui-jobs.md`/`tempui-desk-proc.md`.

### Version 38
- A new `DeskProc` tempui DSL keyword: a one-time Python script with
  real, in-process access to Desk's own live shell -- reveal a placed
  widget instance (the same action as its titlebar eye button),
  screenshot one (or the whole canvas) as a real PNG, or list what's
  currently placed, via a curated `deskproc.*` object injected into the
  script's own exec namespace. A close sibling of `Job` (same tempui
  -file -> notification -> placed one-shot-runner-widget -> Start
  -button shape), but its own keyword: no `html`-kind variant, and its
  notification is deliberately styled differently (a distinct border
  color plus a bold "DESK PROC" caption) so it's never mistaken for an
  ordinary tempui placement notification at a glance. See
  `tempui-desk-proc.md`.

### Version 37
- `desk.popups.show(...)`'s own doc now explicitly warns against using
  the browser's raw `alert()`/`confirm()`/`prompt()` for an
  alert/confirmation instead -- always use `desk.popups.show`, the
  desk-internal popup. No API change, just a stronger warning after a
  real bug where the Python-side equivalent mistake (a raw
  `QMessageBox`) rendered as a detached macOS window.

### Version 36
- A `desk.state.*` schema can now also be declared "top-level,"
  independent of any widget's manifest: a plain JSON file, `{"<key>":
  "<type expression>", ...}`, at `.desk_temp/schemas/` (ephemeral,
  auto-created) or `./desk-schemas/` (git-tracked, create it yourself
  and it's picked up automatically). Permanently enforced from the
  moment it's picked up, live-updated on edit, cleared on delete. See
  "Validated vs. non-validated keys" in `tempui-custom-widgets.md`.

### Version 35
- `desk.state.*` keys can now be validated: declare a schema for a key
  via a `state_schema` field in a real `widgets/<id>/widget.json` (or a
  `StateSchema<TAB>key<TAB>type_expr` `DefineWidget` line), and every
  `set` to that key is checked against it. `get`/`set` also gained an
  optional `typeHint` parameter, meaningful only for a non-validated
  key, for call-site-local best-effort coercion. See "Validated vs.
  non-validated keys" in `tempui-custom-widgets.md`. A widget declaring
  a schema that conflicts with an already-active one for the same key
  fails to load entirely (a clickable notification explains why, and
  `self.getManifest()` gains a `desk_widget_loading_errors` array with
  the same message).

### Version 34
- New `desk.state.*` Bridge API calls (capability `state`): a shared,
  project-scoped key/value store any widget can read (`get`,
  `getHistory`) or write (`set`), with change notification via the
  existing `desk.events` channel (a `desk.state.changed` message on
  every `set`) and a bounded (50 most recent per key), latest-first
  history. See "Shared, project-scoped state" in
  `tempui-custom-widgets.md`. No schema/type checking on state keys in
  this version -- values are opaque JSON.

### Version 33
- `app_dsl`'s `build.py` gained a `--mode=global` output mode
  (alongside the existing, still-default `--mode=module`) -- plain
  global scripts, no `import`/`export` at all, for feeding into
  `build_widget.py`'s own `DefineWidget` packaging pipeline (which
  needs non-module scripts to concatenate). Requires your own
  component/handler source to also avoid module syntax when used --
  see `app_dsl/README.md`. Closes the gap Version 32's own entry
  below left open.

### Version 32
- New `.desk_temp/app_dsl/` tool -- a schema + parser + codegen tool
  for a multi-component widget's own wiring/layout/event-table code
  (generalized from a hand-written SPA structure), not a new tempui
  DSL keyword. See `app_dsl/README.md` for the DSL format. Generates
  real TypeScript ES modules for a standalone build; a Desk-widget
  build target isn't wired into `build_widget.py`'s own packaging
  pipeline yet (see `PARKINGLOT.md`).

### Version 31
- New `Job` tempui DSL keyword -- run a one-time script with real
  widget-context capabilities (notably Bridge API access for a
  `kind: "html"` Job, previously unreachable outside a real
  `kind: "html"` widget's own JS) without building a full
  `DefineWidget`/`widgets/<id>/` registration for it. See
  `tempui-jobs.md` for the file format, the capability list, and an
  important caveat about what "Done" actually means for a `kind:
  "html"` Job.

### Version 30
- New `desk.self.setSubtitle(text)` Bridge API call -- lets a widget
  instance put its own state (e.g. which document it's editing) into
  its own titlebar, alongside the existing `getManifest`/
  `getLocalStorage`/`setLocalStorage`. `text` composes with the
  titlebar's kind label as `"<label> — <text>"`, before the
  `[EXTERNAL]` suffix; `null`/empty clears it back to the bare label.
  Needs no capability declaration (same as `getLocalStorage`/
  `setLocalStorage`) and isn't persisted -- call it again on every
  fresh page load once your own state is restored.
""",
    "version-20": """### Version 29
- `.desk_temp/build_widget.py` now warns to stderr, at the start of
  every run, if a `scripts/build_widget.py` also exists in the
  project -- a copy from before this mechanism moved to `.desk_temp/`
  (TODO `029047b`) can silently defeat a fix already shipped here
  (e.g. capabilities emission, Version 22) with nothing telling the
  project the copy being run might be the stale one. Not an error --
  the build still proceeds either way.
- `.desk_temp/build_widget.py` also now deletes any other
  `DefineWidget` file for the same widget keyword immediately after a
  successful build, instead of leaving one leftover file behind per
  rebuild forever (a real, if narrow, risk: a startup/Desk-switch
  re-scan of `.desk_temp` is alphabetical, not chronological, so
  several stale same-keyword files left behind could make an old one
  "win" again).

### Version 28
- "Questions for the user" corrected: the documented `QUESTIONS.md`
  heading format (`## <short summary>`) never actually matched what
  the real parser requires. The real, required shape starts with a
  literal `TODO`, followed by one or more backtick-wrapped TODO.md
  item ids, then a colon and summary -- see
  `desk-temporary-ui.md`'s own "Questions for the user" section (same
  directory) for a full example. This mechanism has always been
  scoped to questions blocking a specific TODO.md item, not general
  free-standing ones -- a heading in any other shape (including the
  old documented example) is silently not recognized as a question at
  all.

### Version 27
- "The Desk Bridge API" section's storage guidance corrected:
  previously stated flatly that no browser storage (cookies,
  `localStorage`, `IndexedDB`) persists a `kind: "html"` widget's page
  across a reload or a Desk restart, and that
  `getLocalStorage`/`setLocalStorage` was the *only* way to persist
  state. That's no longer accurate -- each widget instance now gets
  its own real, persistent browser profile, so that storage does
  survive a reload/restart for as long as the instance stays placed.
  `getLocalStorage`/`setLocalStorage` is still the *recommended*
  mechanism, though: its data lives in the project's own `.desk` file
  (portable -- travels if the file is copied/shared), unlike the
  per-instance profile storage, which is tied to this specific
  project checkout and is deleted outright the moment the widget
  instance is permanently removed.

### Version 26
- `.desk_temp/build_widget.py` now concatenates a multi-file widget's
  compiled `.js` output in the order `tsconfig.json`'s own top-level
  `"files"` array lists them (base classes before subclasses), instead
  of plain alphabetical filename order -- previously, a subclass whose
  filename happened to sort before its base class's threw
  `ReferenceError: Cannot access '<Base>' before initialization` at
  runtime. Add a `"files"` array (in author-declared order) to opt in;
  a `tsconfig.json` with no `"files"` key is unaffected (unchanged,
  alphabetical-order behavior, correct for the common single-file
  widget). See "Authoring from real source" above.

### Version 25
- New `shared-components/document-editor-base` entry: a base class
  (`DocumentEditorBase<Doc>`) for a title-to-path, auto-load/auto-save
  file-backed document editor -- see its own `README.md`. Unlike
  `hsv-color-picker`, this one specifically recommends copying its
  source directly into your own widget file rather than keeping it as
  a separate one (a real class-inheritance load-order hazard with this
  project's own `build_widget.py` -- see the "Reusable UI components"
  section above).

### Version 24
- `desk.fs.writeFile` now creates any missing parent directories before
  writing (like `mkdir -p`) — a write to a not-yet-existing directory
  previously rejected silently, with no visible error.

### Version 23
- New "Reusable UI components" section: `.desk_temp/shared-components/`
  holds a small library of ready-made, dependency-free UI components
  for "Authoring from real source" (starting with `hsv-color-picker`),
  refreshed automatically alongside the rest of this doc set. Import a
  component's file directly, or copy+paste+modify it into a widget's
  own source -- both are intended, accepted ways to use them.

### Version 22
- "Authoring from real source"'s `widget.json` now supports an
  optional `"capabilities": [...]` key -- `.desk_temp/build_widget.py`
  reads it and emits one `Capability<TAB>name` line per entry into the
  generated `DefineWidget` tempui file automatically. Previously this
  had to be hand-edited into the *generated* file after every build
  (easy to forget, silently dropped otherwise, with no error surfaced
  anywhere beyond whatever Bridge API call the missing capability broke
  at runtime). Omit the key entirely for a widget that needs no
  capabilities -- unchanged, the default.

### Version 21
- `desk.transforms.run(transformId, input, config)` (capability
  `transforms`): runs a transform -- a new entity, separate from a
  widget: converts data of one named type into another
  (`input_type -> output_type`), e.g. a Mermaid diagram's source into
  SVG -- and returns `{ output, error }` (exactly one is non-`null`).
  `config` is optional, only meaningful to a transform that declares
  `has_config: true`.

### Version 20
- `desk.filetypes.get()`/`.set(entries)` (capability `filetypes`): file
  type registry entries can now declare a `"git-diff"` role alongside
  the existing `view`/`edit`/`consume`/`produce` ones -- a built-in Git
  Diff Viewer widget (`git_diff`) is the unconditional fallback for
  this role (git diff is meaningful for any file type, not just
  specific extensions), so registering a `git-diff` handler is only
  needed to override that default for a particular type.
""",
    "version-10": """### Version 19
- `desk.popups.show(title, message, buttons, default)` (capability
  `popups`): shows a desk-internal popup -- a small `WidgetFrame`
  placed on the canvas, not a real OS window -- with `message` and one
  button per label in `buttons`; blocks until the Desk user clicks one
  (or returns `null` if dismissed via its close button/Escape).
  `default` (optional) names the pre-selected/Enter-triggered button.

### Version 16
- `desk.editor.openOrScrap(path)` (capability `editor`): open an
  appropriate editor for `path`, or place an explanatory Scratch note
  if nothing can open it -- the same fallback service a `kind:
  "python"` widget reaches via `current_context
  .get_editor_or_scrap_opener()`.
- `desk.filetypes.get()`/`.set(entries)` (capability `filetypes`,
  introduced back while `TEMPUI_DOC_VERSION` was still 14 but not
  documented here or version-bumped until now): read/edit the file
  type registry; `get()` also subscribes you to future edits.

### Version 14
- See `tempui-breaking-changes.md`'s own Version 14 entry -- the
  authoring-source relocation is breaking, not additive.

### Version 13
- `desk.self.getManifest()` now also returns `content_hash` (the
  currently-registered definition's content hash, for a `DefineWidget`
  widget) and `directory` (the current Desk's own directory).
- `desk.fs.readFile`/`writeFile`'s relative-path handling was fixed:
  a relative path now resolves against the current Desk's own
  directory rather than the server process's ambient working
  directory (an absolute path was, and still is, used as-is --
  nothing changes for existing correct callers).
- `desk.events.*` given top billing in `tempui-custom-widgets.md`'s
  Bridge API capability list, as the preferred mechanism for
  cross-widget signaling (a documentation reordering, not a behavior
  change).

### Version 12
- `DefineWidget` now auto-places one instance the first time a
  genuinely new keyword is registered from a live-added tempui file
  (re-registering an already-known keyword, or a bulk rescan at
  startup/Desk-switch, still doesn't place anything -- use the
  separate keyword-only invocation file for an additional instance).

### Version 11
- A repeatable way to author a `DefineWidget` widget from real
  TypeScript source (a small per-widget source directory + the seeded
  `scripts/build_widget.py`) instead of hand-writing inline JS --
  see "Authoring from real source" in `tempui-custom-widgets.md`.

### Version 10
- New `OpenImage` keyword: open an existing image file in the Image
  Viewer widget. See `tempui-image.md`.
""",
    "version-00": """### Version 9
- New "Inspecting another widget" capability
  (`desk.introspect.snapshot(targetInstanceId)`, capability
  `introspect`): a DOM tree snapshot and console log of another placed
  widget instance, gated by a one-time user confirmation dialog.

### Version 8
- A `DefineWidget` file can now declare `Capability<TAB>name` lines,
  granting its widget kind Bridge API capabilities (`workspace`, `fs`,
  `widgets`, `events`, ...) the same way a real `widgets/<id>/
  widget.json` manifest's own `capabilities` list does.

### Version 7
- `desk.events.*` (capability `events`): Desk's own event message
  channel -- `subscribe`/`unsubscribe`/`publish`/`onMessage`, for
  telling another widget instance "something happened" without either
  needing to know the other exists. See "Sending and receiving named
  messages" in `tempui-custom-widgets.md`.
""",
}


def _render_changelog_doc(title: str, entries: dict[str, str], intro: str) -> str:
    """Renders _BREAKING_CHANGES/_NEW_FEATURES (or any tag_id -> body
    dict shaped like them) into a standalone Markdown doc -- one `##
    <tag id>` section per entry, newest-first per CURRENT_TAGS order
    (an entry whose tag isn't in CURRENT_TAGS at all, which shouldn't
    normally happen, sorts after every entry that is, in dict order)."""
    known_order = {tag: i for i, tag in enumerate(CURRENT_TAGS)}
    ordered_ids = sorted(entries, key=lambda tag_id: -known_order.get(tag_id, -1))
    sections = [f"## {tag_id}\n{entries[tag_id].rstrip()}" for tag_id in ordered_ids]
    return f"{title}\n\n{intro.strip()}\n\n" + "\n\n".join(sections) + "\n"


_BREAKING_CHANGES_DOC = _render_changelog_doc(
    "# TempUI: Breaking Changes",
    _BREAKING_CHANGES,
    """See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- entries here
are listed newest-first, one section per tag, each tagged with the tag
id that introduced the change.

This file is the complete, unfiltered history: every tag Desk has ever
introduced, the same content for every project, regardless of which
tags this particular project has already seen. A section existing here
does **not** mean it's new to you. If you already have a doc-upgrade
notification naming specific tags, that notification -- not this file
-- is what tells you what's actually new; it includes each named tag's
own description directly, so you don't need to come find it here at
all. Open this file yourself only if you want the fuller, permanent
record (and in tempui-new-features.md) -- there's no need to read from
the top in that case either, just the sections for tags you don't
already have.
Versions 1-6 (from this doc's pre-tag history) predate this changelog
and aren't individually recorded.""",
)

_NEW_FEATURES_DOC = _render_changelog_doc(
    "# TempUI: New Features",
    _NEW_FEATURES,
    """See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- entries here
are listed newest-first, one section per tag, each tagged with the tag
id that introduced it.

This file is the complete, unfiltered history: every tag Desk has ever
introduced, the same content for every project, regardless of which
tags this particular project has already seen. A section existing here
does **not** mean it's new to you. If you already have a doc-upgrade
notification naming specific tags, that notification -- not this file
-- is what tells you what's actually new; it includes each named tag's
own description directly, so you don't need to come find it here at
all. Open this file yourself only if you want the fuller, permanent
record (and in tempui-breaking-changes.md) -- there's no need to read
from the top in that case either, just the sections for tags you don't
already have.
Versions 1-6 (from this doc's pre-tag history) predate this changelog
and aren't individually recorded.""",
)


def render_new_tags_digest(tags: Collection[str]) -> str:
    """Markdown body summarizing exactly `tags`' own
    _BREAKING_CHANGES/_NEW_FEATURES entries (newest-first per
    CURRENT_TAGS order) -- used by TempUiManager._notify_docs_upgraded
    to build the doc-upgrade notification's actual content, as
    distinct from _render_changelog_doc's whole-history output."""
    known_order = {tag: i for i, tag in enumerate(CURRENT_TAGS)}
    ordered = sorted(set(tags), key=lambda tag_id: -known_order.get(tag_id, -1))
    sections = []
    for tag_id in ordered:
        breaking = _BREAKING_CHANGES.get(tag_id)
        feature = _NEW_FEATURES.get(tag_id)
        if breaking is None and feature is None:
            continue
        parts = [f"## {tag_id}"]
        if breaking is not None:
            parts.append(f"**Breaking changes:**\n\n{breaking.strip()}")
        if feature is not None:
            parts.append(f"**New features:**\n\n{feature.strip()}")
        sections.append("\n\n".join(parts))
    if not sections:
        return "No changelog details recorded for these tags."
    return "\n\n".join(sections)

# TODO 029047b: the "Authoring from real source" build script (TODO
# b324217), moved here from a one-time-seeded scripts/build_widget.py
# into the same generated/refreshed .desk_temp set the docs themselves
# use -- its own content changes exactly as often as the rest of the
# tempui doc set does, so a one-time seed meant an older project's
# copy would silently go stale forever, the same problem the doc-split
# staleness check (TODO e57ce5f) already solved for the .md files.
# Wrapped in triple *single* quotes deliberately: the script's own
# docstring uses triple double quotes internally.
_BUILD_WIDGET_SCRIPT = '''#!/usr/bin/env python3
"""Packages a DefineWidget source directory (TypeScript custom element +
template HTML + tsconfig + manifest) into a `DefineWidget` tempui file
under `.desk_temp/` -- see "Authoring from real source" in
`tempui-custom-widgets.md` (this same directory) for the full
authoring pattern this implements.

This file itself lives at `.desk_temp/build_widget.py`, generated and
kept fresh there the same way the rest of the tempui doc set is (TODO
029047b) -- refreshed automatically whenever the doc set's shared
version changes, rather than seeded once into a project and left to go
stale. It's deliberately self-contained: no import of this app's own
`desk` package, which the project it's generated into won't have
installed. Takes any directory as its argument -- it doesn't care
whether that's a not-yet-promoted widget's source (recommended at
`.desk_temp/widgets/<name>/`) or a promoted one's (moved to
`desk_widgets/<name>/` at the project root on promotion, TODO 59c5a70);
the build process is identical either way.

Usage:
    python3 .desk_temp/build_widget.py .desk_temp/widgets/<name>
    python3 .desk_temp/build_widget.py desk_widgets/<name>  # after promotion

Expects, in that directory:
    <name>.ts       -- the widget's logic (name must match the directory).
    widget.html     -- self-contained document, with a `<script>` whose
                        entire content is the one-line marker comment
                        `/* BUILD:COMPILED_JS */`.
    tsconfig.json   -- must set compilerOptions.outDir.
    widget.json     -- {"keyword": str, "label": str, "width": int,
                        "height": int, "capabilities": list[str]
                        (optional, defaults to [])}.

Writes a fresh `.desk_temp/<uuid>` tempui file and prints its path.
"""
import base64
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

BUILD_MARKER = "/* BUILD:COMPILED_JS */"
REQUIRED_MANIFEST_KEYS = ("keyword", "label", "width", "height")
HTML_CHUNK_SIZE = 2000
TEMP_UI_DIRNAME = ".desk_temp"


class BuildError(Exception):
    """Any problem that should abort the build with a clear message --
    caught once in main(), never elsewhere, so every failure path prints
    one clean line instead of a traceback."""


def _read_manifest(widget_dir: Path) -> dict:
    manifest_path = widget_dir / "widget.json"
    if not manifest_path.is_file():
        raise BuildError(f"{manifest_path} not found")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        raise BuildError(f"{manifest_path} is not valid JSON: {e}") from e
    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
    if missing:
        raise BuildError(f"{manifest_path} is missing required key(s): {', '.join(missing)}")
    return manifest


def _read_tsconfig(widget_dir: Path) -> dict:
    tsconfig_path = widget_dir / "tsconfig.json"
    if not tsconfig_path.is_file():
        raise BuildError(f"{tsconfig_path} not found")
    try:
        return json.loads(tsconfig_path.read_text())
    except json.JSONDecodeError as e:
        raise BuildError(f"{tsconfig_path} is not valid JSON: {e}") from e


def _read_out_dir(widget_dir: Path, tsconfig: dict) -> Path:
    out_dir = tsconfig.get("compilerOptions", {}).get("outDir")
    if not out_dir:
        raise BuildError(f"{widget_dir / 'tsconfig.json'} must set compilerOptions.outDir")
    return widget_dir / out_dir


def _read_ordered_stems(tsconfig: dict) -> list | None:
    """The basename stems (filename without .ts) of tsconfig.json's own
    top-level "files" array, in the order the widget author declared --
    base classes before subclasses, for a widget split across multiple
    .ts files (TODO 3fc5331). None if "files" isn't present (the common,
    single-file-widget case), meaning the caller keeps its existing,
    order-agnostic behavior unchanged."""
    files = tsconfig.get("files")
    if not files:
        return None
    return [Path(entry).stem for entry in files]


def _compile_typescript(widget_dir: Path) -> None:
    ts_source = widget_dir / f"{widget_dir.name}.ts"
    if not ts_source.is_file():
        raise BuildError(f"{ts_source} not found -- expected a file matching the directory's own name")
    # Deliberately never falls back to `npx tsc`: without TypeScript
    # actually installed, `npx tsc` silently resolves to an unrelated,
    # abandoned npm package also called `tsc` -- a confusing failure mode
    # worth avoiding entirely by only ever invoking a real `tsc` on PATH.
    if shutil.which("tsc") is None:
        raise BuildError("`tsc` not found on PATH -- install TypeScript to build this widget")
    result = subprocess.run(["tsc", "-p", str(widget_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"tsc failed:\\n{result.stdout}{result.stderr}")


def _concatenate_compiled_js(out_dir: Path, ordered_stems: list | None) -> str:
    if not out_dir.is_dir():
        raise BuildError(f"tsc reported success but {out_dir} doesn't exist")
    # sorted() here is only a deterministic starting point for the
    # ordered_stems reorder below -- not the final order once
    # ordered_stems is given (TODO 3fc5331: plain alphabetical order
    # doesn't respect cross-file class inheritance).
    js_files = sorted(out_dir.rglob("*.js"))
    if not js_files:
        raise BuildError(f"no .js files found under {out_dir} after compiling")
    if ordered_stems is None:
        return "".join(path.read_text() for path in js_files)

    by_stem = {}
    for path in js_files:
        if path.stem in by_stem:
            raise BuildError(
                f"multiple compiled files named {path.stem}.js under {out_dir} "
                f"({by_stem[path.stem]}, {path}) -- tsconfig.json's \\"files\\" list "
                f"can't disambiguate same-named files in different directories"
            )
        by_stem[path.stem] = path

    missing = [stem for stem in ordered_stems if stem not in by_stem]
    if missing:
        raise BuildError(
            f"tsconfig.json's \\"files\\" list names {missing[0]}.ts, but no "
            f"matching {missing[0]}.js was found under {out_dir} after compiling"
        )
    unlisted = [stem for stem in by_stem if stem not in ordered_stems]
    if unlisted:
        raise BuildError(
            f"{out_dir} contains {unlisted[0]}.js, which isn't listed in "
            f"tsconfig.json's \\"files\\" -- add it there so its position in the "
            f"compile order is explicit"
        )
    return "".join(by_stem[stem].read_text() for stem in ordered_stems)


def _substitute_marker(widget_dir: Path, compiled_js: str) -> str:
    html_path = widget_dir / "widget.html"
    if not html_path.is_file():
        raise BuildError(f"{html_path} not found")
    html = html_path.read_text()
    if html.count(BUILD_MARKER) != 1:
        raise BuildError(f"{html_path} must contain exactly one {BUILD_MARKER!r} marker line")
    return html.replace(BUILD_MARKER, compiled_js)


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def build_widget(widget_dir: Path) -> tuple[str, str]:
    """Returns (keyword, tempui_text) -- the keyword is needed by
    main() below to find and clean up any other DefineWidget file for
    this same widget kind, not just to build a fresh one."""
    manifest = _read_manifest(widget_dir)
    tsconfig = _read_tsconfig(widget_dir)
    out_dir = _read_out_dir(widget_dir, tsconfig)
    ordered_stems = _read_ordered_stems(tsconfig)
    _compile_typescript(widget_dir)
    compiled_js = _concatenate_compiled_js(out_dir, ordered_stems)
    html = _substitute_marker(widget_dir, compiled_js)
    html_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")

    lines = [
        f"DefineWidget\\t{manifest['keyword']}\\t{manifest['label']}",
        f"Size\\t{manifest['width']}\\t{manifest['height']}",
    ]
    lines.extend(f"Capability\\t{cap}" for cap in manifest.get("capabilities", []))
    lines.extend(
        f"StateSchema\\t{key}\\t{type_expr}" for key, type_expr in manifest.get("state_schema", {}).items()
    )
    # TODO 13f4ad5: records the directory this file was literally built
    # from (Desk resolves it against the project directory) so a later
    # promotion can relocate the real source directory without having
    # to guess it back from `keyword` -- which is almost never the same
    # string as this (kebab-case) directory name.
    lines.append(f"SourcePath\\t{widget_dir.as_posix()}")
    lines.extend(f"Html\\t{chunk}" for chunk in _chunk(html_b64, HTML_CHUNK_SIZE))
    return manifest["keyword"], "\\n".join(lines) + "\\n"


# TODO e86a31b: the historical, pre-029047b seeded location -- a
# project that adopted Desk before that TODO moved this mechanism to
# .desk_temp/build_widget.py (this file) can still have a stale copy
# sitting there, silently defeating any fix landed here since (e.g.
# TODO 31db3f6's capabilities emission) without anything today telling
# them so. Checked by path only, not content/version -- this file
# doesn't know anything about a copy it didn't write, just its own
# canonical location and whether something else also claims that name.
STALE_SIBLING_SCRIPT_PATH = Path("scripts/build_widget.py")


def _warn_if_stale_sibling_exists() -> None:
    if STALE_SIBLING_SCRIPT_PATH.is_file():
        print(
            f"warning: {STALE_SIBLING_SCRIPT_PATH} also exists in this project and is not "
            f"kept up to date -- if you're not sure which one you just ran, it was probably "
            f"the wrong one. Use .desk_temp/build_widget.py (this file) instead.",
            file=sys.stderr,
        )


def _delete_other_builds_for_keyword(temp_ui_dir: Path, keyword: str, keep: Path) -> None:
    """TODO e86a31b: an un-promoted widget rebuilt many times
    accumulates one leftover DefineWidget file per rebuild forever --
    harmless during one continuously-running Desk session (the
    most-recently-registered file always wins), but
    _register_custom_widgets_from_desk_temp re-scans .desk_temp in
    alphabetical (not chronological) order at startup/Desk-switch, so
    several stale same-keyword files left behind risk an old one
    "winning" again with no relationship to which was actually built
    most recently. Deletes every other file in temp_ui_dir whose first
    line is this same keyword's own DefineWidget line -- cheap (a
    handful of files at most), and only ever run right after a
    successful build."""
    marker = f"DefineWidget\\t{keyword}\\t"
    for candidate in temp_ui_dir.iterdir():
        if candidate == keep or not candidate.is_file():
            continue
        try:
            first_line = candidate.open(encoding="utf-8").readline()
        except (OSError, UnicodeDecodeError):
            continue
        if first_line.startswith(marker):
            candidate.unlink()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    widget_dir = Path(argv[0])
    if not widget_dir.is_dir():
        print(f"{widget_dir} is not a directory", file=sys.stderr)
        return 1

    _warn_if_stale_sibling_exists()

    try:
        keyword, tempui_text = build_widget(widget_dir)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    temp_ui_dir = Path(TEMP_UI_DIRNAME)
    temp_ui_dir.mkdir(exist_ok=True)
    out_path = temp_ui_dir / str(uuid.uuid4())
    out_path.write_text(tempui_text)
    _delete_other_builds_for_keyword(temp_ui_dir, keyword, keep=out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

# TODO 49e3732: same "generated and kept fresh, not a one-time seed"
# reasoning as _BUILD_WIDGET_SCRIPT above -- a Job/DeskProc author was
# hand-writing the same base64.b64encode(...)-and-chunk script from
# scratch every time otherwise. Wrapped in triple *single* quotes for
# the same reason: the script's own docstring uses triple double
# quotes internally.
_BUILD_JOB_OR_DESK_PROC_SCRIPT = '''#!/usr/bin/env python3
"""Packages a plain script into a ready-to-drop `Job`/`DeskProc` tempui
file under `.desk_temp/` -- see "The TempUI DSL: Job"/"The TempUI DSL:
DeskProc" (tempui-jobs.md/tempui-desk-proc.md, this same directory) for
the file formats this implements the base64/chunking/writing step for.

This file itself lives at `.desk_temp/build_job_or_desk_proc.py`,
generated and kept fresh there the same way `build_widget.py` (this
same directory) is -- refreshed automatically whenever the doc set's
shared version changes, rather than seeded once into a project and left
to go stale. It's deliberately self-contained: no import of this app's
own `desk` package, which the project it's generated into won't have
installed.

Usage:
    python3 .desk_temp/build_job_or_desk_proc.py desk-proc SUMMARY SCRIPT.py
        Builds a DeskProc file -- SCRIPT.py is always plain Python.

    python3 .desk_temp/build_job_or_desk_proc.py job KIND SUMMARY SCRIPT [--capability NAME ...]
        Builds a Job file. KIND is "python" or "html"; SCRIPT is a .py
        file for "python", or any file (typically .html) for "html".
        --capability is repeatable and only meaningful for an
        html-kind Job (harmless, but ignored, for python).

Writes a fresh `.desk_temp/<uuid>` tempui file and prints its path.
"""
import argparse
import base64
import sys
import uuid
from pathlib import Path

CHUNK_SIZE = 2000
TEMP_UI_DIRNAME = ".desk_temp"


class BuildError(Exception):
    """Any problem that should abort the build with a clear message --
    caught once in main(), never elsewhere, so every failure path prints
    one clean line instead of a traceback."""


def _chunk(text: str, size: int) -> list:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _read_script(path_str: str) -> str:
    path = Path(path_str)
    if not path.is_file():
        raise BuildError(f"{path} not found")
    return path.read_text()


def _check_single_line_safe(value: str, what: str) -> None:
    """A tempui file's first line is TAB-delimited -- a literal tab
    inside `value` would read as an extra field boundary, and a literal
    newline would end the line early, either way silently producing a
    tempui file that looks fine but parses wrong. Caught here once,
    applied to every free-text field this script accepts."""
    if "\\t" in value or "\\n" in value:
        raise BuildError(f"{what} can't contain a tab or newline: {value!r}")


def build_desk_proc(summary: str, script_path: str) -> str:
    _check_single_line_safe(summary, "summary")
    script = _read_script(script_path)
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    lines = [f"DeskProc\\t{summary}"]
    lines.extend(f"Script\\t{chunk}" for chunk in _chunk(script_b64, CHUNK_SIZE))
    return "\\n".join(lines) + "\\n"


def build_job(kind: str, summary: str, script_path: str, capabilities: list) -> str:
    if kind not in ("python", "html"):
        raise BuildError(f"job kind must be 'python' or 'html', got {kind!r}")
    _check_single_line_safe(summary, "summary")
    for capability in capabilities:
        _check_single_line_safe(capability, "capability name")
    script = _read_script(script_path)
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    lines = [f"Job\\t{kind}\\t{summary}"]
    lines.extend(f"Capability\\t{capability}" for capability in capabilities)
    lines.extend(f"Script\\t{chunk}" for chunk in _chunk(script_b64, CHUNK_SIZE))
    return "\\n".join(lines) + "\\n"


def _parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a ready-to-drop Job/DeskProc tempui file under .desk_temp/."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    desk_proc_parser = subparsers.add_parser("desk-proc", help="Build a DeskProc tempui file.")
    desk_proc_parser.add_argument("summary", help="Shown in the notification and the placed Runner widget.")
    desk_proc_parser.add_argument("script", help="Path to the Python script to embed.")

    job_parser = subparsers.add_parser("job", help="Build a Job tempui file.")
    job_parser.add_argument("kind", choices=("python", "html"), help="Which Job kind to build.")
    job_parser.add_argument("summary", help="Shown in the notification and the placed Runner widget.")
    job_parser.add_argument("script", help="Path to the script to embed (.py for python, .html for html).")
    job_parser.add_argument(
        "--capability",
        action="append",
        default=[],
        dest="capabilities",
        metavar="NAME",
        help="A Bridge API capability this html-kind Job needs (repeatable). Ignored, but harmless, for python.",
    )

    return parser.parse_args(argv)


def main(argv: list) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "desk-proc":
            tempui_text = build_desk_proc(args.summary, args.script)
        else:
            tempui_text = build_job(args.kind, args.summary, args.script, args.capabilities)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    temp_ui_dir = Path(TEMP_UI_DIRNAME)
    temp_ui_dir.mkdir(exist_ok=True)
    out_path = temp_ui_dir / str(uuid.uuid4())
    out_path.write_text(tempui_text)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

LIGHTNING_ROUND_DOC_FILENAME = "tempui-lightning-round.md"
MARKDOWN_DOC_FILENAME = "tempui-markdown.md"
IMAGE_DOC_FILENAME = "tempui-image.md"
SCRATCH_DOC_FILENAME = "tempui-scratch.md"
CUSTOM_WIDGETS_DOC_FILENAME = "tempui-custom-widgets.md"
DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME = "tempui-discuss-parking-lot-item.md"
JOBS_DOC_FILENAME = "tempui-jobs.md"
DESK_PROC_DOC_FILENAME = "tempui-desk-proc.md"
INSTALLED_JOBS_DOC_FILENAME = "tempui-installed-jobs.md"
BREAKING_CHANGES_DOC_FILENAME = "tempui-breaking-changes.md"
NEW_FEATURES_DOC_FILENAME = "tempui-new-features.md"
BUILD_WIDGET_SCRIPT_FILENAME = "build_widget.py"
BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME = "build_job_or_desk_proc.py"

# filename -> its static content, for every split-out doc (TODO
# e57ce5f) -- iterated by write_tempui_docs/ensure_docs_current so
# adding a future split file is a one-line addition here, not a new
# call site to remember elsewhere. Not every entry is a `.md` doc --
# BUILD_WIDGET_SCRIPT_FILENAME (TODO 029047b)/
# BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME (TODO 49e3732) are `.py`
# scripts, but write_tempui_docs/ensure_docs_current treat every entry
# identically (`.write_text(content)`), so neither needs special-casing
# here.
SPLIT_DOC_CONTENT: dict[str, str] = {
    LIGHTNING_ROUND_DOC_FILENAME: _LIGHTNING_ROUND_DOC,
    MARKDOWN_DOC_FILENAME: _MARKDOWN_DOC,
    IMAGE_DOC_FILENAME: _IMAGE_DOC,
    SCRATCH_DOC_FILENAME: _SCRATCH_DOC,
    CUSTOM_WIDGETS_DOC_FILENAME: _CUSTOM_WIDGETS_DOC,
    DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME: _DISCUSS_PARKING_LOT_ITEM_DOC,
    JOBS_DOC_FILENAME: _JOBS_DOC,
    DESK_PROC_DOC_FILENAME: _DESK_PROC_DOC,
    INSTALLED_JOBS_DOC_FILENAME: _INSTALLED_JOBS_DOC,
    BREAKING_CHANGES_DOC_FILENAME: _BREAKING_CHANGES_DOC,
    NEW_FEATURES_DOC_FILENAME: _NEW_FEATURES_DOC,
    BUILD_WIDGET_SCRIPT_FILENAME: _BUILD_WIDGET_SCRIPT,
    BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME: _BUILD_JOB_OR_DESK_PROC_SCRIPT,
}


def render_static_doc() -> str:
    """DOC_TEMPLATE with its tag-comment block filled in (TODO
    6839365, was a single version placeholder pre-tags, TODO f7b1611)
    -- plain string substitution, not str.format(): the template is
    free-form Markdown prose that could plausibly contain a literal
    `{`/`}` some day (e.g. a JSON example), which .format() would
    silently misinterpret as a field reference."""
    tag_lines = "\n".join(f"<!-- desk-temporary-ui.md tag: {tag} -->" for tag in CURRENT_TAGS)
    return DOC_TEMPLATE.replace(_DOC_TAGS_PLACEHOLDER, tag_lines)


def parse_doc_tags(text: str) -> set[str] | None:
    """Extracts the set of tags desk-temporary-ui.md's own header
    records it has already seen (TODO 6839365, one `<!-- ...tag: ...
    -->` comment per tag). Falls back to migrating a pre-tags file's
    old single `<!-- ...version: N -->` comment (TODO f7b1611) via
    _legacy_version_tags if there's no tag comment at all. Returns
    None only when neither is present -- a file that predates *any*
    tracking, always treated as out of date (see ensure_docs_current),
    the same as an unparseable/missing version note always was
    pre-tags."""
    tag_lines = _TAG_LINE_RE.findall(text)
    if tag_lines:
        return set(tag_lines)
    legacy_match = _LEGACY_VERSION_RE.search(text)
    if legacy_match is not None:
        return set(_legacy_version_tags(int(legacy_match.group(1))))
    return None


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


def ensure_docs_current(temp_dir: Path) -> tuple[bool, frozenset[str]]:
    """Refreshes the *whole* tempui doc set in place if stale (TODO
    e57ce5f, generalizing TODO f7b1611 once the docs split across
    multiple files; TODO 6839365 for the move from a single version
    integer to a tag set) -- called before opening a Desk (see
    desk.shell.temp_ui_manager.TempUiManager.provision), right
    alongside the analogous check TODO 91b3f42 already does for the
    dynamic custom-widgets section. A no-op if desk-temporary-ui.md
    doesn't exist at all (nothing to refresh -- first creation is
    `provision`'s own job, via write_tempui_docs).

    The main file's tag comments stand for the *entire* set, per the
    request -- so this refreshes everything (not just the main file)
    if the known-tags set (after resolving any TAG_COLLAPSES) doesn't
    cover CURRENT_TAGS, *or* any split file is missing (e.g. a user
    deleted one) -- there's no per-file staleness concept to check
    independently.

    Preserves the main file's custom-widgets section verbatim if
    present (extracted before rewriting, re-appended after) -- "be
    certain not to clobber the DSL extensions." A file that predates
    the custom-widgets feature too (no markers at all) has nothing to
    preserve; it's just fully rewritten, which is safe even in
    isolation since DeskWindow._sync_tempui_doc runs immediately
    afterward in the real startup/Desk-switch flow and inserts a fresh
    section regardless.

    Returns (rewrote, missing_tags) (TODO 7c7b676, TODO 6839365):
    rewrote is True whenever write_tempui_docs actually ran.
    missing_tags is CURRENT_TAGS minus the doc's own (canonicalized)
    known tags, but only when the doc had *some* real tag information
    to diff against -- an empty frozenset otherwise (nothing rewrote
    and every tag already matched, a split file was merely missing, or
    the doc predates tag-tracking entirely and has nothing to diff)
    -- none of those are "the tag set changed" in the sense
    TempUiManager.provision's own caller cares about, just "the file
    set was topped up/repaired." Lets the caller distinguish a real
    convention upgrade worth telling the user about from routine
    repair, without re-deriving the same comparison twice."""
    doc_path = temp_dir / DOC_FILENAME
    if not doc_path.is_file():
        return False, frozenset()
    text = doc_path.read_text()
    known_tags = parse_doc_tags(text)
    canonical_known = _canonicalize_tags(known_tags) if known_tags is not None else frozenset()
    tags_current = known_tags is not None and CURRENT_TAG_SET <= canonical_known
    all_split_docs_present = all((temp_dir / filename).is_file() for filename in SPLIT_DOC_CONTENT)
    if tags_current and all_split_docs_present:
        return False, frozenset()
    missing_tags = frozenset(CURRENT_TAG_SET - canonical_known) if known_tags is not None else frozenset()
    custom_section = None
    if CUSTOM_WIDGETS_SECTION_START in text and CUSTOM_WIDGETS_SECTION_END in text:
        start = text.index(CUSTOM_WIDGETS_SECTION_START)
        end = text.index(CUSTOM_WIDGETS_SECTION_END) + len(CUSTOM_WIDGETS_SECTION_END)
        custom_section = text[start:end]
    write_tempui_docs(temp_dir)
    if custom_section is not None:
        doc_path.write_text(doc_path.read_text().rstrip("\n") + "\n\n" + custom_section + "\n")
    return True, missing_tags


def _repo_shared_components_dir() -> Path:
    """This installed `desk` package's own shared-components/ directory
    (TODO 3b1ef3d) -- resolved relative to this very file, not the
    current working directory, since Desk is always run from its own
    checked-out repo (editable-installed) regardless of which project's
    directory is currently open. Confirmed directly: `Path(__file__)
    .resolve()` for this module already resolves to this repo's real
    `src/desk/temp_ui.py`, not a separate site-packages copy."""
    return Path(__file__).resolve().parents[2] / SHARED_COMPONENTS_DIRNAME


def sync_shared_components(temp_dir: Path) -> None:
    """Mirrors this repo's own shared-components/ into
    `temp_dir/shared-components`, always fresh (TODO 3b1ef3d) -- called
    on every TempUiManager.provision, unconditionally (unlike
    write_tempui_docs/ensure_docs_current's branch above, there's no
    "only if missing/stale" check here: a full copy is cheap, and this
    guarantees `.desk_temp/shared-components/` is never a stale mirror,
    e.g. after a component here was removed). A no-op if this checkout
    has no shared-components/ of its own (an unusual non-source
    install) -- nothing to copy."""
    source = _repo_shared_components_dir()
    if not source.is_dir():
        return
    destination = temp_dir / SHARED_COMPONENTS_DIRNAME
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _repo_app_dsl_dir() -> Path:
    """This installed `desk` package's own app_dsl/ directory (TODO
    48e3b39) -- mirrors _repo_shared_components_dir's exact shape and
    reasoning above."""
    return Path(__file__).resolve().parents[2] / APP_DSL_DIRNAME


def sync_app_dsl_tool(temp_dir: Path) -> None:
    """Mirrors this repo's own app_dsl/ into `temp_dir/app_dsl`, always
    fresh (TODO 48e3b39) -- mirrors sync_shared_components's exact
    shape/reasoning above (unconditional full copy, no "only if
    missing/stale" check; a no-op if this checkout has no app_dsl/ of
    its own). `__pycache__` is excluded -- a stale local bytecode
    cache from running this repo's own scripts has no business being
    mirrored into a project's `.desk_temp/`."""
    source = _repo_app_dsl_dir()
    if not source.is_dir():
        return
    destination = temp_dir / APP_DSL_DIRNAME
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))


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
JOB_KEYWORD = "Job"
DESK_PROC_KEYWORD = "DeskProc"
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
        JOB_KEYWORD,
        DESK_PROC_KEYWORD,
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
    capabilities (`"workspace"`, `"state"`, `"fs"`, `"widgets"`, `"events"`, ...)
    this widget kind is allowed to use -- same coarse, resource-level
    strings a real `widgets/<id>/widget.json`'s own `capabilities`
    list already uses; defaults to none declared, same as a manifest
    with no `capabilities` key. `state_schema` (TODO af7898b) is the
    same key -> TypeScript-type-expression-string dict a real
    `widget.json`'s own `state_schema` field would be -- see
    desk.schema_types and plans/state-store-schema-core.md.
    `source_path` (TODO 13f4ad5) is the project-directory-relative,
    POSIX-style path to this widget's current authoring source
    directory (e.g. `.desk_temp/widgets/pdf-viewer`, later
    `desk_widgets/pdf-viewer` once promoted) -- `None` for a
    hand-authored, inline-only widget with no source directory at all,
    or a definition saved before this field existed. This is the
    durable record `_relocate_promoted_widget_source`/
    `_register_custom_widget` (desk.shell.window) use instead of
    reconstructing a source directory from `keyword`, which almost
    never matches the real (kebab-case) directory name."""

    keyword: str
    label: str
    html_b64: str
    default_size: tuple[int, int] | None = None
    capabilities: list[str] = field(default_factory=list)
    state_schema: dict[str, str] = field(default_factory=dict)
    source_path: str | None = None


def parse_define_widget(text: str) -> CustomWidgetDefinition | None:
    """Extracts a CustomWidgetDefinition from a DefineWidget temp-UI
    file: `DefineWidget<TAB>keyword<TAB>label` (must be the first
    line), an optional `Size<TAB>width<TAB>height` line, zero or more
    `Capability<TAB>name` lines (TODO f693275 -- same shape as `Size`,
    repeatable, collected in file order), zero or more
    `StateSchema<TAB>key<TAB>type_expr` lines (TODO af7898b -- same
    repeatable shape; a duplicate key keeps the last one in file order,
    the same way a real widget.json's own state_schema dict would
    behave for a duplicate JSON key), an optional `SourcePath<TAB>path`
    line (TODO 13f4ad5 -- the project-relative authoring source
    directory this file was built from, if any), and one or more
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
    state_schema: dict[str, str] = {}
    source_path: str | None = None
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
        elif line.startswith("StateSchema\t"):
            parts = line.split("\t")
            if len(parts) >= 3:
                key = parts[1].strip()
                type_expr = parts[2].strip()
                if key and type_expr:
                    state_schema[key] = type_expr
        elif line.startswith("SourcePath\t"):
            path = line.split("\t", 1)[1].strip()
            if path:
                source_path = path
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
        state_schema=state_schema,
        source_path=source_path,
    )


@dataclass
class JobDefinition:
    """A tempui-DSL-defined one-shot agent Job (TODO d7e66f6) --
    Scratch/Question-shaped (one file, one bound widget instance), not
    DefineWidget's two-step type-then-instance shape: nothing else
    invokes a Job, this *is* the invocation. `kind` is `"python"` or
    `"html"`; `capabilities` (meaningful for `kind == "html"` only,
    always collected regardless -- harmless to ignore for `"python"`)
    are the same coarse Bridge API capability strings a real
    `widgets/<id>/widget.json` or a `DefineWidget`'s own `Capability`
    lines already use. `script_b64` is the job's entire script body,
    base64-encoded (tabs/newlines in real script content can't
    otherwise survive this TAB-delimited-lines format)."""

    kind: str
    summary: str
    script_b64: str
    capabilities: list[str] = field(default_factory=list)


def parse_job(text: str) -> JobDefinition | None:
    """Extracts a JobDefinition from a Job temp-UI file:
    `Job<TAB>kind<TAB>summary` (must be the first line, `kind` one of
    "python"/"html"), zero or more `Capability<TAB>name` lines (same
    shape as parse_define_widget's), and one or more
    `Script<TAB>base64-chunk` lines (concatenated in file order before
    decoding, mirroring Html's own chunking). Returns None if the file
    doesn't start with the Job keyword, has no valid kind, or has no
    Script content at all."""
    lines = text.splitlines()
    if not lines:
        return None
    first = lines[0].split("\t")
    if not first or first[0] != JOB_KEYWORD:
        return None
    kind = first[1].strip() if len(first) > 1 else ""
    if kind not in ("python", "html"):
        return None
    summary = first[2].strip() if len(first) > 2 else ""

    capabilities: list[str] = []
    script_chunks: list[str] = []
    for line in lines[1:]:
        if line.startswith("Capability\t"):
            name = line.split("\t", 1)[1].strip()
            if name:
                capabilities.append(name)
        elif line.startswith("Script\t"):
            script_chunks.append(line.split("\t", 1)[1])

    if not script_chunks:
        return None
    return JobDefinition(
        kind=kind,
        summary=summary,
        script_b64="".join(script_chunks),
        capabilities=capabilities,
    )


@dataclass
class DeskProcDefinition:
    """A tempui-DSL-defined one-shot "Desk Proc" (TODO 97bd090) -- a
    close sibling of JobDefinition above, Scratch/Question-shaped (one
    file, one bound widget instance). Deliberately simpler than
    JobDefinition: no `kind`/`capabilities` at all, since a Desk Proc is
    always a plain Python script with real, in-process access to Desk's
    own live shell state (see current_context.get_gui_thread_caller) --
    there is no `html`-kind variant the way a Job has one. `script_b64`
    is the proc's entire script body, base64-encoded, same reasoning as
    JobDefinition.script_b64 (tabs/newlines in real script content
    can't otherwise survive this TAB-delimited-lines format)."""

    summary: str
    script_b64: str


def parse_desk_proc(text: str) -> DeskProcDefinition | None:
    """Extracts a DeskProcDefinition from a DeskProc temp-UI file:
    `DeskProc<TAB>summary` (must be the first line), and one or more
    `Script<TAB>base64-chunk` lines (concatenated in file order before
    decoding, mirroring parse_job's own Script handling). Returns None
    if the file doesn't start with the DeskProc keyword, or has no
    Script content at all."""
    lines = text.splitlines()
    if not lines:
        return None
    first = lines[0].split("\t")
    if not first or first[0] != DESK_PROC_KEYWORD:
        return None
    summary = first[1].strip() if len(first) > 1 else ""

    script_chunks: list[str] = []
    for line in lines[1:]:
        if line.startswith("Script\t"):
            script_chunks.append(line.split("\t", 1)[1])

    if not script_chunks:
        return None
    return DeskProcDefinition(summary=summary, script_b64="".join(script_chunks))


def detect_temp_ui_kind(text: str, custom_keywords: Collection[str] = ()) -> str:
    """"question" (the original, default type), "lightning_round",
    "open_markdown", "open_image", "scratch", "markdown_content",
    "define_widget", "discuss_parking_lot_item", "job", "desk_proc", or
    (if the file's own keyword is a currently-known custom widget --
    TODO 91b3f42) "custom:<keyword>" -- read from the first non-blank
    line's keyword. Lets a caller
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
            if keyword == JOB_KEYWORD:
                return "job"
            if keyword == DESK_PROC_KEYWORD:
                return "desk_proc"
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


def _present_gitignore_entries(text: str) -> set[str]:
    return {line.strip().rstrip("/") for line in text.splitlines()}


def _missing_entries(text: str) -> list[str]:
    """Which of GITIGNORE_ENTRIES aren't present yet -- checked
    independently (an existing project that already ignores
    `.desk_temp/` but not `**/__pycache__/`, from before TODO c458012,
    gets just the missing one appended, not a duplicate)."""
    present = _present_gitignore_entries(text)
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


# TODO 1c67fe5: the pattern covering SOURCE_BUILD_CACHE_DIRNAME
# wherever it can appear under a project's PROMOTED_WIDGET_SRC_DIRNAME
# -- e.g. `desk_widgets/pdf-viewer/.build/`. Deliberately narrower than
# GITIGNORE_ENTRIES above (this repo's own top-level `**/.build/`,
# added the same TODO 13f4ad5 this supports): a *project* Desk is
# managing should only ever need to ignore its own desk_widgets/ build
# caches, not every `.build/` directory anywhere in the project, which
# could plausibly collide with something unrelated to Desk.
DESK_WIDGETS_BUILD_GITIGNORE_ENTRY = f"{PROMOTED_WIDGET_SRC_DIRNAME}/**/{SOURCE_BUILD_CACHE_DIRNAME}/"


def ensure_desk_widgets_gitignore_entry(directory: Path, ask: Callable[[], bool]) -> None:
    """Adds DESK_WIDGETS_BUILD_GITIGNORE_ENTRY to `directory`'s git
    root's `.gitignore` (creating the file if it doesn't exist) if it's
    missing -- but only if `directory/PROMOTED_WIDGET_SRC_DIRNAME`
    (`desk_widgets/`) actually exists: a project that has never
    promoted a source-backed custom widget has nothing to protect yet
    and shouldn't be asked about it. Separate from
    ensure_gitignore_entry/GITIGNORE_ENTRIES above, which are
    unconditional (ensured alongside .desk_temp provisioning
    regardless of whether any custom widget has ever been promoted) --
    this one is conditional on desk_widgets/ existing, so it can't just
    be a third GITIGNORE_ENTRIES member.

    Called from two places (TODO 1c67fe5): DeskWindow._provision_temp_ui
    (startup/Desk-switch -- covers a project that already had
    desk_widgets/ from before this check existed, or from working on
    it outside Desk) and right after DeskWindow
    ._on_tempui_promote_requested's own _relocate_promoted_widget_source
    call, the other moment desk_widgets/ can first come to exist.
    Mirrors ensure_gitignore_entry's own re-check-before-write dance
    (TODO 4716585): `ask()` can pump a modal dialog's own nested event
    loop for an arbitrary amount of time, during which something else
    could already have added the entry."""
    if not (directory / PROMOTED_WIDGET_SRC_DIRNAME).is_dir():
        return
    git_root = find_git_root(directory)
    if git_root is None:
        return
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    if DESK_WIDGETS_BUILD_GITIGNORE_ENTRY.rstrip("/") in _present_gitignore_entries(existing):
        return
    if not ask():
        return
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    if DESK_WIDGETS_BUILD_GITIGNORE_ENTRY.rstrip("/") in _present_gitignore_entries(existing):
        return
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore_path.write_text(f"{prefix}\n{GITIGNORE_COMMENT}\n{DESK_WIDGETS_BUILD_GITIGNORE_ENTRY}\n")


# TODO 94a2fa2: the pattern covering a rust-kind Installed Job's own
# `target/` build output, e.g. `desk-installed-jobs/gpu-sim/target/` --
# same reasoning as DESK_WIDGETS_BUILD_GITIGNORE_ENTRY just above (a
# project-scoped pattern, not this repo's own broader one), just for
# cargo's build directory instead of a promoted widget's `.build/`.
INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY = f"{INSTALLED_JOBS_DIRNAME}/**/target/"


def ensure_installed_jobs_gitignore_entry(directory: Path, ask: Callable[[], bool]) -> None:
    """Adds INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY to `directory`'s
    git root's `.gitignore` (creating the file if it doesn't exist) if
    it's missing -- but only if `directory/INSTALLED_JOBS_DIRNAME`
    actually exists, mirroring ensure_desk_widgets_gitignore_entry's own
    shape exactly (same conditional-on-the-parent-directory-existing
    reasoning, same re-check-before-write dance for the same TODO
    4716585 reason). Called from the same two kinds of moments
    (DeskWindow._provision_temp_ui, and right after DeskWindow
    .install_job succeeds) as that function -- see TODO 94a2fa2,
    plans/installed-jobs-rust-gpu.md."""
    if not (directory / INSTALLED_JOBS_DIRNAME).is_dir():
        return
    git_root = find_git_root(directory)
    if git_root is None:
        return
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    if INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY.rstrip("/") in _present_gitignore_entries(existing):
        return
    if not ask():
        return
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    if INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY.rstrip("/") in _present_gitignore_entries(existing):
        return
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore_path.write_text(f"{prefix}\n{GITIGNORE_COMMENT}\n{INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY}\n")
