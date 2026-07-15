# Plan: TODO 585d235 (COMPLETED) — move `MEDIATED-EVENT-LOG.tsv` into `.desk_temp/`

## Summary

`desk.event_mediator.EventMediator` currently logs every published event
to `MEDIATED-EVENT-LOG.tsv` directly in the current Desk's project
directory (`DeskWindow._refresh_picker` calls
`self._event_mediator.set_log_directory(self.current_desk.directory)`).
This is Desk-generated, ambient bookkeeping — the same category of thing
`.desk_temp/` already holds (crash logs, tempui docs, custom-widget
source) — so it should live there instead of alongside the user's own
project files. `widgets/event_log/widget.py` independently computes the
same path today (it doesn't ask `EventMediator.log_path`), so it needs
the identical change.

## `src/desk/shell/window.py`

`_refresh_picker`'s existing line:

```python
self._event_mediator.set_log_directory(self.current_desk.directory)
```

becomes:

```python
self._event_mediator.set_log_directory(self.current_desk.directory / TEMP_UI_DIRNAME)
```

`TEMP_UI_DIRNAME` is already imported from `desk.temp_ui` in this file.

## `widgets/event_log/widget.py`

Its `_bind`-style setup (around the existing `directory =
current_context.get_current_desk_directory()` /
`self._log_path = directory / LOG_FILENAME` lines) needs the same `/
TEMP_UI_DIRNAME` inserted: `self._log_path = directory / TEMP_UI_DIRNAME
/ LOG_FILENAME`. Import `TEMP_UI_DIRNAME` from `desk.temp_ui`.

## Behavior note (not a code change, just documented here)

`EventMediator._log` already does `path.parent.mkdir(parents=True,
exist_ok=True)` before writing a row. Once the log lives under
`.desk_temp/`, this means `.desk_temp` itself would get silently created
the first time any event is published, if it doesn't already exist —
bypassing the confirm-gated `.desk_temp`-creation flow elsewhere (TODO
`4716585`, `NewDeskDialog` / the "Temporary UI" confirm prompt). In
practice this is very unlikely to matter: `.desk_temp` is provisioned
before any widget is placed on Desk open/switch/new-Desk (`switch_desk`
already provisions it up front), so by the time any widget could publish
an event, `.desk_temp` already exists either way. Not treated as a bug to
fix here, just called out so it isn't a silent surprise later.

## Verification

- `EventMediator.log_path` resolves to `<directory>/.desk_temp/
  MEDIATED-EVENT-LOG.tsv` after `set_log_directory(directory /
  TEMP_UI_DIRNAME)`, both for a fresh directory and one where
  `.desk_temp` doesn't exist yet (confirms the mkdir side effect noted
  above, doesn't treat it as a failure).
- A real publish through `DeskWindow`-like wiring (unbound-method-on-a
  -fake-double pattern, matching this project's established test shape)
  writes the row under `.desk_temp/MEDIATED-EVENT-LOG.tsv`, not the
  project directory.
- Event Log widget: `_log_path` computed the same way, watcher watches
  the new location, and reading/parsing/Clear-action all still work
  against it.
- Full scratchpad regression suite (`git stash` before/after) to confirm
  no new failures beyond the existing known-stale set.
