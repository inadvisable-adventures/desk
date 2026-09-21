"""Promotion and a widget's `tsconfig.json` shared dependencies (TODO
8a09220).

A widget authored "from real source" (see tempui-custom-widgets.md) may
list files outside its own directory in `tsconfig.json`'s top-level
`"files"` array -- a shared base class, a shared DSL module,
`shared-components/...`. Promotion moves the widget's directory from
`.desk_temp/widgets/<name>/` to `desk_widgets/<name>/`, which silently
breaks those relative paths. This module holds the pure filesystem side
of fixing that -- planning, applying, and finding un-promoted peers that
reference a moved file -- with no Qt, so it is testable against real
temp trees. `DeskWindow._relocate_promoted_widget_source` drives it and
owns everything user-facing.

Paths are resolved lexically (`os.path.normpath`), never through
symlinks, and every path handled here is absolute."""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from desk.custom_widgets import SourceBuildError, _read_files_entries, _read_tsconfig
from desk.temp_ui import CUSTOM_WIDGET_SRC_DIRNAME, PROMOTED_WIDGET_SRC_DIRNAME, TEMP_UI_DIRNAME


@dataclass
class DependencyPlan:
    """What promoting one widget needs done about its external files.
    `moves` maps a file's current path to where it is moving; `rewrites`
    maps each tsconfig entry (as written) to its replacement, relative
    to the widget's *new* directory. `notes` are user-facing lines for
    anything that could not be fully handled."""

    moves: dict[Path, Path] = field(default_factory=dict)
    rewrites: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class PeerDependent:
    """An un-promoted widget directory whose tsconfig.json references a
    file that has just been moved. `rewrites` is entry -> replacement,
    relative to the peer's own (unmoved) directory."""

    directory: Path
    rewrites: dict[str, str]


def _norm(path: Path | str) -> Path:
    return Path(os.path.normpath(path))


def _is_within(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


def _relative_posix(target: Path, start: Path) -> str:
    return Path(os.path.relpath(target, start)).as_posix()


def _temp_widgets_dir(project_dir: Path) -> Path:
    return project_dir / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME


def _files_entries(widget_dir: Path) -> list[str]:
    """Best-effort: a missing or malformed tsconfig.json means "nothing
    to do here", never an error -- promotion itself must not fail over
    this secondary bookkeeping."""
    try:
        return _read_files_entries(_read_tsconfig(widget_dir))
    except SourceBuildError:
        return []


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _final_location(project_dir: Path, resolved: Path) -> tuple[Path, str | None]:
    """Where `resolved` should live once promotion is done, plus a
    user-facing note when it belongs to something else and is left
    alone."""
    temp_widgets = _temp_widgets_dir(project_dir)
    if not _is_within(resolved, temp_widgets) or resolved == temp_widgets:
        return resolved, None
    relative = resolved.relative_to(temp_widgets)
    if len(relative.parts) >= 2 and (temp_widgets / relative.parts[0] / "widget.json").is_file():
        return resolved, (
            f"{resolved} belongs to another widget's own directory ({relative.parts[0]}) -- "
            "left where it is; that widget's promotion will need to be handled separately."
        )
    return project_dir / PROMOTED_WIDGET_SRC_DIRNAME / relative, None


def plan_dependency_relocation(project_dir: Path, old_widget_dir: Path, new_widget_dir: Path) -> DependencyPlan:
    """Called *before* the widget's directory moves: `"files"` entries
    are relative to `old_widget_dir`, which still exists at this point.
    Nothing on disk is changed here."""
    plan = DependencyPlan()
    old_widget_dir = _norm(old_widget_dir)
    for entry in _files_entries(old_widget_dir):
        resolved = _norm(old_widget_dir / entry)
        if _is_within(resolved, old_widget_dir):
            continue
        final, note = _final_location(project_dir, resolved)
        if note:
            plan.notes.append(note)
        if final != resolved and resolved not in plan.moves:
            if resolved.exists() and not final.exists():
                plan.moves[resolved] = final
            elif resolved.exists() and final.exists():
                if _same_bytes(resolved, final):
                    plan.notes.append(
                        f"{final} already exists with identical contents -- {resolved} was left in place "
                        "(un-promoted widgets may still use it)."
                    )
                else:
                    plan.notes.append(
                        f"{final} already exists and differs from {resolved} -- nothing was moved, and this "
                        "widget still points at the original. Reconcile the two by hand."
                    )
                    final = resolved
            elif not final.exists():
                plan.notes.append(f"{entry} does not exist (looked for {resolved}) -- its path was left alone.")
                continue
            # else: only the final location exists -- an earlier promotion already moved it.
        rewritten = _relative_posix(final, new_widget_dir)
        if rewritten != entry:
            plan.rewrites[entry] = rewritten
    return plan


def apply_moves(plan: DependencyPlan) -> None:
    for source, destination in plan.moves.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))


def rewrite_files_entries(widget_dir: Path, rewrites: dict[str, str]) -> bool:
    """Rewrites `"files"` entries in `widget_dir/tsconfig.json`. Prefers
    exact-string replacement so the author's own formatting survives;
    if the result doesn't parse to the expected list, falls back to
    re-dumping the JSON. Returns whether the file was changed."""
    if not rewrites:
        return False
    tsconfig_path = widget_dir / "tsconfig.json"
    try:
        text = tsconfig_path.read_text()
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return False
    old_files = data.get("files")
    if not isinstance(old_files, list):
        return False
    expected = [rewrites.get(entry, entry) if isinstance(entry, str) else entry for entry in old_files]
    if expected == old_files:
        return False
    replaced = text
    for old, new in rewrites.items():
        replaced = replaced.replace(json.dumps(old), json.dumps(new))
    try:
        ok = json.loads(replaced).get("files") == expected
    except json.JSONDecodeError:
        ok = False
    if not ok:
        data["files"] = expected
        replaced = json.dumps(data, indent=2) + "\n"
    tsconfig_path.write_text(replaced)
    return True


def find_peer_dependents(
    project_dir: Path, moved: dict[Path, Path], exclude: set[Path] | None = None
) -> list[PeerDependent]:
    """Other directories under `.desk_temp/widgets/` whose tsconfig.json
    still references a file that was just moved (`moved`: old path ->
    new path). Sorted by directory name for a stable prompt order."""
    temp_widgets = _temp_widgets_dir(project_dir)
    if not moved or not temp_widgets.is_dir():
        return []
    excluded = {_norm(path) for path in (exclude or set())}
    result: list[PeerDependent] = []
    for directory in sorted(temp_widgets.iterdir()):
        directory = _norm(directory)
        if not directory.is_dir() or directory in excluded:
            continue
        rewrites: dict[str, str] = {}
        for entry in _files_entries(directory):
            target = moved.get(_norm(directory / entry))
            if target is not None:
                rewrites[entry] = _relative_posix(target, directory)
        if rewrites:
            result.append(PeerDependent(directory=directory, rewrites=rewrites))
    return result
