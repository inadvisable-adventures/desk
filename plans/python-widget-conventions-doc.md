# Python widget conventions doc (COMPLETED)

TODO d4c0d68, from `../FEEDBACK/FEEDBACK-DESK-painted-combo-crash-and-enforcement-gap-2026-10-16-1836.md`.

## Summary
Document the "use `qt_controls`, not native Qt controls" rule for Desk's own code and for agents in other projects.

## Approach
- `python-widget-conventions.md` at the root (qt_controls rule, popup rules, verification rule), referenced
  from `CLAUDE.md` like `browser-frontend.md`.
- Agents in other projects can't read this repo's root, so the rule is stated self-contained in the tempui
  docs: the top-level doc's "Project widgets" section (the section the TODO called `tempui-custom-widgets.md`'s
  project-widgets section; it lives in the top-level doc) and a one-line pointer in the porting doc.
- Tag `python widgets use qt_controls, not QComboBox #514695` in `CURRENT_TAGS` plus a `_NEW_FEATURES` entry.
- `verify_python_widget_conventions_doc.py`. The porting-doc test rejects `desk.shell.` in that doc (it reads
  `desk.<namespace>.` as a Bridge API), so the pointer there names only the `qt_controls` package.

## Verification
All `*tempui*`, changelog, versioning and deprecated-docs scripts pass.
