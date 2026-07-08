# Packaging & distribution (PARKED)

## Summary

App bundling (e.g. PyInstaller) and installation/run instructions, so
Desk can be distributed to and run by someone without a Python dev
environment already set up.

## Status

**Blocked** — this item can't be implemented without answers to two
questions `design-docs/architecture.md`'s own Open Questions section has
already been carrying, unresolved, since early in this project:

- Distribution/packaging target (PyInstaller app bundle? a
  pip-installable CLI? something else?).
- Platform scope (macOS-only first, matching where all development and
  verification so far has actually happened, or cross-platform from day
  one?).

Both materially change the implementation (a PyInstaller `.app` bundle
vs. a `pip install desk-app` + console-script entry point are different
enough approaches — different handling of `QtWebEngine`'s bundled
Chromium, different signing/notarization needs on macOS, different CI
matrix if cross-platform) that guessing at an answer risks building the
wrong thing rather than making a reasonable default judgment call.

Questions added to `QUESTIONS.md`. No other local changes exist beyond
this plan file, `TODO.md`, and `QUESTIONS.md`, so nothing needed
branching off separately per `development-process.md`'s workflow.

**Update:** moved from `TODO.md` (`PENDING`) to `PARKINGLOT.md` — the two
questions above moved there with it (removed from `QUESTIONS.md`, which
is scoped to questions actively blocking a `TODO.md` item). This file
stays as the starting sketch for whenever it's picked back up.

## Affected files (once unblocked)

To be determined once the target/scope is known — likely
`pyproject.toml` (packaging metadata, entry point), a new
build/packaging config (PyInstaller spec file or equivalent), and a
`README.md`/`INSTALL.md` section with install/run instructions matching
whichever distribution shape is chosen.
