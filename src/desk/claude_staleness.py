"""Staleness tracking for the Claude (Desk) widget (TODO 5ce8447).

Pure state machine: every method takes `now` explicitly (seconds, any
monotonic origin), no timers, no Qt -- the widget ticks it. See
plans/claude-desk-staleness-and-probe.md.

"Outstanding" means the user is plausibly waiting on a reply: a solicited
turn is pending, an unsolicited turn is open, a delegated-agent background
task is in flight, or we are inside the grace window after the last such
task finished. While outstanding, silence (no session_event) is measured;
past STALE_AFTER it is "stale", past PROBE_AFTER the widget should also
probe network reachability.
"""

STALE_AFTER = 15.0
PROBE_AFTER = 45.0
PROBE_INTERVAL = 5.0
GRACE_SECONDS = 30.0

# MIRRORS AN INTERNAL, UNEXPORTED IMPLEMENTATION DETAIL of claude_agent_sdk
# -- `DEFERRING_TASK_TYPES` in claude_agent_sdk/_internal/query.py, which
# the SDK uses to decide whose completion wakes the parent agent for a
# follow-up turn (delegated agent work), as opposed to a plain background
# shell, which may never do so (or never even reach a terminal status).
# It is not a documented contract: a future CLI/SDK version can add,
# rename or remove task types and this copy will silently stop matching
# reality. Used only as a heuristic for *hedged* status text, never for
# control flow. See investigations/claude-agent-sdk-upstream-requests.md.
DEFERRING_TASK_TYPES = frozenset({"local_agent", "local_workflow"})

TERMINAL_STATUSES = ("completed", "failed", "killed", "stopped", "cancelled")


class StalenessTracker:
    def __init__(self) -> None:
        self._last_event: float | None = None
        self._turn_open = False  # a solicited turn is pending
        self._unsolicited_open = False
        self._tasks: dict[str, dict] = {}  # task_id -> {"status", "task_type"}
        self._grace_until: float | None = None
        # TODO f8da2c5: a pending permission/AskUserQuestion panel -- the
        # silence is the user's, not a stall.
        self._waiting_on_user = False

    # -- inputs -----------------------------------------------------------------

    def set_waiting_on_user(self, waiting: bool, now: float) -> None:
        """TODO f8da2c5: while Claude is blocked on a human (permission
        request / question), nothing is outstanding from the network's or
        model's side, so no stale clock runs. When the human answers, the
        clock restarts from `now` -- the wait itself must not count as
        silence."""
        if self._waiting_on_user and not waiting:
            self._last_event = now
        self._waiting_on_user = waiting

    def feed(self, event: dict, now: float) -> None:
        """Consumes one ClaudeSession.session_event dict."""
        kind = event["kind"]
        solicited = event.get("solicited", True)
        self._last_event = now
        if kind == "turn_started":
            self._turn_open = True
        elif kind == "unsolicited_turn_started":
            self._unsolicited_open = True
        elif kind == "turn_complete":
            if solicited:
                self._turn_open = False
            else:
                self._unsolicited_open = False
        elif kind == "session_error":
            self._turn_open = False
            self._unsolicited_open = False
        elif kind == "task_event":
            data = event.get("data", {})
            self._task_event(data.get("task_id", ""), data.get("patch", {}), now)

    def _task_event(self, task_id: str, patch: dict, now: float) -> None:
        task = self._tasks.setdefault(task_id, {"status": "running", "task_type": None})
        was_deferring_inflight = self._deferring_inflight()
        for key in ("status", "task_type"):
            if patch.get(key) is not None:
                task[key] = patch[key]
        if was_deferring_inflight and not self._deferring_inflight():
            # The last delegated-agent task just settled; it may still
            # wake the agent for a follow-up turn.
            self._grace_until = now + GRACE_SECONDS

    def _deferring_inflight(self) -> bool:
        return any(
            task["task_type"] in DEFERRING_TASK_TYPES and task["status"] not in TERMINAL_STATUSES
            for task in self._tasks.values()
        )

    # -- queries ----------------------------------------------------------------

    def in_grace(self, now: float) -> bool:
        return (
            self._grace_until is not None
            and now < self._grace_until
            and not (self._turn_open or self._unsolicited_open or self._deferring_inflight())
        )

    def outstanding(self, now: float) -> bool:
        if self._waiting_on_user:
            return False
        return self._turn_open or self._unsolicited_open or self._deferring_inflight() or self.in_grace(now)

    def silent_seconds(self, now: float) -> float | None:
        if not self.outstanding(now) or self._last_event is None:
            return None
        return max(0.0, now - self._last_event)

    def level(self, now: float) -> int:
        """0 = fine/idle, 1 = stale, 2 = stale long enough to probe."""
        silent = self.silent_seconds(now)
        if silent is None or silent < STALE_AFTER:
            return 0
        return 2 if silent >= PROBE_AFTER else 1

    def describe(self, now: float, network_ok: bool | None) -> str:
        """Hedged, plain-language status note ("" when nothing to say).
        `network_ok`: None = not probed (yet), else the latest probe."""
        silent = self.silent_seconds(now)
        if self.level(now) == 0 or silent is None:
            return ""
        text = f"no response for {int(silent)}s"
        if self.in_grace(now):
            # A guess, not a promise.
            text = f"probably wrapping up a background task, no response for {int(silent)}s"
        if self.level(now) < 2:
            return text  # a probe verdict only means anything once we're probing
        if network_ok is False:
            text += " -- your network looks down"
        elif network_ok is True:
            text += " -- network's fine, something else is stuck"
        return text
