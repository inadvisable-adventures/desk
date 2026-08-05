# Add pypdf as an optional dependency (TODO `742ba0a`)

## Summary

`kind: "python"` transforms run in-process, loaded via
`importlib.util.spec_from_file_location`/`exec_module` inside
`desk_services/transforms/service.py` — confirmed directly reading
that file. That means a transform can never bring its own
project-level Python dependency; whatever it imports has to already be
importable in whichever venv is actually running Desk. A project
needing real PDF structural parsing (outline/bookmark extraction,
resolving destinations to page numbers — genuine object-graph parsing,
not something to hand-roll) has no way to get that short of Desk
itself depending on a PDF library.

Per `../FEEDBACK/FEEDBACK-DESK-pypdf-optional-dependency-as-stopgap-2026-08-04-1535.md`
and discussion with the user (see `investigations/feedback_review.md`
for the fuller review this came out of): add `pypdf` as an **optional**
Desk dependency, not a hard one — most Desk projects never touch PDFs,
so this shouldn't grow the baseline install. Explicitly labeled as
provisional against `PARKINGLOT.md`'s parked "file/stream format DSL"
direction, while being honest that that direction is not near-term (it
needs "DSL" formalized as a general concept first, per `PARKINGLOT.md`
itself), so this should be expected to stick around, not treated as
imminently temporary.

The user also separately decided *not* to pursue, right now, the more
general alternative discussed (subprocess-isolated `kind: "python"`
transforms with their own project-scoped dependencies, avoiding the
need for Desk's own dependency list to grow per format) — that gets
recorded in `PARKINGLOT.md` as its own entry, cross-referenced here,
not designed or built as part of this item.

## Affected files

- `pyproject.toml` — add `pypdf` under `[project.optional-dependencies]`.
- `PARKINGLOT.md` — new entry for the subprocess-isolated-dependencies
  alternative (separate commit from this plan/implementation, since
  it's a park-for-later, not part of this item's own scope).
- `tests/verify/` — new coverage confirming the extra installs and
  imports correctly, and that a normal (non-`[pdf]`) install still
  doesn't depend on it.

## Design decisions

- **`[project.optional-dependencies]` (PEP 621), not a hard
  dependency.** `pip install desk[pdf]` (or `.[pdf]` from a source
  checkout) pulls in `pypdf`; a plain `pip install desk` does not.
  Matches the feedback's own suggested shape and keeps the common,
  PDF-free case dependency-free.
- **No code changes beyond the dependency declaration itself.** There
  is no PDF-handling transform or widget in *this* repo today — the
  actual consumer is a different project (`collage-for-desk`)
  authoring its own `desk_transforms/` transform that imports `pypdf`.
  This item's job is only to make that import possible when Desk is
  installed with the `pdf` extra; writing a reusable
  transform/widget wrapper around `pypdf` is out of scope (nothing
  asked for one, and inventing one without a concrete second consumer
  would be premature abstraction).
- **A comment in `pyproject.toml`, pointing at the parked DSL
  direction**, is the "provisional" labeling mechanism — cheap, sits
  right next to the dependency it's about, and doesn't require
  inventing a new place to record this kind of note.
- **No lazy-import/friendly-error wrapper added here.** The feedback
  suggested one ("a lazy import in the transform with a clear
  'install the pdf extra to use this' error if missing") as an
  alternative shape, but that's a concern for whichever transform
  actually does the importing (in the *other* project, not this
  repo) — there's nothing in Desk itself that imports `pypdf`
  conditionally, so there's no lazy-import site to add here.

## Step-by-step implementation

1. Add `[project.optional-dependencies]` to `pyproject.toml` with
   `pdf = ["pypdf"]`, and a short comment above it explaining the
   provisional framing (pointing at `PARKINGLOT.md`'s file/stream
   -format DSL entry).
2. Install the extra in the dev venv (`.venv/bin/pip install -e
   ".[pdf]"`) and confirm `import pypdf` succeeds.
3. New verify script confirming: the extra is declared correctly
   (parse `pyproject.toml`, check `pdf` extra lists `pypdf`), and that
   `pypdf` is actually importable once installed (real, not mocked --
   this repo's own venv will have it installed as part of verifying
   this item).
4. Add the `PARKINGLOT.md` entry for the subprocess-isolated
   -dependencies alternative, cross-referencing this TODO and the
   already-parked Job-primitive discussion from the `world-timelines`
   FEEDBACK batch. Separate commit (a parking-lot addition isn't part
   of "implementing" this TODO item).
5. Run the full `tests/verify/` regression suite.

## Key tradeoffs

- This is a real, if labeled, exception to `CLAUDE.md`'s "avoid
  adding dependencies, prefer bespoke solutions" instruction --
  discussed explicitly with the user and decided deliberately, not
  slipped in silently. `CLAUDE.md` itself is not being amended with a
  general exception policy as part of this item (not asked for; the
  provisional-labeling comment in `pyproject.toml` is judged
  sufficient context for this one case).
- "Stopgap" framing may be misleading long-term, since the DSL
  direction it's provisional against isn't close to existing --
  flagged directly in both `TODO.md`'s completion narrative (once
  written) and the `pyproject.toml` comment itself, so a future reader
  isn't misled into thinking removal is imminent.

## Verification

New script `tests/verify/verify_pypdf_optional_dependency.py`, real
(no mocking):
- `pyproject.toml`'s `[project.optional-dependencies]` declares a
  `pdf` extra containing `pypdf`.
- `import pypdf` succeeds in this repo's own venv (installed via the
  extra as part of implementing this item) and exposes the
  `PdfReader`/outline-related API the feedback's use case needs.
- Full `tests/verify/` regression suite (confirms nothing about
  making `pypdf` available broke anything else -- e.g. no accidental
  hard-dependency promotion).
