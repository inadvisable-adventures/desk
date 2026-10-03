# Claude (Desk) widget: staleness, task grace window, connectivity probe (TODO `5ce8447`) (COMPLETED)

## Summary
A silent stall (e.g. a network outage) currently looks identical to "working".
Track silence while something is outstanding, say so, hedge honestly about
background-task wake-ups, and -- only once stale for longer -- probe whether
the network is reachable.

## Affected files
- `src/desk/claude_staleness.py` (new): pure `StalenessTracker` (all times
  passed in, no timers) + the hedged status text.
- `src/desk/connectivity_probe.py` (new): stdlib-only TCP reachability probe.
- `src/desk/claude_session.py`: forward `task_type` in the task_event patch.
- `src/desk/claude_flow_view.py`: amber "stale" state on the Session node.
- `widgets/claude_desk/widget.py`: 1 s tick, stale label, probe lifecycle.
- `investigations/claude-agent-sdk-upstream-requests.md` (new): drafted
  upstream asks (nothing is sent anywhere).
- `tests/verify/verify_claude_desk_staleness.py` (new), `TODO.md`.

## Decisions
- **Thresholds** (constants, one place): stale after 15 s of silence while
  outstanding; probe after 45 s; probe re-run every 5 s while still stale;
  task grace window 30 s.
- **Outstanding** = a solicited turn pending, an unsolicited turn open, a
  *deferring* background task in flight, or inside the grace window.
  Deviation from the TODO text, which says "any non-terminal task": a plain
  backgrounded shell (dev server, `tail -f`) may never reach a terminal
  status, so counting it would show a permanent false "no response for 3h".
  Only delegated-agent task types (`local_agent`, `local_workflow`, copied
  from the SDK's own unexported `DEFERRING_TASK_TYPES` in
  `_internal/query.py`, with a comment saying it mirrors an internal detail
  that may silently drift) count.
- **Grace window**: when the last deferring task goes terminal and no turn is
  pending, stay "outstanding" for 30 s -- a settled task can still wake the
  agent. The user-facing text hedges ("probably wrapping up a background
  task") and never promises a reply; no SDK jargon in the UI.
- **Clock** resets on every `session_event` (they all prove the stream is
  alive), including `rate_limit` and `token_usage`.
- **Presentation**: a dedicated amber `_stale_label` in the top row rather
  than suffixing the status label, which is rewritten from many places
  (token counts, interrupt, errors) and would fight a suffix. Flow view's
  Session node gets an amber border and the note as its annotation.
- **Probe**: a bare unauthenticated TCP connect to `api.anthropic.com:443`
  (no request body, no credentials), started only once stale past the probe
  threshold, repeated every 5 s, stopped when the stall resolves. Runs on a
  short-lived thread; the check function is injectable for tests. Text:
  "network looks down" vs "network's fine, something else is stuck".
  Caveat (documented in the module): success from Desk's process doesn't
  prove the CLI subprocess's network path matches (proxy/VPN scoping) --
  a strong signal, not a proof. ToS: a plain TCP handshake to the public API
  hostname, occasional and stall-triggered, sends no data.
- Upstream asks drafted: a run-boundary signal from the CLI, and a public
  task-type classification.

## Verification
Tracker driven with explicit times (stale/probe levels, task and grace
handling, shell tasks ignored, unsolicited turns, clock reset); probe with an
injected checker; widget and flow integration. No live network/API.
