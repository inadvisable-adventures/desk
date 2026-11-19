"""The shared web component libraries (TODO d34f8ed) as data: the catalog of
what's available, which widgets use what, and vendoring -- copying the
desk-wide components a widget depends on into the project's own library
(TODO b04682e) so a project carries everything its widgets need rather than
relying on whichever Desk happens to open it. Used by the Components widget
(widgets/components/, TODO 5ee7493) and the `desk_vendor_widget_components`
MCP tool; the build side lives in desk.custom_widgets."""
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from desk.custom_widgets import (
    PROJECT_COMPONENTS_RELPATH,
    SourceBuildError,
    read_component_names,
    resolve_components,
)
from desk.temp_ui import (
    CUSTOM_WIDGET_SRC_DIRNAME,
    PROMOTED_WIDGET_SRC_DIRNAME,
    TEMP_UI_DIRNAME,
    _repo_shared_components_dir,
)

_IGNORED = shutil.ignore_patterns("__pycache__", ".DS_Store")


@dataclass
class CatalogEntry:
    name: str
    scope: str  # "desk" | "project"
    directory: Path
    summary: str  # first prose paragraph of the README ("" if none)
    readme: Path | None
    has_template: bool
    files: list[str]  # relative paths, sorted
    used_by: list[str] = field(default_factory=list)  # source widget paths (relative to the project)
    vendored: bool = False  # desk-wide entry only: the project library holds a copy

    @property
    def ts_path(self) -> Path:
        return self.directory / f"{self.name}.ts"


def source_widget_dirs(project_dir: Path) -> list[Path]:
    """Every real-source widget directory in the project (a `widget.json`
    inside): promoted `desk_widgets/<name>/` and not-yet-promoted
    `.desk_temp/widgets/<name>/`."""
    found: list[Path] = []
    for base in (project_dir / PROMOTED_WIDGET_SRC_DIRNAME, project_dir / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME):
        if base.is_dir():
            found.extend(
                p for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith("_") and (p / "widget.json").is_file()
            )
    return found


def _summary(readme: Path | None) -> str:
    if readme is None:
        return ""
    paragraph: list[str] = []
    for line in readme.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not paragraph:
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def _entries_in(library: Path, scope: str) -> list[CatalogEntry]:
    entries = []
    if not library.is_dir():
        return entries
    for directory in sorted(library.iterdir()):
        if not (directory / f"{directory.name}.ts").is_file():
            continue
        readme = directory / "README.md"
        readme = readme if readme.is_file() else None
        entries.append(
            CatalogEntry(
                name=directory.name,
                scope=scope,
                directory=directory,
                summary=_summary(readme),
                readme=readme,
                has_template=(directory / "template.html").is_file(),
                files=sorted(
                    p.relative_to(directory).as_posix()
                    for p in directory.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store"
                ),
            )
        )
    return entries


def list_catalog(project_dir: Path, desk_library_dir: Path | None = None) -> list[CatalogEntry]:
    """Both libraries: the project's first, then Desk's. `used_by` lists the
    source widgets whose `widget.json` resolves to that exact entry;
    `vendored` marks a desk-wide entry the project library has a copy of."""
    desk_library = desk_library_dir if desk_library_dir is not None else _repo_shared_components_dir()
    project = _entries_in(project_dir / PROJECT_COMPONENTS_RELPATH, "project")
    desk = _entries_in(desk_library, "desk")
    by_key = {(e.scope, e.name): e for e in project + desk}
    project_names = {e.name for e in project}
    for entry in desk:
        entry.vendored = entry.name in project_names
    for widget_dir in source_widget_dirs(project_dir):
        try:
            resolved = resolve_components(read_component_names(widget_dir), project_dir, desk_library)
        except SourceBuildError:
            continue
        for component in resolved:
            entry = by_key.get((component.scope, component.name))
            if entry is not None:
                entry.used_by.append(widget_dir.relative_to(project_dir).as_posix())
    return project + desk


def catalog_signature(project_dir: Path, desk_library_dir: Path | None = None) -> tuple:
    """Cheap change detector for the catalog (file lists + mtimes of both
    libraries and every source widget.json) -- the Components widget polls it."""
    desk_library = desk_library_dir if desk_library_dir is not None else _repo_shared_components_dir()
    parts = []
    for root in (project_dir / PROJECT_COMPONENTS_RELPATH, desk_library):
        if root.is_dir():
            parts.extend((str(p), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file())
    parts.extend(
        (str(w / "widget.json"), (w / "widget.json").stat().st_mtime_ns) for w in source_widget_dirs(project_dir)
    )
    return tuple(parts)


def _same_tree(a: Path, b: Path) -> bool:
    files = lambda root: sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)  # noqa: E731
    left, right = files(a), files(b)
    return left == right and all((a / f).read_bytes() == (b / f).read_bytes() for f in left)


def vendor_component(
    project_dir: Path, name: str, desk_library_dir: Path | None = None, overwrite: bool = False
) -> tuple[Path, str]:
    """Copies the desk-wide component `name` into the project library.
    Returns (destination, "copied" | "unchanged"). An existing project copy
    that differs is never replaced silently: SourceBuildError unless
    `overwrite`."""
    desk_library = desk_library_dir if desk_library_dir is not None else _repo_shared_components_dir()
    source = desk_library / name
    if not (source / f"{name}.ts").is_file():
        raise SourceBuildError(f"no desk-wide component {name!r} in {desk_library}")
    destination = project_dir / PROJECT_COMPONENTS_RELPATH / name
    if destination.exists():
        if _same_tree(source, destination):
            return destination, "unchanged"
        if not overwrite:
            raise SourceBuildError(
                f"{destination} already exists and differs from Desk's {name!r}; it was probably "
                f"customized -- pass overwrite to replace it"
            )
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=_IGNORED)
    return destination, "copied"


@dataclass
class VendorResult:
    copied: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    pinned: list[str] = field(default_factory=list)  # widget.json entries rewritten to `project:<name>`

    def describe(self) -> str:
        if not (self.copied or self.unchanged or self.pinned):
            return "nothing to vendor: the widget uses no desk-wide components"
        parts = []
        if self.copied:
            parts.append(f"copied into the project library: {', '.join(self.copied)}")
        if self.unchanged:
            parts.append(f"already present, identical: {', '.join(self.unchanged)}")
        if self.pinned:
            parts.append(f"widget.json now pins: {', '.join('project:' + n for n in self.pinned)}")
        return "; ".join(parts)


def vendor_widget_components(
    project_dir: Path, source_path: str, desk_library_dir: Path | None = None, overwrite: bool = False
) -> VendorResult:
    """TODO b04682e: makes a source widget self-contained in the project --
    every desk-wide component its `widget.json` resolves to is copied into
    the project library and its entry rewritten to `project:<name>`, so the
    build reads only project files (it fails loudly, not silently falling
    back to the opening Desk's copy, if one goes missing). A component
    already resolved from the project library is left as is. `source_path`
    is relative to the project, e.g. `desk_widgets/my-widget`."""
    widget_dir = project_dir / source_path
    manifest_path = widget_dir / "widget.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as e:
        raise SourceBuildError(f"cannot read {manifest_path}: {e}") from e
    names = read_component_names(widget_dir)
    resolved = resolve_components(names, project_dir, desk_library_dir)
    result = VendorResult()
    rewritten: list[str] = []
    done: set[str] = set()
    by_name = {c.name: c for c in resolved}
    for raw in names:
        _, _, name = raw.rpartition(":")
        component = by_name.get(name)
        if component is None or component.scope != "desk" or raw.startswith("project:"):
            rewritten.append(raw)
            continue
        if name not in done:
            _, outcome = vendor_component(project_dir, name, desk_library_dir, overwrite)
            (result.copied if outcome == "copied" else result.unchanged).append(name)
            result.pinned.append(name)
            done.add(name)
        rewritten.append(f"project:{name}")
    if result.pinned:
        manifest["components"] = rewritten
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return result
