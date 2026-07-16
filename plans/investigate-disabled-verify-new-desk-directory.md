# Plan: TODO 6e9def4 (COMPLETED) — investigate `disabled_verify_new_desk_directory.py`

## Investigation

Confirmed fixture drift: the fake `switch_desk(self, path, confirm=None)`
predates the real `DeskWindow.switch_desk` gaining a `provisioning`
parameter. Nothing in this script's own assertions inspects
`provisioning`'s content — it just needs to be accepted and ignored.

## Resolution

Add `provisioning=None` to the fake's `switch_desk` signature.

## Verification

Re-run standalone (passes); full `tests/verify/` suite: disabled count
drops to 7, 0 new failures.
