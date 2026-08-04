# FEEDBACK review (TODO `feff1ec`)

Written per TODO `feff1ec` ("review and discuss all of the new FEEDBACK
items with user"). Records the discussion had with the user about the
FEEDBACK items current at the time of the first pass, plus a second
pass after re-scanning `../FEEDBACK/` (relative to this repo's root)
turned up five more that had appeared in the meantime. This is a
discussion record, not a design doc — no decisions were finalized here;
see the "Where things were left" section at the end.

## Sources read

All paths below are relative to this repo's root (`desk/`).

**Already read/discussed before the first pass, for context (found via
earlier grepping of `TODO.md`/`PARKINGLOT.md`, not re-read in full for
this investigation):** TODO `4ab5875` (hex_flower investigation,
COMPLETED) and its associated `PARKINGLOT.md` entry ("`kind: "html"`
widget robustness and docs"), and TODOs `7c7b676`/`a820354` (both
COMPLETED, and — as it turned out — a full fix for one of the FEEDBACK
items below).

**First pass — read in full:**

- `DESK_FEEDBACK-2026-07-13T012144.md` (this repo's own root, not
  `../FEEDBACK/` — an older, differently-named convention: an
  investigation+feedback doc Desk itself produced about its own
  `widgets/hex_flower`)
- `../FEEDBACK/FEEDBACK-DESK-app-structure-dsl-and-editor-widget-2026-08-03-1634.md`
- `../FEEDBACK/FEEDBACK-DESK-batch-ingestion-job-concept-2026-08-03-1634.md`
- `../FEEDBACK/FEEDBACK-DESK-claude-md-relative-paths-2026-08-03-1604.md`
- `../FEEDBACK/FEEDBACK-DESK-existing-app-decomposition-process-2026-08-03-1719.md`
- `../FEEDBACK/FEEDBACK-DESK-external-service-dependency-concept-2026-08-03-1634.md`
- `../FEEDBACK/FEEDBACK-DESK-new-desk-in-existing-project-source-diving-2026-08-03-1506.md`
- `../FEEDBACK/FEEDBACK-DESK-stale-build-widget-script-defeats-capabilities-fix-2026-07-31-1445.md`
- `../FEEDBACK/FEEDBACK-DESK-tempui-convention-drift-notification-2026-07-30-1120.md`
- `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
- `../FEEDBACK/FEEDBACK-DESK-widget-titlebar-subtitle-api-2026-08-03-1830.md`

Also present but explicitly out of scope (not about Desk):
`../FEEDBACK/FEEDBACK-CLAUDECODE-subagent-deep-research-skill-anomaly-2026-07-20-1858.md`
— an anomaly report about Claude Code/agent-orchestration tooling
itself, written from a `world-timelines` session but not a Desk issue.
Noted to the user; not analyzed further here.

**Second pass — `../FEEDBACK/` re-scanned per the user's follow-up
request; five new files had appeared since the first pass (all dated
2026-08-04, all from a project called `collage-for-desk`):**

- `../FEEDBACK/FEEDBACK-DESK-error-indicator-empty-message-noop-2026-08-04-1305.md`
- `../FEEDBACK/FEEDBACK-DESK-promoted-widget-source-of-truth-2026-08-04-1321.md`
- `../FEEDBACK/FEEDBACK-DESK-pypdf-optional-dependency-as-stopgap-2026-08-04-1535.md`
- `../FEEDBACK/FEEDBACK-DESK-questions-md-format-undocumented-and-brittle-2026-08-04-1347.md`
- `../FEEDBACK/FEEDBACK-DESK-transform-discovery-staleness-2026-08-04-1301.md`

`./investigations/` (this directory) was also checked for anything
new/feedback-related, per the same request — it holds three files
(`live_transcription_chunking.md`, `shutdown_perf.md`,
`whisper_prompting.md`), all pre-existing session research on
speech/mic topics, unrelated to FEEDBACK review. Nothing new or
relevant there.

`../FEEDBACK/implemented/` (eight files, all already `COMPLETED` in
`TODO.md`) was not re-read in full — used only to confirm which
concerns are already closed.

## First-pass discussion (recorded as given to the user)

I read through all the current feedback: the one local
`DESK_FEEDBACK-2026-07-13T012144.md` in this repo, and the ten
not-yet-`implemented/` `FEEDBACK-DESK-*.md` docs in `../FEEDBACK/`
(there's also one `FEEDBACK-CLAUDECODE-*` doc, but it's about Claude
Code tooling itself, not Desk — out of scope here unless the user
wants it looped in separately).

Grouped by theme, with the connections found between them:

**Already done — just needs archiving**
- `tempui-convention-drift-notification` (Scratch note on doc-version
  bump, log line on promotion's no-source-found path) is fully covered
  by TODOs `7c7b676`/`a820354`, both completed earlier in this session.
  It should move to `../FEEDBACK/implemented/`.

**One bug, cited by three separate feedback docs as the top blocker**
- Multi-file `kind: "html"` widgets silently fail to load: relative
  -path `<script src>`/`<link href>` requests don't carry the
  per-launch auth token, get 401'd, and the module graph dies with
  zero console output. Root-caused in the local `DESK_FEEDBACK` doc
  (hex_flower), already logged in detail in `PARKINGLOT.md` with a
  proposed fix (a same-origin cookie alongside the existing
  query-param/header checks) — but never promoted to an active TODO.
  `widget-extraction-communication-gaps` independently flags it as
  *the* prerequisite blocker for splitting any multi-component app
  into widgets. This feels like the highest-leverage single fix in the
  whole batch.

**Small, concrete, mostly independent fixes**
- `claude-md-relative-paths` — one line in our own `CLAUDE.md`.
- `widget-titlebar-subtitle-api` — a `desk.self.setSubtitle()` Bridge
  call; fairly well-scoped, the routing plumbing already mostly
  exists.
- `stale-build-widget-script-defeats-capabilities-fix` — an old seeded
  `scripts/build_widget.py` silently diverges from
  `.desk_temp/build_widget.py` and drops `capabilities`; plus two
  smaller unrelated gaps (Bridge client errors lack a `.status`
  property; unpromoted `DefineWidget` build output never gets cleaned
  up, alphabetical-not-chronological reload risk).
- `new-desk-in-existing-project-source-diving` — several small
  seeding/doc gaps from adopting the shared dev-process split into an
  existing project (no breadcrumb note, missing how-to doc,
  `todo_item_ids.py` doesn't handle a few real `TODO.md` phrasings,
  `../FEEDBACK/` convention isn't in the canonical shared doc).

**One shared underlying primitive, proposed from two angles**
- `batch-ingestion-job-concept` (a job that runs to completion: typed
  params, progress protocol, managed subprocess w/ auto-restart, run
  history, citation/provenance reporting) and
  `external-service-dependency-concept` (a `depends_on` manifest field
  for a long-running backend a widget needs up) both explicitly say
  they want the same managed-subprocess-lifecycle primitive, just
  configured differently (finite vs. indefinite). Worth designing
  once.

**Cross-widget communication / porting a real multi-component app —
the biggest, most speculative cluster**
- `app-structure-dsl-and-editor-widget` (a DSL + codegen + editor
  widget for the wiring/layout/event-table/worker/cache code of a
  hand-built SPA) and `widget-extraction-communication-gaps` (shared
  state store, shared cache, shared worker, typed event payloads, a
  home for cross-cutting orchestration rules) are two views of "how
  would a real, multi-piece existing app actually become several
  interoperating Desk widgets." `existing-app-decomposition-process`
  sits on top of both — it's not a Desk feature request so much as a
  proposed *methodology* (inventory → categorize → research →
  synthesize) for doing this kind of decomposition well, with a
  suggestion to write it up as a doc now and maybe build tooling
  around it later (and it explicitly proposes the Job primitive above
  as a second use case for validating that design).

Things that stood out before prioritizing: the auth-token bug is
small, well-understood, and unblocks real work (both the
extraction-communication feedback and any future multi-file `html`
widget) — it seems like it should jump the queue regardless of what
else gets decided. The DSL/state-store/porting-process cluster is the
real design conversation — three documents' worth of genuinely good
thinking, but speculative and general in a way that could grow
arbitrarily large if not scoped deliberately (e.g. how much of the DSL
to actually build vs. treat as a documented direction).

Question put to the user: start with the auth-token bug first since
it's small and unblocking, or get the big picture on the
multi-component/porting cluster first so we know what shape a fix even
needs to support? -- **not yet answered; the user instead asked for
this write-up plus a re-scan before continuing the discussion.**

## Second pass: five new items from `collage-for-desk`

Unlike the `world-timelines` batch above (mostly speculative design
surveys), every item in this second batch is a *confirmed, concretely
-diagnosed bug or gap* hit while actually building one project's PDF
Viewer widget (TODO `0ba6f28` in that project) — file:line citations
throughout, not proposals from inspection alone.

**A recurring pattern worth naming on its own**: at least three of the
five (`error-indicator-empty-message-noop`,
`questions-md-format-undocumented-and-brittle`, and the relocation bug
inside `promoted-widget-source-of-truth`) are the same shape of
failure — a real, already-anticipated case (an empty error message
that's still a real error; a heading that doesn't match the parser's
actual required format; a keyword that doesn't match its source
directory's name) gets silently treated as equivalent to "nothing
happened," with zero diagnostic surfaced anywhere in the chain. Worth
discussing as a class, not just fixing four unrelated one-offs —
e.g. whether Desk wants a standing convention ("a code path that
decides something didn't happen must be able to distinguish that from
genuinely-nothing-to-report") rather than re-discovering this same bug
shape project by project.

**Small, well-scoped, mostly self-contained fixes:**

- `error-indicator-empty-message-noop` — the `[ERROR]` titlebar button
  can light up and then do nothing when clicked, because the click
  handler infers "was there an error" from the captured message
  string's truthiness, but the capture code already has a documented
  `or ""` fallback for a real error with no usable text. Fix: an
  explicit `_has_error: bool` on `WidgetFrame`, decoupled from
  `last_error_message`'s content; fall back to a placeholder string
  when showing an error with empty text instead of not showing it at
  all.
- `questions-md-format-undocumented-and-brittle` — `desk-temporary-ui
  .md`'s documented `QUESTIONS.md` heading format
  (`## <short summary>`) doesn't match what
  `questions_file.py`'s actual parser requires (`## TODO
  \`<id>\`[/\`<id2>\`...]: <summary>`, literal leading `TODO`,
  backtick-wrapped id) — and an entry that doesn't match doesn't
  partially parse, it vanishes entirely (silently absorbed into
  `preamble`), so neither the widget nor the top-right notification
  ever shows anything. Two possible fixes offered: fix the doc to
  match the code (and state plainly that a free-standing,
  non-TODO-linked question isn't supported), or relax the parser to
  accept an id-less heading if free-standing questions are meant to be
  legitimate (the doc's own framing reads that way) — either way, stop
  the parse from being silently all-or-nothing.
- `transform-discovery-staleness` — `TransformsService` only ever
  calls `discover()` at Desk startup/Desk-switch, so a transform added
  or edited during an already-open Desk session (the only way an agent
  ever adds one) is invisible until something happens to trigger a
  refresh, with a cryptic `Unknown transform: ... (call discover()
  first)` in the meantime. Also, even a manual re-discover doesn't
  help an *edited* Python transform (only a newly-added one), since
  `self._python_modules` is never invalidated. Fix: retry `discover()`
  once on a lookup miss before raising; track each transform's
  mtime/hash and reload on a staleness check, mirroring what the
  JS/TS path's `_resolve_js_entry` partially already does.

**A larger, multi-part item:**

- `promoted-widget-source-of-truth` — three related findings from one
  incident: (1) a confirmed bug where `[TEMPUI]` promotion's
  source-relocation step looks up the source directory by the tempui
  DSL keyword (CamelCase, e.g. `PdfViewer`) when the real convention
  names the directory in kebab-case (`pdf-viewer`) — so relocation
  silently no-ops for very close to *every* real-source widget, not a
  rare miss; (2) a design recommendation that a promoted widget's
  `.desk`-file entry should reference its source (plus a
  `.desk_temp/`-cached build) rather than freeze a base64 blob at
  promote time, since editing the source after promotion currently has
  no path back into the saved definition at all and the two silently
  diverge; (3) a doc-gap/process recommendation that an agent building
  a widget the user explicitly asked for should skip the
  tempui/promote dance entirely and author directly into a real,
  project-level `desk_widgets/` directory from the start (reserving
  tempui for speculative, agent-initiated widgets) — which would need
  a second `discover_widgets()` call against the project directory,
  something `desk.widgets.discover_widgets` is already
  kind-agnostic/path-parameterized enough to support without change.
  Findings (2) and (3) are naturally the same underlying change (make
  `desk_widgets/` a first-class, independently-discoverable location).

**Narrower, and touches a standing project convention directly:**

- `pypdf-optional-dependency-as-stopgap` — asks that Desk add `pypdf`
  as an optional dependency (an extra, not a hard requirement) for PDF
  outline/bookmark extraction, on the grounds that it has to be a
  Desk-level change, not a project-level one: `kind: "python"`
  transforms run in-process inside whichever venv is actually running
  Desk, so a project-scoped `desk_transforms/` transform can't pull in
  a library Desk's own `pyproject.toml` doesn't already depend on. The
  user had already approved `pypdf` specifically for this via a
  `QUESTIONS.md` answer in that other project. Explicitly framed as
  provisional against `PARKINGLOT.md`'s already-parked "file/stream
  format DSL" idea (a declarative, format-agnostic alternative), not a
  precedent for "add a library per file format." This is the one item
  in the whole batch that runs directly into
  `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke solutions"
  instruction — the case made is that a bespoke solution isn't
  realistic here (hand-rolling PDF object-graph/outline parsing), so
  it's worth discussing as a real exception rather than either
  reflexively declining or reflexively accepting.

## Where things were left

This is a discussion record, not a finished design — nothing above was
decided, planned, or implemented as part of writing this investigation
(per TODO `feff1ec`'s own scope: review and discuss only). Two things
are still open before any of this moves to actual TODO items/plans:

1. The original question from the first pass (start with the
   auth-token bug, or the big-picture porting/DSL conversation first)
   is still unanswered.
2. The second-pass batch adds a third, more actionable option: several
   of these five are small, well-diagnosed, low-risk fixes that could
   likely just become TODO items directly with little further design
   discussion needed (`error-indicator-empty-message-noop`,
   `transform-discovery-staleness`, the relocation-bug half of
   `promoted-widget-source-of-truth`) — versus items that still need
   real discussion before being scoped (the base64-vs-reference design
   in `promoted-widget-source-of-truth`, and the `pypdf`/dependency
   -policy question).
