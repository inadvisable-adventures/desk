# Dedicated `tempui-hmsvc.md` (TODO `879bfb4`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-docs-too-thin-forced-source-spelunking-2026-10-09-1400.md`.

## Summary

hmsvc had one sentence in the permanent tempui docs. New doc
`tempui-hmsvc.md` (mirrors `tempui-installed-jobs.md`): layout,
`service.py` contract, every `service.json` key, discovery timing,
management-only networking model, mandatory CORS (+ preflight), the
`hmsvc_client` calls, in-memory logs, worked example.

## Affected files

- `src/desk/temp_ui.py` -- `_HMSVC_DOC`, `HMSVC_DOC_FILENAME`,
  `SPLIT_DOC_CONTENT`, a new `desk.hmsvc.*` entry in the custom-widgets
  Bridge API list, a link from the porting doc, new changelog tag
  `#812810`.
- `tests/verify/verify_tempui_hmsvc_doc.py`.

## Decisions

- Facts transcribed from `hmsvc.py`/`hmsvc_host.py`/`hmsvc_client.py` and
  the existing `#285553`/`#892147` changelog entries; constants (log cap,
  startup timeout, default capabilities) are asserted against the code.
- The worked example is executed by the verify script (GET and preflight).
- Written for the original discovery behavior (no live watcher); TODO
  `c40c5c5` then updated the discovery section for the live watcher.
