# Desk

Desk is an environment for interacting with coding agents via a dynamic UX.

Desk is a python application which uses PyQt6. Its zoomable workspace is a
native Python/Qt canvas — not a web page.

Desk is a zoomable workspace.

Desk has widgets written in python, which render directly in the app as
native Qt widgets — no local server or browser involved. That's the
preferred/default way to write a widget: a `widget.py` exposing `build() ->
QWidget`, imported and embedded directly by Desk, following ordinary Qt
patterns. Widgets can be dynamically reloaded as needed: editing a widget's
source rebuilds it in place.

Desk also supports widgets written in html/css/typescript for cases where a
Desk user wants a custom, rich SPA-based widget. Those are backed by their
own embedded chromium (via QtWebEngine), which browses to an SPA served
locally by Desk's own Python webserver (also part of Desk, and part of the
same process). That mechanism is meant more for what Desk users build than
for Desk's own development — building and running Desk itself never
requires Node/npm/tsc, though Desk can still run those tools on behalf of a
widget that needs them.

Desk has a code editing widget which is aware that it is in desk and has access to the Desk.

Desk has a console widget which hosts bash so that it can run claude.

## Development setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

python -m desk
```

No Node/npm/`tsc` is needed to build or run Desk. If you author a
`kind: "html"` widget of your own (a custom SPA, e.g. in TypeScript), that
widget's own build step is yours to run — Desk doesn't require it.

See `design-docs/` for the architecture and `TODO.md`/`development-process.md`
for how work on this project is planned and tracked.

