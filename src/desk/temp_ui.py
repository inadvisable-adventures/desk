import re
import shutil
import time
import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path

from desk import tempui_content
from desk.deprecations import get_registry as get_deprecation_registry
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
# collapsed tags' descriptions (entries in src/desk/tempui_content/*.json,
# TODO de16076) into the new tag's own entry -- which may go in any file,
# existing files can be regrouped or merged freely -- delete the old
# entries (so the old tag ids drop out of CURRENT_TAGS, which is derived
# from the files), and record
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

# The changelog entries and the long-text docs live in src/desk/tempui_content/ (TODO de16076, see
# desk.tempui_content). They are all read right here, at import, so nothing can use the tempui doc set before
# every file has been loaded and checked.
_CONTENT = tempui_content.load()

# CURRENT_TAGS: every tag a from-scratch .desk_temp is created with -- the tag-based replacement for the old
# single TEMPUI_DOC_VERSION integer's role as "the current baseline." Derived from the changelog files, oldest
# first (by monthstamp, then file name, then position); it doesn't affect staleness comparisons (a plain set,
# via CURRENT_TAG_SET below), only display order (newest-first) in _BREAKING_CHANGES/_NEW_FEATURES and the
# doc-upgrade notification.
CURRENT_TAGS: tuple[str, ...] = _CONTENT.tags
_BREAKING_CHANGES: dict[str, str] = _CONTENT.breaking_changes
_NEW_FEATURES: dict[str, str] = _CONTENT.new_features
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
  render Markdown content given directly in the tempui file itself
  (including a fenced ` ```mermaid ` diagram -- works out of the box in
  every project, nothing to set up). See
  [tempui-markdown.md](./tempui-markdown.md).
- `OpenImage` — open an existing image file in the Image Viewer
  widget. See [tempui-image.md](./tempui-image.md).
- `OpenWithWidget` — place any other widget kind with a file already
  loaded (the generic form; `OpenMarkdown`/`OpenImage` above are each a
  fixed one-widget special case). See
  [tempui-open-with-widget.md](./tempui-open-with-widget.md).
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

For more information on porting existing app code to Desk -- a
repeatable process, plus a "what Desk gives you" inventory -- see
[tempui-porting-existing-apps.md](./tempui-porting-existing-apps.md).

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
against memory.

**When a doc covers a feature too thinly to act on** — a single
sentence, no schema, no example — and you're about to write real code
against it, check `tempui-new-features.md`'s own section for that
feature's tag *before* reaching for Desk's own source or another
project's code. The changelog entry written when a feature shipped is
often its fullest existing write-up, even for a tag your own project has
long since "seen" (so no doc-upgrade notification will ever point you at
it again). If you still end up having to read outside this doc set to
understand a feature, say so in your summary to the user and offer to
write a FEEDBACK file about the gap, so the next agent doesn't pay the
same cost.

There's also
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
And [tempui-widget-logs.md](./tempui-widget-logs.md) -- the `log` Bridge
capability and its `desk_list_widget_logs`/`desk_query_widget_log` MCP
tools, for letting an agent query what a widget has been doing; also not
a dropped-file keyword.
And [tempui-docked-widgets.md](./tempui-docked-widgets.md) -- the docked
sidebar: `desk_dock_widget`/`desk_undock_widget`/`desk_list_docked_widgets`
MCP tools for putting a `kind: "python"` widget in a panel outside the
zoomable canvas; also not a dropped-file keyword.
And [tempui-areas.md](./tempui-areas.md) -- desk areas: named, click-through
background rectangles on the canvas you can create, rename, move, delete
and jump to with the `desk_*_area` MCP tools; also not a dropped-file
keyword.
And [tempui-experts.md](./tempui-experts.md) -- the general expert registry:
`desk_ask_expert` and friends, for questions whose answers arrive long after
your session is gone; also not a dropped-file keyword.
And [tempui-ask-desk-expert.md](./tempui-ask-desk-expert.md) -- the
`desk_ask_desk_expert` MCP tool, which hands a question about Desk
itself to a fresh agent that can read Desk's source and docs; also not
a dropped-file keyword.
And [tempui-agent-events.md](./tempui-agent-events.md) -- the
`desk_raise_event` and `desk_wait_for_event` MCP tools, for an agent to
signal a running widget, and hear back, directly over `desk.events`
instead of through a polled file.
And [tempui-handoff-requests.md](./tempui-handoff-requests.md) -- the
`desk_*_handoff_request` MCP tools, for handing a task from one agent to
another and tracking its status; also not a dropped-file keyword.
And [tempui-feedback-items.md](./tempui-feedback-items.md) -- the
`desk_create_feedback`/`desk_list_feedback`/`desk_get_feedback` MCP tools,
for reporting friction with Desk itself; also not a dropped-file keyword.

## Project widgets

If you want a genuinely new, permanent widget added to *this* project
-- as opposed to a quick, speculative, in-browser widget you're trying
out via `DefineWidget` (above) -- write it directly at
`desk_widgets/<name>/` at the project root: a `widget.json` manifest
and an entry file, the exact same shape a built-in Desk widget uses
(`{"name", "kind": "python", "entry": "widget.py", "capabilities": [],
"default_size": {"width": ..., "height": ...}}`), with `widget.py`
exposing a `build() -> QWidget` function (real PyQt6, imported and run
directly in Desk's own process -- see `tempui-custom-widgets.md`'s
"Authoring from real source" if you'd rather build a `kind: "html"`
widget instead via `DefineWidget`/promote; a `kind: "html"` entry
written directly here isn't served yet). No tempui file, no promote
step -- it's picked up automatically (and hot-reloads on further
edits) the next time this Desk is opened or switched to, or shortly
after you save it if this Desk is already open on this project.
`desk_widgets/` also durably holds a *promoted* `DefineWidget`
widget's own source (that `widget.json` shape has no `"kind"` key);
the two coexist in the same directory without conflict. **Same trust
level as any other `kind: "python"` widget: this widget's code has
full, unsandboxed, direct access to Desk's own running process** --
the same trust Installed Jobs' `main.py` already gets, not a
capability-scoped surface like a `kind: "html"` widget's Bridge API.

**Don't use native Qt controls that misbehave under canvas zoom.** Widget
content is embedded in the zoomable canvas, where a native `QComboBox`
scales oddly and opens its dropdown list detached from the control, and a
`QTreeView`/`QTreeWidget`'s native expand/collapse arrows detach from their
rows (same for `QToolButton.setArrowType`). Desk ships replacements in
`desk.shell.qt_controls` -- import and use them instead:
`from desk.shell.qt_controls import PaintedComboBox` (`addItem(text,
userData)`, `currentIndex()`, `currentData()`, `itemText()`,
`currentIndexChanged`) and `PaintedBranchTreeView`/`PaintedBranchTreeWidget`.
If a Qt popup window (a `Qt.Popup`) is ever needed from widget content,
construct it with `parent=None`.

## Desk's own log

Desk writes its own log (startup, warnings, errors, and the traceback of
any uncaught exception) to `logs/desk.log` in this directory --
`.desk_temp/logs/desk.log` from the project root -- rotated at about 1 MB
with 5 older files kept (`desk.log.1` ...). Each project has its own, and
you're welcome to read it, e.g. when something in Desk misbehaves and you
want the underlying error rather than guessing. It only exists once Desk
has been opened on this project with this directory present; it is
Desk's log, not something to write to.

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

# The less-general DSL sections split out of DOC_TEMPLATE (TODO e57ce5f) are sibling files in the same
# .desk_temp directory as desk-temporary-ui.md, linked from its intro above. Their text lives in
# src/desk/tempui_content/*.md (TODO de16076), one file per doc, named exactly as it is written into a project;
# see SPLIT_DOC_CONTENT below. None of them carry their own tag comments -- CURRENT_TAGS covers the whole set.

# TODO 6839365, TODO de16076: reverse-chronological-by-tag changelogs for the whole tempui doc set.
# _BREAKING_CHANGES/_NEW_FEATURES (defined near the top of this file from src/desk/tempui_content/*.json) are
# dicts (tag id -> markdown body, no leading heading), not opaque strings: this is what lets
# render_new_tags_digest build a real excerpt for exactly the tags a given project is missing.
# _render_changelog_doc turns each dict into the actual tempui-breaking-changes.md/tempui-new-features.md file
# content (SPLIT_DOC_CONTENT below), one `## <tag id>` section per entry, newest-first per CURRENT_TAGS order.
#
# Going forward: a change that is a breaking change or a new capability gets its own changelog file in
# src/desk/tempui_content/ (scripts/new_tempui_changelog_entry.py mints the tag and writes it) -- see
# development-process.md's "When working on Desk itself" section. Editing temp_ui.py for it is not needed.
#
# TODO 6839365: versions 1-46 from the old TEMPUI_DOC_VERSION scheme were migrated in bulk into five
# decade-bucket tags (version-00 .. version-40) -- see plans/tempui-doc-tags.md for why buckets-of-ten, and
# _legacy_version_tags for how an old project's own single `version: N` comment maps onto these same buckets.


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
                        (optional, defaults to []), "components":
                        list[str] (optional: shared web components --
                        see "Shared components" in tempui-custom-
                        widgets.md)}.

Writes a fresh `.desk_temp/<uuid>` tempui file and prints its path.
"""
import base64
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

BUILD_MARKER = "/* BUILD:COMPILED_JS */"
REQUIRED_MANIFEST_KEYS = ("keyword", "label", "width", "height")
HTML_CHUNK_SIZE = 2000
TEMP_UI_DIRNAME = ".desk_temp"
# TODO d34f8ed: shared web components -- an independent copy of the logic in
# desk.custom_widgets (this file can't import `desk`); keep them in step.
PROJECT_COMPONENTS_RELPATH = "desk_widgets/_shared/components"
DESK_COMPONENTS_DIR = Path(__file__).resolve().parent / "shared-components"  # mirrored from Desk
COMPONENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
TEMPLATE_ID_RE = re.compile(r"<template\\b[^>]*?\\bid\\s*=\\s*[\\"']([^\\"']+)[\\"']", re.IGNORECASE)
TEMPLATES_MARKER = "<!-- BUILD:COMPONENT_TEMPLATES -->"


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


def _library_component(directory: Path, name: str):
    candidate = directory / name
    return candidate if (candidate / f"{name}.ts").is_file() else None


def _resolve_components(manifest: dict, project_dir: Path) -> list:
    """The manifest's "components" as (name, scope, directory) tuples, in
    declared order. A name is `desk:<name>` (Desk's shared-components/),
    `project:<name>` (desk_widgets/_shared/components/), or a bare `<name>`:
    the project library's copy if there is one, else the desk-wide one."""
    names = manifest.get("components", [])
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise BuildError('widget.json: "components" must be a list of component names')
    project_library = project_dir / PROJECT_COMPONENTS_RELPATH
    resolved = []
    for raw in names:
        scope, _, name = raw.rpartition(":")
        if scope not in ("", "desk", "project") or not COMPONENT_NAME_RE.match(name):
            raise BuildError(
                f"invalid component {raw!r}: use a lowercase-kebab name, optionally prefixed desk: or project:"
            )
        in_desk = _library_component(DESK_COMPONENTS_DIR, name) if scope in ("", "desk") else None
        in_project = _library_component(project_library, name) if scope in ("", "project") else None
        found = in_project or in_desk
        if found is None:
            raise BuildError(
                f"component {raw!r} not found (looked for {name}/{name}.ts in {DESK_COMPONENTS_DIR}"
                f"{'' if scope == 'desk' else f' and {project_library}'})"
            )
        entry = (name, "project" if found is in_project else "desk", found)
        if all(e[:2] != entry[:2] for e in resolved):
            resolved.append(entry)
    return resolved


def _compile_typescript(widget_dir: Path, components: list | None = None) -> None:
    ts_source = widget_dir / f"{widget_dir.name}.ts"
    if not ts_source.is_file():
        raise BuildError(f"{ts_source} not found -- expected a file matching the directory's own name")
    # Deliberately never falls back to `npx tsc`: without TypeScript
    # actually installed, `npx tsc` silently resolves to an unrelated,
    # abandoned npm package also called `tsc` -- a confusing failure mode
    # worth avoiding entirely by only ever invoking a real `tsc` on PATH.
    if shutil.which("tsc") is None:
        raise BuildError("`tsc` not found on PATH -- install TypeScript to build this widget")
    project = widget_dir
    if components:
        # An `extends` config next to the build output: the widget's own
        # tsconfig keeps governing every compiler option, while `files`
        # gains the component sources.
        tsconfig = _read_tsconfig(widget_dir)
        own = [str((widget_dir / f).resolve()) for f in (tsconfig.get("files") or [])]
        files = [str((d / f"{n}.ts").resolve()) for n, _scope, d in components]
        files += [f for f in own if f not in files]
        # Compiled into its own wiped directory: tsc lays output out
        # relative to the inputs' common root, which differs with components.
        out = widget_dir / ".build" / "js"
        shutil.rmtree(out, ignore_errors=True)
        config = {
            "extends": "../tsconfig.json",
            "compilerOptions": {"outDir": str(out.resolve())},
            "files": files,
        }
        if not own:
            config["include"] = [str(widget_dir.resolve()) + "/**/*.ts"]
        build_dir = widget_dir / ".build"
        build_dir.mkdir(parents=True, exist_ok=True)
        project = build_dir / "tsconfig.components.json"
        project.write_text(json.dumps(config, indent=2))
    result = subprocess.run(["tsc", "-p", str(project)], capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"tsc failed:\\n{result.stdout}{result.stderr}")


def _component_stem_order(out_dir: Path, ordered_stems: list | None, components: list) -> list | None:
    """Concatenation order once components are involved: their compiled files
    first (a widget's classes may extend them), then the widget's own -- in
    its tsconfig "files" order if given, else alphabetical."""
    if not components:
        return ordered_stems
    first = [name for name, _scope, _dir in components]
    rest = ordered_stems if ordered_stems is not None else sorted({p.stem for p in out_dir.rglob("*.js")})
    return first + [stem for stem in rest if stem not in first]


def _inject_component_templates(html: str, components: list, html_path: Path) -> str:
    blocks = []
    for name, scope, directory in components:
        template = directory / "template.html"
        if not template.is_file():
            continue
        text = template.read_text()
        ids = TEMPLATE_ID_RE.findall(text)
        # A widget that already hand-pasted this template keeps working: a
        # second copy would duplicate its id.
        if ids and all(re.search(r"id\\s*=\\s*[\\"']" + re.escape(i) + r"[\\"']", html) for i in ids):
            print(f"note: {html_path} already contains {scope}:{name}'s template; not injecting a second copy", file=sys.stderr)
            continue
        blocks.append(f"<!-- component {scope}:{name} -->\\n{text.rstrip()}\\n")
    if not blocks:
        return html
    block = "".join(blocks)
    if html.count(TEMPLATES_MARKER) > 1:
        raise BuildError(f"{html_path} must contain at most one {TEMPLATES_MARKER!r} marker")
    if TEMPLATES_MARKER in html:
        return html.replace(TEMPLATES_MARKER, block)
    body = re.search(r"<body\\b[^>]*>", html, re.IGNORECASE)
    if body is None:
        raise BuildError(
            f"{html_path} has no <body> to put component templates after; add one, "
            f"or a {TEMPLATES_MARKER} line where they should go"
        )
    return html[: body.end()] + "\\n" + block + html[body.end() :]


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


def _substitute_marker(widget_dir: Path, compiled_js: str, components: list | None = None) -> str:
    html_path = widget_dir / "widget.html"
    if not html_path.is_file():
        raise BuildError(f"{html_path} not found")
    html = html_path.read_text()
    if components:
        # Before the JS goes in, so the search for <body> only sees markup.
        html = _inject_component_templates(html, components, html_path)
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
    components = _resolve_components(manifest, Path.cwd())
    if components:
        out_dir = widget_dir / ".build" / "js"
    _compile_typescript(widget_dir, components)
    compiled_js = _concatenate_compiled_js(out_dir, _component_stem_order(out_dir, ordered_stems, components))
    html = _substitute_marker(widget_dir, compiled_js, components)
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
OPEN_WITH_WIDGET_DOC_FILENAME = "tempui-open-with-widget.md"
PORTING_DOC_FILENAME = "tempui-porting-existing-apps.md"
SCRATCH_DOC_FILENAME = "tempui-scratch.md"
CUSTOM_WIDGETS_DOC_FILENAME = "tempui-custom-widgets.md"
DISCUSS_PARKING_LOT_ITEM_DOC_FILENAME = "tempui-discuss-parking-lot-item.md"
JOBS_DOC_FILENAME = "tempui-jobs.md"
DESK_PROC_DOC_FILENAME = "tempui-desk-proc.md"
INSTALLED_JOBS_DOC_FILENAME = "tempui-installed-jobs.md"
HMSVC_DOC_FILENAME = "tempui-hmsvc.md"
WIDGET_LOGS_DOC_FILENAME = "tempui-widget-logs.md"
ASK_DESK_EXPERT_DOC_FILENAME = "tempui-ask-desk-expert.md"
EXPERTS_DOC_FILENAME = "tempui-experts.md"
AREAS_DOC_FILENAME = "tempui-areas.md"
DOCKED_WIDGETS_DOC_FILENAME = "tempui-docked-widgets.md"
AGENT_EVENTS_DOC_FILENAME = "tempui-agent-events.md"
HANDOFF_REQUESTS_DOC_FILENAME = "tempui-handoff-requests.md"
FEEDBACK_ITEMS_DOC_FILENAME = "tempui-feedback-items.md"
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
    # Every `*.md` in src/desk/tempui_content/ (the long-text docs, TODO de16076), keyed by its file name;
    # order does not matter.
    **_CONTENT.docs,
    BREAKING_CHANGES_DOC_FILENAME: _BREAKING_CHANGES_DOC,
    NEW_FEATURES_DOC_FILENAME: _NEW_FEATURES_DOC,
    BUILD_WIDGET_SCRIPT_FILENAME: _BUILD_WIDGET_SCRIPT,
    BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME: _BUILD_JOB_OR_DESK_PROC_SCRIPT,
}
_collisions = {BREAKING_CHANGES_DOC_FILENAME, NEW_FEATURES_DOC_FILENAME, BUILD_WIDGET_SCRIPT_FILENAME,
               BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME} & set(_CONTENT.docs)
if _collisions:
    raise tempui_content.TempUiContentError(
        f"tempui_content/ must not contain {', '.join(sorted(_collisions))}: Desk generates that file."
    )


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
OPEN_WITH_WIDGET_KEYWORD = "OpenWithWidget"
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
        OPEN_WITH_WIDGET_KEYWORD,
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
    capabilities (`"workspace"`, `"state"`, `"fs"`, `"documents"`, `"widgets"`,
    `"events"`, `"media"`, ...) this widget kind is allowed to use -- same coarse,
    resource-level strings a real `widgets/<id>/widget.json`'s own
    `capabilities` list already uses; defaults to none declared, same
    as a manifest with no `capabilities` key. `state_schema` (TODO af7898b) is the
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
    "define_widget", "discuss_parking_lot_item", "job", "desk_proc",
    "deprecated:<DEPR id>" (a tombstoned old keyword, TODO df8138a), a
    dynamic "open_with_widget:<widget_id>" (TODO 3b6de01, the file's
    own second field -- "question" instead if that field or the third
    (the path) is missing, same tolerance a genuinely unrecognized
    keyword already gets), or (if the file's own keyword is a
    currently-known custom widget -- TODO 91b3f42) "custom:<keyword>"
    -- read from the first non-blank line's keyword. Lets a caller
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
            if keyword == OPEN_WITH_WIDGET_KEYWORD:
                parsed = parse_open_with_widget(text)
                return f"open_with_widget:{parsed[0]}" if parsed is not None else "question"
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
            # TODO df8138a: an old keyword whose replacement exists is a
            # tombstone -- not a widget, and not silently a "question".
            deprecated = get_deprecation_registry().tempui_keyword(keyword)
            if deprecated is not None:
                return f"deprecated:{deprecated.id}"
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


def parse_open_with_widget(text: str) -> tuple[str, str] | None:
    """Extracts `(widget_id, path)` from an OpenWithWidget temp-UI
    file's first line (`OpenWithWidget<TAB>widget_id<TAB>path`, TODO
    3b6de01) -- tab-separated, unlike parse_open_markdown/
    parse_open_image's simpler single-space-split shape, since a path
    (or a widget id, in principle) may itself contain spaces. Returns
    None if the file doesn't actually start with the OpenWithWidget
    keyword, or either field is missing/blank."""
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] != OPEN_WITH_WIDGET_KEYWORD:
            return None
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            return None
        return parts[1].strip(), parts[2].strip()
    return None


def parse_open_with_widget_label(text: str) -> str | None:
    """The optional fourth, tab-separated field of an OpenWithWidget
    file's first line -- a human-readable label for the notification
    (TODO f9e24e0), for a widget that doesn't meaningfully consume
    `path`. None if absent/blank, or the file isn't a valid
    OpenWithWidget file."""
    if parse_open_with_widget(text) is None:
        return None
    for line in text.splitlines():
        if line.strip():
            parts = line.split("\t")
            return parts[3].strip() or None if len(parts) > 3 else None
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


def _conditional_gitignore_entry_pending(directory: Path, parent_dirname: str, entry: str) -> bool:
    """Shared by the two conditional ensure_*_gitignore_entry functions
    below: True if `directory/parent_dirname` exists, `directory` is in
    a git repo, and that repo's `.gitignore` lacks `entry`."""
    if not (directory / parent_dirname).is_dir():
        return False
    git_root = find_git_root(directory)
    if git_root is None:
        return False
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    return entry.rstrip("/") not in _present_gitignore_entries(existing)


def _ensure_conditional_gitignore_entry(
    directory: Path, parent_dirname: str, entry: str, ask: Callable[[], bool]
) -> None:
    if not _conditional_gitignore_entry_pending(directory, parent_dirname, entry):
        return
    if not ask():
        return
    # Re-check before writing (TODO 4716585): `ask()` may have pumped a
    # nested event loop for an arbitrary time.
    if not _conditional_gitignore_entry_pending(directory, parent_dirname, entry):
        return
    git_root = find_git_root(directory)
    assert git_root is not None
    gitignore_path = git_root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.is_file() else ""
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore_path.write_text(f"{prefix}\n{GITIGNORE_COMMENT}\n{entry}\n")


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
    _ensure_conditional_gitignore_entry(
        directory, PROMOTED_WIDGET_SRC_DIRNAME, DESK_WIDGETS_BUILD_GITIGNORE_ENTRY, ask
    )


def desk_widgets_gitignore_pending(directory: Path) -> bool:
    """True if ensure_desk_widgets_gitignore_entry would currently ask
    (TODO 0593797: lets the shell offer the edit as a non-blocking
    notification instead of a modal question)."""
    return _conditional_gitignore_entry_pending(
        directory, PROMOTED_WIDGET_SRC_DIRNAME, DESK_WIDGETS_BUILD_GITIGNORE_ENTRY
    )


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
    _ensure_conditional_gitignore_entry(
        directory, INSTALLED_JOBS_DIRNAME, INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY, ask
    )


def installed_jobs_gitignore_pending(directory: Path) -> bool:
    """See desk_widgets_gitignore_pending (TODO 0593797)."""
    return _conditional_gitignore_entry_pending(
        directory, INSTALLED_JOBS_DIRNAME, INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY
    )
