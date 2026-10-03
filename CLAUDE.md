# Project instructions

- avoid adding dependencies, prefer bespoke solutions.
- use paths relative to the current project directory rather than absolute ones.
- read and follow ./development-process.md.

- generally, the labels for UI elements should not be user-selectable, unless that is specifically requested.

- For code that will run in a web browser (TypeScript strictness, static imports, template/slot conventions), read and follow ./browser-frontend.md.

- `deprecated-docs/` holds documentation of replaced/removed APIs, for deep-dive history investigations only. Do not read, grep into, quote or link to it during normal work; the current API is documented elsewhere, and keeping outdated docs out of context is the point.
