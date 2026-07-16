# Plan: TODO a96c091 (COMPLETED) — investigate `disabled_verify_crash_handler.py`

## Investigation

Confirmed directly against `src/desk/crash_handler.py`'s current
`_log_path()`: it writes to `directory / TEMP_UI_DIRNAME /
"DESK-CRASH-<timestamp>.log"` (TODO `7f51230` relocated it under
`.desk_temp/`), not `directory` directly. `test_writes_log_in_current_
desk_dir`/`test_falls_back_to_cwd` both glob `directory.glob("DESK
-CRASH-*.log")` — the pre-relocation path — so they correctly build
zero real crash logs there anymore.

## Resolution

Fix: both globs become `(directory / ".desk_temp").glob("DESK-CRASH-*.
log")`. Nothing else in this script needs to change — `install()`
idempotence, previous-hook-chaining, and survives-log-write-failure
coverage are all unaffected by where the log itself lands.

## Verification

Re-run the script standalone (passes); full `tests/verify/` suite:
disabled count drops to 13, 0 new failures.
