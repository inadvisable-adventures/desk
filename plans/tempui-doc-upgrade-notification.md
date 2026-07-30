# Plan: TODO 7c7b676 — notify when the tempui doc set silently upgrades

From `../FEEDBACK/FEEDBACK-DESK-tempui-convention-drift-notification
-2026-07-30-1120.md`: `ensure_docs_current` (`src/desk/temp_ui.py:1300`)
already computes whether a project's tempui doc set is stale (its
embedded version differs from `TEMPUI_DOC_VERSION`) and rewrites it in
place — the comparison result is computed and thrown away, so an agent
picking up a session has no signal that anything changed, and no
particular reason to open `tempui-breaking-changes.md` unless something
already seems broken.

## Design

### `ensure_docs_current` reports what it found

Change its return type from `None` to `tuple[bool, int | None]` —
`(rewrote, previous_version)`:

- `previous_version` is the doc set's own embedded version *before*
  this call, but **only** when it's a real, parseable version that
  actually differs from `TEMPUI_DOC_VERSION` — `None` otherwise
  (nothing rewrote, or the version already matched but a split file
  was merely missing, or the doc predates version-tracking (TODO
  `f7b1611`) entirely and has no version to report at all — none of
  these are "a convention changed" in the sense this feedback is
  about, just "the file set was topped up/repaired").
- `rewrote` is `True` whenever `write_tempui_docs` actually ran (kept
  even though the caller mostly only needs `previous_version`, for
  clarity at the call site and because a `None` return doesn't
  distinguish "nothing was stale" from "nothing to check" as cleanly).

Two existing call sites read this today with no return value used
(`tests/verify/verify_ensure_build_widget_script.py`,
`tests/verify/verify_tempui_doc_versioning.py`) — a plain signature
change, not a behavior change for them; check whether either asserts
anything about the function's own return value (unlikely, since there
currently isn't one) before touching them.

### `TempUiManager.provision` writes a `Scratch` note — deterministically, not via the watcher

Rejected approach: write the note file to `temp_dir` and let the
already-started file-watcher notice it the normal way (the same path
an agent's own new tempui file takes). This has a real race: `_start
_watching`'s underlying `get_service().watch(...)` may not have begun
observing the instant it returns, so a note written immediately
afterward isn't guaranteed to be seen — this class of "did the watcher
actually start observing in time" concern is exactly what earlier
`.desk_temp` watcher work here already had to reason carefully about
(TODO `578cb6b`'s migration, the atomic-write-lands-as-a-FileMovedEvent
gotcha).

Instead: write the note file directly, then **directly emit
`file_added` and update `_known_files`** — the same two things
`_handle_change` would eventually do for a watcher-observed new file —
bypassing any dependency on watcher timing entirely for this one,
synthetic, Desk-authored file:

```python
def provision(self, directory, ask_create_dir, ask_gitignore) -> Path | None:
    ...
    doc_path = temp_dir / DOC_FILENAME
    if not doc_path.is_file():
        write_tempui_docs(temp_dir)
        previous_version = None
    else:
        _, previous_version = ensure_docs_current(temp_dir)

    sync_shared_components(temp_dir)
    self._start_watching(temp_dir)  # clears self._known_files -- must run first

    if previous_version is not None:
        self._notify_docs_upgraded(temp_dir, previous_version)

    return temp_dir

def _notify_docs_upgraded(self, temp_dir: Path, previous_version: int) -> None:
    note_path = temp_dir / str(uuid.uuid4())
    note_path.write_text(
        "Scratch Desk's tempui conventions changed\n"
        f"This project's tempui docs were just refreshed from version "
        f"{previous_version} to {TEMPUI_DOC_VERSION}. See "
        "tempui-breaking-changes.md for what changed in between -- some "
        "of it may affect widgets already built in this project.\n"
    )
    self._known_files.add(note_path.name)
    self._relay.added.emit(note_path)
```

Ordering matters: `_start_watching` must run *before* this, since it
clears `self._known_files` — calling `_notify_docs_upgraded` after
ensures the note's filename isn't wiped back out.

## Verification

Extend `tests/verify/verify_qt_watchers.py` (already the home for a
real `TempUiManager.provision` test) or a new dedicated script:

- A real, pre-existing `.desk_temp` whose `desk-temporary-ui.md` embeds
  an old version number — `provision()` rewrites it (confirm the file
  content actually changed to the current version) **and** emits
  `file_added` for a real new Scratch-shaped file under `temp_dir`,
  whose content mentions both the old and new version numbers and
  points at `tempui-breaking-changes.md`. A real `DeskWindow` (or the
  same fake-window-with-real-`_place_widget` shape other tests here
  already use) receiving that `file_added` signal actually places a
  Scratch widget — not just "the signal fired," the real downstream
  effect too.
- A brand-new `.desk_temp` (no prior `desk-temporary-ui.md` at all) —
  no notification (there's nothing to have "missed").
- An already-current doc set (version already matches) whose only
  problem is a missing split file — still gets repaired
  (`write_tempui_docs` still runs), but **no** notification (nothing
  about the *convention* changed, just a repair).
- `ensure_docs_current`'s own new return value, tested directly against
  the three cases above (stale-with-a-real-old-version,
  current-but-missing-a-split-file, brand-new/no-doc-at-all).
- Full `tests/verify/` regression suite.
