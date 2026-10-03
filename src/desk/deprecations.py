"""Deprecations by tombstone (TODO df8138a). See design-docs/deprecation-process.md.

When a widget-facing API is replaced, Desk keeps the old name -- but with nothing
behind it except (1) a report to Desk that the old API was used and (2) an error
that says what to use now and carries a short command to hand to an agent. There
is no grace period and no old behavior to maintain.

This module is the registry: one `Deprecation` per replaced API (id `DEPR-NNN`,
which surface it lives on, the old name, the replacement, the message), plus the
mechanics shared by every surface -- reporting (deduplicated per instance and
API), the error type, and a helper that builds a python tombstone. Each surface
wires itself to this:

- Bridge JS: `desk.server.bridge_client` installs stubs from the registry.
- python hooks: use `tombstone(dep_id)` as the old function.
- tempui keywords: `desk.temp_ui.detect_temp_ui_kind` returns `deprecated:<id>`.
- manifest fields: `check_manifest(...)` in `desk.widgets`.
- wire paths: the Bridge server's identity dependency (DEPR-001).

`detector` and `rewriter` are carried here for the scan and rewrite follow-ups
(see the process doc); nothing in this slice runs them.

Messages never need, and never point at, the documentation of the old API: that
lives only in the isolated history store (deep-dive investigations only; see the
guard line in CLAUDE.md), which no runtime message may mention.
"""
import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

SURFACES = ("bridge_js", "python_hook", "tempui_keyword", "manifest_field", "wire_path")


@dataclass(frozen=True)
class Detector:
    """What to look for in source (for the scan follow-up): `pattern` is a
    regex source, matched in files whose kind is in `kinds`."""

    kinds: tuple[str, ...]
    pattern: str


@dataclass(frozen=True)
class Deprecation:
    id: str
    surface: str
    old: str
    replacement: str
    message: str
    since: str
    detector: Detector | None = None
    # text -> rewritten text, or None if it can't be rewritten mechanically
    # (for the rewrite follow-up).
    rewriter: Callable[[str], str | None] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.surface not in SURFACES:
            raise ValueError(f"unknown deprecation surface {self.surface!r}; expected one of {SURFACES}")


@dataclass(frozen=True)
class UsageReport:
    deprecation: Deprecation
    widget_id: str
    instance_id: str
    detail: str | None
    first_seen: float


def agent_command(dep: Deprecation, where: str | None = None) -> str:
    """The short command a person can paste into an agent console."""
    target = f" in {where}" if where else ""
    return f"Fix deprecated Desk API use {dep.id}: replace {dep.old} with {dep.replacement}{target}."


def format_error(dep: Deprecation, where: str | None = None) -> str:
    """The message every tombstone carries: what changed, what to use now, and
    the command to give an agent. Complete on its own -- no old docs needed."""
    return f"{dep.old} was replaced by {dep.replacement}. {dep.message} [{dep.id}] To have an agent fix it, paste: {agent_command(dep, where)}"


class DeprecatedApiError(Exception):
    def __init__(self, deprecation: Deprecation, where: str | None = None) -> None:
        super().__init__(format_error(deprecation, where))
        self.deprecation = deprecation


class DeprecatedManifestError(DeprecatedApiError, ValueError):
    """A manifest using a deprecated field. Also a ValueError so loaders that
    already skip-and-log a bad manifest (project widgets, hmsvc services) treat
    it the same way, with the tombstone message as the reason."""


class DeprecationRegistry:
    """Qt-free and thread-safe (reports arrive on the Bridge server's thread as
    well as the GUI thread)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._deprecations: dict[str, Deprecation] = {}
        self._reports: dict[tuple[str, str], UsageReport] = {}
        self._listeners: list[Callable[[UsageReport], None]] = []

    def register(self, dep: Deprecation) -> Deprecation:
        with self._lock:
            existing = self._deprecations.get(dep.id)
            if existing is not None and existing != dep:
                raise ValueError(f"{dep.id} is already registered with different content")
            self._deprecations[dep.id] = dep
        return dep

    def unregister(self, dep_id: str) -> None:
        """For tests that register synthetic deprecations."""
        with self._lock:
            self._deprecations.pop(dep_id, None)
            for key in [k for k in self._reports if k[0] == dep_id]:
                del self._reports[key]

    def get(self, dep_id: str) -> Deprecation | None:
        with self._lock:
            return self._deprecations.get(dep_id)

    def all(self) -> list[Deprecation]:
        with self._lock:
            return sorted(self._deprecations.values(), key=lambda d: d.id)

    def by_surface(self, surface: str) -> list[Deprecation]:
        return [d for d in self.all() if d.surface == surface]

    def tempui_keyword(self, keyword: str) -> Deprecation | None:
        return next((d for d in self.by_surface("tempui_keyword") if d.old == keyword), None)

    def add_listener(self, listener: Callable[[UsageReport], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def report(self, dep_id: str, widget_id: str, instance_id: str, detail: str | None = None) -> UsageReport | None:
        """Records that `instance_id` used the deprecated API; returns the
        report, or None if this instance already reported this deprecation
        (reporting is once per instance and API). Listeners run outside the lock."""
        with self._lock:
            dep = self._deprecations.get(dep_id)
            if dep is None:
                raise KeyError(f"unknown deprecation {dep_id!r}")
            key = (dep_id, instance_id)
            if key in self._reports:
                return None
            report = UsageReport(dep, widget_id, instance_id, detail, time.time())
            self._reports[key] = report
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(report)
            except Exception:  # noqa: BLE001 -- a broken listener must not break the tombstone
                import logging

                logging.getLogger("desk.deprecations").exception("deprecation listener failed")
        return report

    def reports(self) -> list[UsageReport]:
        with self._lock:
            return sorted(self._reports.values(), key=lambda r: r.first_seen)

    def forget_instance(self, instance_id: str) -> None:
        """A removed instance's reports are dropped (a re-placed one reports again)."""
        with self._lock:
            for key in [k for k in self._reports if k[1] == instance_id]:
                del self._reports[key]


_registry = DeprecationRegistry()


def get_registry() -> DeprecationRegistry:
    return _registry


def tombstone(dep_id: str, registry: DeprecationRegistry | None = None) -> Callable[..., object]:
    """A python tombstone: call it (it is the old function) and it reports the
    caller's location to Desk, then raises `DeprecatedApiError`. Accepts and
    ignores any arguments, so the old signature needn't be kept."""
    reg = registry or _registry

    def _tombstone(*args: object, **kwargs: object) -> object:
        dep = reg.get(dep_id)
        if dep is None:
            raise KeyError(f"unknown deprecation {dep_id!r}")
        frame = inspect.stack()[1]
        where = f"{frame.filename}:{frame.lineno}"
        reg.report(dep_id, "python", where, detail=where)
        raise DeprecatedApiError(dep, where)

    _tombstone.__name__ = f"tombstone_{dep_id}"
    return _tombstone


def check_manifest(manifest: dict, origin: str, registry: DeprecationRegistry | None = None) -> None:
    """For a manifest-field deprecation: if `manifest` (a parsed `widget.json` /
    `service.json`) uses a deprecated field, report it and fail the load with
    the tombstone error. `origin` is where it came from (a path)."""
    reg = registry or _registry
    for dep in reg.by_surface("manifest_field"):
        if dep.old in manifest:
            reg.report(dep.id, "manifest", origin, detail=f"{origin}: {dep.old}")
            raise DeprecatedManifestError(dep, origin)


DEPR_001 = _registry.register(
    Deprecation(
        id="DEPR-001",
        surface="wire_path",
        old="the shared launch token as Bridge caller identity (identity asserted in X-Desk-Widget-Id / X-Desk-Instance-Id headers)",
        replacement="a per-instance Bridge credential",
        message=(
            "Caller identity now comes only from the credential Desk issues to each widget instance or service; "
            "a request that presents the shared launch token and asserts its own identity is refused."
        ),
        since="2026-10-03",
    )
)
