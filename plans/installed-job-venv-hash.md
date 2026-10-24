# Installed Job hash skips the job's `.venv` (TODO `e5b5567`) (COMPLETED)

## Summary

`compute_version_hash` skips a job's own top-level `.venv/` (big, generated; hashing it timed out the install tools),
while `requirements.txt` and other files stay hashed so dependency bumps still force re-approval. The bridge timeout
change from the feedback is deliberately out of scope.

## Affected files

- `src/desk/installed_jobs.py`: `SELF_MANAGED_VENV_DIRNAME`, skip in `compute_version_hash` (docstring updated).
- `src/desk/temp_ui.py`: tag, changelog entry, "Self-managed venvs" section of `tempui-installed-jobs.md`.
- `LEARNINGS.md`; `tests/verify/verify_installed_job_venv_hash.py` (new).

## Decisions

- Only the exact top-level name `.venv` (the convention the feedback cites); a nested `.venv` or a `venv/` is still hashed.
- The hmsvc `venv` setting names a service's project-relative venv and is not part of a job's directory hash.
- One-time re-approval for existing venv-bearing jobs is called out in the changelog.

## Status

Headless-verified; no live install against a real large venv.
