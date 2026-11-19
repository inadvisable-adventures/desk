# Porting an existing app into Desk

See `desk-temporary-ui.md` (in this same directory) for this directory's
own overview and its current set of tags -- this file is the guide for
**porting existing application code into Desk**: figuring out which
parts of a project become widgets, jobs or services, and where Desk is
missing something the project needs.

## A repeatable process

"Work out how to port this project" gets reinvented from scratch each
time unless it follows a process. These six steps are what made earlier
analyses good; follow them in order.

1. **Inventory pass.** List the target project's *current* directory
   structure directly (a plain recursive listing -- not memory, not what
   its README says). Projects grow second-generation pieces nobody
   remembers; a fresh listing finds them.
2. **Group into a small number of non-redundant "porting units."** A unit
   is a set of related pieces worth one design proposal: e.g. the app's
   wiring code, the components it wires together, a family of ingestion
   scripts, a local backend service. Note where two units share an
   underlying mechanism (say, both need a managed subprocess) so you can
   cross-reference them instead of merging them or writing the same
   reasoning twice.
3. **For each unit, gather two kinds of grounded facts.** (a) What the
   target code does, with `file:line` evidence. (b) What Desk *already*
   provides for it -- read "What Desk gives you" below first, then the
   real docs (this directory's `tempui-*.md` files, `desk-temporary-ui.md`)
   and at least one real existing widget. **Report a gap only once (b)
   comes back empty after actually looking**, never merely unsearched;
   otherwise you propose something that already exists.
4. **Parallelize the fact-finding, centralize the writing.** Give each
   unit its own read-only research pass (cite `file:line`, report facts,
   don't design the fix) so units can run concurrently without leaking
   assumptions into each other. Then write all the proposals in one
   pass, by one author, so they share one vocabulary -- two gaps are
   often one primitive in two configurations.
5. **Match the destination format's existing conventions.** Read a real
   example of the artifact you are about to produce before writing a new
   one.
6. **Cross-link related outputs** rather than re-explaining shared
   reasoning in each.

This is a draft methodology, refined against a few worked examples --
improve it when a port teaches you something.

## What Desk gives you

Use this to answer step 3(b). Names are the Bridge API (`window.desk.*`,
for `kind: "html"` widgets, jobs and services -- each namespace needs its
capability declared) unless noted. See `tempui-custom-widgets.md`, "The
Desk Bridge API", for each call's exact shape.

**Putting UI on the canvas**
- Built-in widgets already cover common shapes: an Editor, a Markdown
  viewer (table of contents, folding, Mermaid), an Image Viewer, an SVG
  editor, a Sheet (tables/TSV), a Console (a real terminal), a Browser,
  a TODO list, git status/diff viewers, and Claude chat widgets. Check
  the widget catalog (`desk.widgets.list()`) before building one.
- A **new widget kind**: a `kind: "html"` widget via `DefineWidget`
  (see `tempui-custom-widgets.md`; promotable into the project), or a
  real `kind: "python"` widget package in the project's own
  `desk_widgets/<name>/` directory (same `widget.json`/`entry` shape as
  Desk's built-ins; full in-process access, so only for trusted code; use
  the `qt_controls` package's `PaintedComboBox` rather than `QComboBox` --
  see "Project widgets" in the top-level doc).
- Open an existing file in a viewer: `OpenMarkdown`, `OpenImage`, and
  the generic `OpenWithWidget` tempui keywords.
- Ask the user something through the canvas: `Question` and
  `LightningRound` tempui files; `desk.popups` for a confirmation from
  widget code.

**Making pieces talk to each other**
- `desk.events.*` (capability `events`): publish/subscribe on a shared
  channel keyed by widget *instance*; widgets never call each other
  directly. An agent can raise an event onto the same channel with the
  `desk_raise_event` MCP tool, and wait for one with `desk_wait_for_event`
  from a background sub-agent (`tempui-agent-events.md`). An event can be
  a bare signal ("I updated the file") or carry the data in its payload
  instead of a file; past about 1 KB, use a file. See "A signal, or the
  data itself" in `tempui-custom-widgets.md`.
- `desk.log.append/line` (capability `log`): fire-and-forget, time-stamped
  strings into a named log an agent can query by time range
  (`desk_query_widget_log`); the way to let an agent ask a widget what it
  has been doing. Full reference: `tempui-widget-logs.md`.
- `desk.state.get/set/getHistory` (capability `state`): a shared,
  project-scoped key/value store with an edit history; a widget may also
  declare the keys it needs (a state schema).
- `self.getLocalStorage()/setLocalStorage()`: per-instance state that
  survives a reload of the Desk.

**Files and large data**
- `desk.fs.readFile/writeFile` (capability `fs`): relative paths resolve
  against the project's Desk directory; writes create missing parents.
- `desk.documents.open/read/close` (capability `documents`): cached,
  binary-safe byte-range reads, for files too large to base64 whole.
- The file type registry (`desk.filetypes.*`, capability `filetypes`)
  maps extensions/MIME types to the widgets that can view or edit them.

**Computation and long-running work**
- Transforms (`desk.transforms.run`, capability `transforms`; bundled
  ones live in `desk_transforms/`) and the pipeline DSL/Pipeline widget
  for chained steps.
- A `Job` tempui file: **one** throwaway script with Bridge access. An
  *installed job* (`desk_install_job` MCP tool, capability
  `installed_jobs`): a durable, versioned job the project keeps, runnable
  later and from other jobs.
- Desk-hosted microservices (`desk.hmsvc.*`, a `service.json` per
  service): a long-running background process Desk starts, stops, logs
  and restarts for you -- the answer for "this project needs a local
  backend". Full reference: `tempui-hmsvc.md`.

**Seeing and driving Desk itself**
- `desk.introspect.*` plus the screenshot/reveal/list MCP tools
  (`desk_screenshot_widget`, `desk_reveal_widget`,
  `desk_list_widget_instances`) to inspect what is on the canvas, and
  `desk_place_widget` to put a new instance of a registered widget on it; a
  `DeskProc` tempui file for one-off access to the live shell;
  `desk_ask_desk_expert` to hand a question about Desk itself to an
  agent that can read Desk's source (`tempui-ask-desk-expert.md`).
- Named background regions of the canvas ("areas") you can create and
  jump to with `desk_list_areas`/`desk_create_area`/`desk_update_area`/
  `desk_delete_area`/`desk_view_area` (`tempui-areas.md`).
- Layout helpers built in: Open Widgets (a live table of everything
  placed, with stale markers), Minimap (navigate, tile, organize) and
  Recently Removed (revive a removed widget with its state).

## Known gaps

There is no first-class **batch ingestion job** with progress reporting
and a structured result (a `Job` is a single one-shot run; an installed
job has no progress channel), and no first-class model of an **external
service dependency** a project expects to find running (hmsvc manages
services Desk itself starts). If a port needs either, say so explicitly
as a gap -- with the file:line evidence from step 3(a) -- rather than
working around it silently.
