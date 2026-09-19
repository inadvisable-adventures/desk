# Pipeline widget: visualize + control a pipe-chained verb DSL pipeline (TODO `9d52dc4`) (COMPLETED)

## Summary

A new `kind: "python"` widget, **Pipeline** (`widgets/pipeline/`), that:

1. Lets the user type/edit a pipe-chained verb DSL pipeline string
   (`desk.pipeline_dsl`, TODO `63bfd42`).
2. Renders the pipeline's *structure* (not its execution) as a Mermaid
   flowchart (`desk.mermaid`, TODO `a76e723`, via the existing
   `mermaid_flowchart_svg` transform the Markdown widget already
   uses), regenerated live as the text changes.
3. Provides an explicit drop target labeled "Input" that accepts a
   drag-and-dropped image file — becomes the pipeline's *initial*
   piped value on Run (today `run_pipeline` always starts every
   pipeline from `None`; nothing lets a caller seed it).
4. Has a "Run" button that actually executes the pipeline
   (`pipeline_dsl.run_pipeline`) against the dropped input, then
   re-renders the diagram with per-stage OK/FAILED annotations and
   shows the raw JSON result.

Plus two additions to the DSL itself, both usable from any pipeline
(not widget-specific):

- **New `split_channels` verb**: splits an image into a 3-item list
  (R, G, B), each a full image of the same type/size/content as the
  source except with the other two channels zeroed out.
- **No new "display an image" verb** — `open_image` (already in
  `VERB_REGISTRY`) already does exactly this via the existing
  `OpenImage` tempui mechanism. Confirmed by reading `pipeline_dsl.py`
  before assuming a new verb was needed.

The widget's own default pipeline demonstrates both:
`split_channels | map +| open_image |+`.

## Affected files

- **New: `widgets/pipeline/widget.json`**, **`widgets/pipeline/widget.py`**
  — the widget itself.
- **Modified: `src/desk/pipeline_dsl.py`**
  - `run_pipeline` gains an `initial_value: Any = None` keyword
    parameter (backward compatible — every existing caller, just
    `desk_mcp_server.py`, passes only `text` and keeps starting from
    `None`).
  - New public `StageInfo` dataclass + `parse_pipeline(text, registry=None)
    -> list[StageInfo]`: parses (never executes) a pipeline into a
    plain, introspectable structure — the same grammar `run_pipeline`
    uses, `ValueError` for the same structural problems. Built for the
    widget's diagram; reuses the existing private `_parse_stages`
    under the hood rather than duplicating any grammar logic.
  - New `split_channels` verb (see "The `split_channels` verb" below),
    added to `VERB_REGISTRY`.
- **Modified: `src/desk/shell/canvas.py`** (`WorkspaceView`) — lets a
  widget opt into handling its own local-file drops (see "Canvas
  drop-delegation" below). General, not Pipeline-widget-specific.
- **Modified: `src/desk/shell/desk_mcp_server.py`** — `desk_run_pipeline`'s
  tool description gains `split_channels` in its verb list.
- **Modified: `src/desk/temp_ui.py`** — mint one new tag (agent-facing:
  a new pipeline verb) covering both the verb and the widget briefly;
  `CURRENT_TAGS` + a `_NEW_FEATURES` entry.
- **New: `tests/verify/verify_pipeline_dsl_split_channels.py`** —
  `split_channels`/`parse_pipeline`/`run_pipeline`'s new
  `initial_value` param.
- **New: `tests/verify/verify_pipeline_widget.py`** — the widget's own
  pure-logic pieces (mermaid generation, drop-target state) plus a
  real `build()` instantiation.
- **New: `tests/verify/verify_canvas_drop_delegation.py`** — the
  `WorkspaceView` change in isolation.

## Canvas drop-delegation (why this needs a `canvas.py` change at all)

`WorkspaceView.dragEnterEvent`/`dragMoveEvent`/`dropEvent`
(`src/desk/shell/canvas.py`) currently intercept *any* local-file drag
unconditionally — the instant `event.mimeData()` carries a local file
URL, the view accepts it itself and (on drop) emits `files_dropped`,
without ever calling `super()...Event(event)`. That skips
`QGraphicsView`'s own default behavior of forwarding the event to the
scene, which is what would otherwise let a `QGraphicsProxyWidget`
holding a `WidgetFrame` (and *its* embedded content widget — Qt
natively supports drag-and-drop propagation into an embedded widget
for exactly this reason) receive and handle the drop itself. So today,
dropping a file anywhere on the canvas — even squarely on top of an
existing widget's own drop target — always opens a *new* widget at
that position; nothing already on the canvas ever gets a chance to
claim the drop.

Fix: before doing the existing canvas-level handling, check whether
the scene item under the drop position is a `QGraphicsProxyWidget`
whose embedded widget tree has some descendant with
`acceptDrops()` true at that exact point (via `QWidget.childAt` +
walking up `parentWidget()`); if so, let the event fall through to
`super()...Event(event)` — native Qt Graphics-View forwarding handles
the rest, delivering to that descendant's own `dragEnterEvent`/
`dropEvent`. Otherwise, canvas-level handling proceeds exactly as
before.

This is a small, general mechanism (`_drop_target_widget_at(scene_pos)`
+ three call sites), not special-cased to the Pipeline widget — any
future widget can opt in the same way, by calling
`self.setAcceptDrops(True)` on whichever of its own child widgets
should own drops landing on it and implementing that child's own
`dragEnterEvent`/`dropEvent`.

## The `split_channels` verb

```python
def split_channels(piped: dict) -> list[dict]:
```

Reads `piped["path"]`, loads it via `QImage` (already a Desk
dependency through PyQt6 — no new dependency per `CLAUDE.md`'s "avoid
adding dependencies, prefer bespoke solutions"; no Pillow/numpy
involved). Converts to `QImage.Format.Format_RGBA8888` deliberately —
Qt's one *byte-ordered* 32-bit format, where the in-memory byte order
is always R, G, B, A regardless of host endianness (unlike
`Format_ARGB32`, whose 32-bit-int packing means the byte order differs
between big- and little-endian platforms) — so the channel-zeroing
step below doesn't need any endianness handling.

Zeroing is done with one strided slice assignment per channel
(`buf[offset::4] = zeros`) rather than a per-pixel Python loop —
confirmed this is meaningfully faster for a several-megapixel photo
(a nested-loop `QImage.setPixelColor` version was tried first and
was slow enough on a real test photo to be a real UX problem, not a
hypothetical one) and needs no new dependency to get it (a `bytearray`
extended slice with a step is a plain-Python, C-implemented bulk
operation).

Writes each of the three resulting images as a new PNG into the
current Desk's `.desk_temp/` (`current_context.get_current_desk_directory()`
+ `TEMP_UI_DIRNAME`, the same directory `open_image` already writes
into) with a short random-prefixed name, and returns
`[{"path": <str>, "channel": "R"}, {"path": ..., "channel": "G"},
{"path": ..., "channel": "B"}]`, R/G/B order. Each entry's `"path"` is
exactly the shape `open_image` already expects
(`open_image(piped: dict)` reads `piped["path"]`), so
`split_channels | map +| open_image |+` opens all three without
either verb needing to know about the other.

Raises (never silently no-ops, matching every other verb's fail-fast
contract):
- `ValueError` if `QImage(path).isNull()` (not a loadable image file).
- `RuntimeError` if there's no current Desk directory, or its
  `.desk_temp/` doesn't exist yet, or a save fails.

No GUI-thread dispatch needed — unlike `reveal_widget`/
`screenshot_widget`/etc. (which call through `_call_gui` because they
touch the live `DeskWindow`), `QImage` pixel manipulation and
`.save()` don't touch any window/widget and are documented as safe of
the GUI thread.

## `parse_pipeline` / `StageInfo`

```python
@dataclass
class StageInfo:
    kind: str  # "verb" | "py" | "map"
    verb: str | None = None
    args: list[str] | None = None
    sub_stages: list["StageInfo"] | None = None


def parse_pipeline(text: str, registry: dict[str, Callable] | None = None) -> list[StageInfo]:
```

A thin public wrapper: `_parse_stages(text, registry or VERB_REGISTRY)`
then a recursive conversion from the existing private `_ParsedStage`
(which stays private and unchanged) into `StageInfo` (public,
`py_source` deliberately dropped — the widget only ever shows a fixed
`"N. py:"` label for a `py:` stage, never renders the decoded source
into the diagram). Raises the same `ValueError`s `run_pipeline` raises
upfront, for the same reasons — this *is* `run_pipeline`'s own parse
step, just without the execute step after it.

## The widget

### Layout (top to bottom)

1. A one-line label ("Pipeline:") + a small `QPlainTextEdit` holding
   the pipeline text, pre-filled with
   `split_channels | map +| open_image |+`.
2. A row: the `_DropTarget` ("Input" box) + a "Run" button.
3. The diagram: an `SvgView` (`desk.svg_view`, the same class the
   Markdown widget's own Mermaid rendering uses), stretch-1.
4. A one-line status label (last run's outcome, or a parse-error
   message).
5. A read-only `QPlainTextEdit` showing the last run's full JSON
   result (`{"ok", "stages", "value", "traceback"}`).

### `_DropTarget`

A small `QFrame` subclass: `setAcceptDrops(True)`, a centered,
non-selectable `QLabel` reading `"Input\n(drop an image here)"` (or
`"Input\n<filename>"` once set — labels non-user-selectable per
`CLAUDE.md`'s UI-labels rule), a dashed border that highlights on
`dragEnterEvent` (reverted on `dragLeaveEvent`), only ever accepts a
local file URL whose suffix is a known raster-image extension.
`dropEvent` stores the path (`.path()` accessor for the Run handler)
and emits `file_dropped(Path)`; referenced in place, never copied
(matching the canvas's own by-reference drop for non-image files) —
`split_channels` just reads it once, synchronously, at Run time.

Relies entirely on the canvas drop-delegation change above; nothing
image-viewer- or window.py-specific is duplicated here.

### Diagram generation (private to the widget, not in `pipeline_dsl.py`)

`_to_mermaid_flowchart(stages: list[StageInfo], statuses: list[dict] | None) -> str`
builds `flowchart LR` source text: a synthetic `input((Input))` circle
node, one `[...]` rect node per top-level stage in order (`"N. verb
arg1 arg2"` / `"N. py:"` / `"N. map"`), plain `-->` edges between
them, and a synthetic `output((Output))` circle node at the end.

**The `map`-as-explicit-node workaround:** `desk.mermaid`'s flowchart
support has no `subgraph` grouping (a `subgraph` line is parsed and
skipped — its nodes flatten into the top level — per `diagrams.md`'s
"Known limitations", confirmed by reading `src/desk/mermaid.py` and
`diagrams.md` directly rather than assuming) and no `classdef`/`style`
(so no color-coding either). A `map` stage's own node therefore gets
two extra edges instead of a nested box: `mapNode -->|each item|` into
its sub-pipeline's own small node chain (recursively built the exact
same way, supporting a nested `map` inside a `map` since the DSL
itself allows that), and the sub-chain's last node `-->|collected|`
back into `mapNode` — this is a legitimate small cycle in the graph
(the renderer's own "Self-loops and cycles" support, per `diagrams.md`,
confirmed cycle-safe), and reads as "branches out to a repeated
sub-process, comes back with the collected results" without claiming a
containment the renderer can't actually draw.

Node ids are built from stage position (`s1`, `s1_1`, `s1_2`, ...) —
always `[A-Za-z0-9_]+`, matching `_NODE_RE`. Labels are sanitized
(`[`/`]` replaced with `(`/`)`) since those are the one pair of
characters that would break out of a rect node's own `[...]` syntax;
no other shape is ever used for a stage node, so no other bracket
pair needs escaping.

After a Run, `statuses` (the top-level `result["stages"]` list — a
`map` stage's own per-item detail isn't in that list, so only
top-level nodes ever get annotated, never sub-pipeline nodes) appends
`" -- OK"` or `" -- FAILED: <reason, truncated>"` to the matching
node's label before the next render; a stage past where a fail-fast
run stopped has no entry in `statuses` at all and stays unannotated.

Regenerated (debounced, 300ms via a `QTimer`) on every pipeline-text
edit, and again immediately after every Run. A pipeline that doesn't
parse shows a plain-text fallback message in place of the diagram —
never lets a `ValueError` while typing propagate anywhere -- matching
the Markdown widget's own graceful-fallback precedent for a bad
Mermaid fence.

### Run

Requires the drop target to have a path first (shows a status message
and does nothing otherwise — no silent no-op, no crash from
`split_channels` hitting `piped["path"]` on `None`). Calls
`pipeline_dsl.run_pipeline(text, initial_value={"path": str(input_path)})`;
a `ValueError` (malformed pipeline text) shows in the status label. On
a structurally valid run (success or a stage failure — both are the
same result-contract dict, not an exception), updates the status
label, dumps the full result as JSON into the output box, and
re-renders the diagram with the new per-stage statuses.

## Verification

`tests/verify/verify_pipeline_dsl_split_channels.py`:
- `split_channels` on a small hand-built solid-color test image (write
  a tiny known-RGB PNG via `QImage` itself in the test, no fixture
  file needed): each of the three results loads back with `QImage`,
  is the same size as the source, and has exactly the expected
  channel value preserved / other two zeroed (checked pixel-by-pixel
  on a tiny, e.g. 2x2, image — cheap enough for a test even without
  the bulk-slice optimization).
- Alpha is preserved unchanged across all three outputs for a source
  with a non-255 alpha.
- `ValueError` for a non-image file path; `RuntimeError` for no
  current Desk directory / no `.desk_temp/`.
- End-to-end: `run_pipeline("split_channels | map +| open_image |+", initial_value={"path": ...})`
  against a temp Desk directory + the existing `_FakeWindow`-style
  registration succeeds, and three `OpenImage` tempui files land in
  `.desk_temp/` (reusing the existing `open_image` verb test's own
  assertions shape from `verify_pipeline_dsl.py`).
- `parse_pipeline`: matches `run_pipeline`'s own stage shapes for a
  plain pipeline, a `py:` stage, and a nested `map`; raises the same
  `ValueError`s for the same malformed input `run_pipeline` already
  covers (reuse existing malformed-input cases, don't re-invent them).
- `run_pipeline`'s new `initial_value` param: omitted still behaves
  exactly as before (starts from `None`); passed, the first stage
  receives it instead.

`tests/verify/verify_canvas_drop_delegation.py`:
- Build a real `WorkspaceView` + scene (offscreen `QApplication`,
  matching `verify_relocate_promoted_widget_source.py`'s own setup
  shape) with one placed `WidgetFrame` whose content is a plain
  `QWidget` with `setAcceptDrops(True)` and a `dropEvent` override
  recording what it received. Simulate a local-file drop at a scene
  position: (a) landing on that widget's bounds — the content widget's
  own `dropEvent` fires (native Qt proxy-widget forwarding, via
  `super().dropEvent(event)`), `files_dropped` does *not* emit; (b)
  landing on empty canvas — unchanged existing behavior, `files_dropped`
  emits, the content widget's `dropEvent` never fires.
- **Delegation is purely structural (any `acceptDrops()` descendant
  under the cursor), not "only if that widget will actually accept
  this payload."** A drop landing on a drop-accepting widget that then
  itself ignores this particular mime type (e.g. a non-image file
  dropped on the Pipeline widget's own image-only "Input" box) is
  simply not handled by anyone — it does *not* fall back to
  canvas-level "open a new widget" handling. Considered synthesizing
  the event and checking `event.isAccepted()` before deciding whether
  to still do the canvas-level fallback; rejected as needless
  complexity for a case with an obvious, more defensible answer: a
  drop the user visibly aimed at an existing widget's own drop zone
  should never silently redirect into opening some *other*, unrelated
  new widget behind/on top of it. Covered directly: a drop-accepting
  widget whose own `dragEnterEvent`/`dropEvent` ignores the payload
  results in no `dropEvent` fallback anywhere and no `files_dropped`
  emission — the drop is simply rejected.

`tests/verify/verify_pipeline_widget.py`:
- `_to_mermaid_flowchart` output actually parses via
  `desk.mermaid.parse` (the real parser, not a re-implementation of
  its grammar) for: a plain multi-verb pipeline, a `py:` stage, a
  `map` (confirms the node count/edge shape, including the
  branch-out/branch-back edges), and a nested `map` inside a `map`.
  Also confirms label sanitization: a verb arg containing `[`/`]`
  round-trips without breaking the surrounding node's own brackets.
- Status annotation: given a `result["stages"]` shorter than the full
  parsed stage list (a fail-fast partial run), only the attempted
  stages' nodes get annotated.
- `_DropTarget`: a simulated drop of a non-image file is ignored
  (`.path()` stays `None`); a real image-suffix drop sets `.path()`
  and emits `file_dropped`.
- `build()` returns a real `PipelineWidget` instance under an
  offscreen `QApplication`, with the default pipeline text present and
  the drop target empty.

Full `tests/verify/` regression suite run after, to confirm nothing
else regressed (in particular: `verify_pipeline_dsl.py`'s existing
`open_image`/registry-shape coverage, and anything exercising
`WorkspaceView`'s existing file-drop behavior).

Also: a step of this plan's verification is opening the actual widget
in a running Desk and manually dragging a real photo onto "Input",
clicking Run, and confirming the diagram updates and three Image
Viewer instances open with the three channels. If launching the
browser/GUI isn't available in this environment, that manual step is
noted as skipped rather than silently omitted (per
`shared_development_process.md`'s verification step 5).

## Key design decisions

- **No new "display an image" verb.** `open_image` already does this;
  adding a second verb with the same effect would just be an
  unnecessary duplicate name in the registry. Confirmed by reading
  `pipeline_dsl.py`'s existing registry before assuming one was
  missing.
- **`map`'s sub-pipeline is drawn as an explicit branch-out/branch-back
  node pair, not a nested subgraph box**, because the renderer
  genuinely can't draw the box (not a stylistic choice — a hard
  capability limit of `desk.mermaid`, confirmed by reading it).
- **The dropped input image is referenced by path, never copied into
  `.desk_temp/`.** Nothing about the pipeline needs the file to
  outlive one synchronous Run; copying it would just be unused
  bytes left behind on every drop.
- **`split_channels` writes its own three outputs into `.desk_temp/`
  (never overwrites/reuses the input file's own location)** — matches
  `open_image`'s own existing convention for verb-generated temp
  images, and keeps the source file untouched regardless of where it
  came from (could be anywhere on disk, not necessarily inside the
  current Desk directory at all).
- **Canvas drop-delegation is a general opt-in mechanism, not
  Pipeline-widget-specific** — the alternative (hard-coding "if this
  is the Pipeline widget, route drops differently" inside
  `canvas.py`/`window.py`) would tie unrelated canvas code to one
  widget's existence; the `acceptDrops()`-based delegation costs
  about the same amount of code and works for any future widget that
  wants its own drop target.
