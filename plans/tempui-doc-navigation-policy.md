# Doc-navigation rule + dedicated-doc policy (TODO `601dae5`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-docs-too-thin-forced-source-spelunking-2026-10-09-1400.md`
(the "general gap" section). Companion to TODO `879bfb4`.

## Summary

(a) `desk-temporary-ui.md` tells an agent that finds a doc too thin to act
on to read that feature's `tempui-new-features.md` section before Desk's
source or another project's code, and to say so and offer a FEEDBACK file
if it had to read outside the doc set. (b) `development-process.md` gains a
standing policy: a feature needing more than a one-line mention gets a
dedicated `tempui-<feature>.md`, linked from its changelog entry and from
the higher-level doc.

## Affected files

`src/desk/temp_ui.py` (overview text in `DOC_TEMPLATE`, changelog tag
`#888639`), `development-process.md`,
`tests/verify/verify_tempui_hmsvc_doc.py` (3 checks added).

## Decisions

Both parts in one item/commit; (a) is agent-visible so it gets a changelog
tag, (b) is Desk-development-only. Verification is textual.
