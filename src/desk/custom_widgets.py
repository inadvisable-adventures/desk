"""Materializes a tempui-DSL-defined custom widget's (TODO 91b3f42,
desk.temp_ui.CustomWidgetDefinition) base64-encoded HTML onto disk, so
it can be served exactly like any other `kind: "html"` widget (see
desk.server.runner.ServerHandle.mount_html_widget /
desk.shell.chromium_widget.ChromiumWidget). This is a disposable cache,
not a source of truth -- the actual source is whichever `DefineWidget`
tempui file or `.desk` file entry the definition came from, and this
gets regenerated fresh every time a definition is (re-)registered."""

import base64
import binascii
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from desk.temp_ui import (
    CUSTOM_WIDGET_SRC_DIRNAME,
    PROMOTED_WIDGET_SRC_DIRNAME,
    SOURCE_BUILD_CACHE_DIRNAME,
    TEMP_UI_DIRNAME,
    CustomWidgetDefinition,
    _repo_shared_components_dir,
)

logger = logging.getLogger(__name__)

CUSTOM_WIDGETS_CACHE_DIRNAME = "custom_widgets"

# SOURCE_BUILD_CACHE_DIRNAME (TODO 13f4ad5, where build_from_source
# below writes a source-backed widget's rebuilt-on-demand HTML --
# gitignored, inside the widget's own durable source directory rather
# than a shared cache, so it moves for free whenever the source
# directory itself does, e.g. on promotion) is defined in desk.temp_ui,
# not here -- see that module's own comment (TODO 1c67fe5) for why.

_BUILD_MARKER = "/* BUILD:COMPILED_JS */"

# TODO d34f8ed: shared web components. A widget lists component names in its
# widget.json "components"; the build compiles each component's <name>.ts
# ahead of the widget's own files and injects its template.html at the top of
# the page. Two libraries: the desk-wide one (this Desk's own shared-components/,
# static -- changes only with Desk's source) and a per-project one (mutable,
# authored in the project). The generated .desk_temp/build_widget.py carries
# an independent copy of this logic (it must be self-contained); keep them in
# step -- verify_widget_components.py runs both and compares the HTML.
PROJECT_COMPONENTS_RELPATH = "desk_widgets/_shared/components"
_COMPONENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_TEMPLATE_ID_RE = re.compile(r"<template\b[^>]*?\bid\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_TEMPLATES_MARKER = "<!-- BUILD:COMPONENT_TEMPLATES -->"
_COMPONENTS_BUILD_CONFIG = "tsconfig.components.json"


@dataclass
class Component:
    name: str
    scope: str  # "desk" (Desk's own shared-components/) or "project"
    directory: Path

    @property
    def ts(self) -> Path:
        return self.directory / f"{self.name}.ts"

    @property
    def template(self) -> Path | None:
        path = self.directory / "template.html"
        return path if path.is_file() else None


class SourceBuildError(Exception):
    """Any problem that should abort a source-backed widget's build --
    caught only in build_from_source, which logs and returns None
    instead, so one bad/stale source directory can't take the whole
    app down. Mirrors .desk_temp/build_widget.py's own BuildError --
    deliberately not the same class, since that script is a separate,
    self-contained generated file with no dependency on this package."""


def materialized_widget_dir(desk_temp_dir: Path, keyword: str) -> Path:
    return desk_temp_dir / CUSTOM_WIDGETS_CACHE_DIRNAME / keyword


def materialize(desk_temp_dir: Path, definition: CustomWidgetDefinition) -> Path | None:
    """Decodes `definition.html_b64` to a real index.html at
    materialized_widget_dir(desk_temp_dir, definition.keyword),
    creating directories as needed, and returns that directory. Returns
    None (logged, not raised) if the base64/UTF-8 content is malformed
    -- one bad definition shouldn't take down the whole app."""
    target_dir = materialized_widget_dir(desk_temp_dir, definition.keyword)
    try:
        html = base64.b64decode(definition.html_b64.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        logger.error(
            "Failed to decode custom widget %r's html_b64 -- malformed base64/UTF-8",
            definition.keyword,
            exc_info=True,
        )
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "index.html").write_text(html)
    return target_dir


def read_component_names(widget_dir: Path) -> list[str]:
    """The `"components"` list in a source widget's widget.json, as written
    (empty if absent). Raises SourceBuildError if present but not a list of
    strings. See resolve_components."""
    manifest_path = widget_dir / "widget.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return []
    names = manifest.get("components", []) if isinstance(manifest, dict) else []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise SourceBuildError(f'{manifest_path}: "components" must be a list of component names')
    return names


def _library_component(directory: Path, name: str) -> Path | None:
    candidate = directory / name
    return candidate if (candidate / f"{name}.ts").is_file() else None


def resolve_components(
    names: list[str], project_dir: Path, desk_library_dir: Path | None = None
) -> list[Component]:
    """TODO d34f8ed: names -> Components, in declared order, duplicates dropped.
    A name is `desk:<name>` (Desk's shared-components/), `project:<name>`
    (<project>/desk_widgets/_shared/components/), or a bare `<name>`: the
    project library's copy if it has one, else the desk-wide one. So a
    project copy (e.g. one vendored from the desk-wide library, TODO
    b04682e) takes precedence over Desk's, and a component Desk adds later
    can never change what an existing project builds; `desk:`/`project:`
    pin a side. A component is a directory holding `<name>.ts` and,
    optionally, `template.html`."""
    if desk_library_dir is None:
        desk_library_dir = _repo_shared_components_dir()
    project_library = project_dir / PROJECT_COMPONENTS_RELPATH
    resolved: list[Component] = []
    for raw in names:
        scope, _, name = raw.rpartition(":")
        if scope not in ("", "desk", "project") or not _COMPONENT_NAME_RE.match(name):
            raise SourceBuildError(
                f"invalid component {raw!r}: use a lowercase-kebab name, optionally prefixed desk: or project:"
            )
        in_desk = _library_component(desk_library_dir, name) if scope in ("", "desk") else None
        in_project = _library_component(project_library, name) if scope in ("", "project") else None
        found = in_project or in_desk
        if found is None:
            raise SourceBuildError(
                f"component {raw!r} not found (looked for {name}/{name}.ts in {desk_library_dir}"
                f"{'' if scope == 'desk' else f' and {project_library}'})"
            )
        component = Component(name, "project" if found is in_project else "desk", found)
        if all((c.scope, c.name) != (component.scope, component.name) for c in resolved):
            resolved.append(component)
    return resolved


def _read_tsconfig(widget_dir: Path) -> dict:
    tsconfig_path = widget_dir / "tsconfig.json"
    if not tsconfig_path.is_file():
        raise SourceBuildError(f"{tsconfig_path} not found")
    try:
        return json.loads(tsconfig_path.read_text())
    except json.JSONDecodeError as e:
        raise SourceBuildError(f"{tsconfig_path} is not valid JSON: {e}") from e


def _read_out_dir(widget_dir: Path, tsconfig: dict) -> Path:
    out_dir = tsconfig.get("compilerOptions", {}).get("outDir")
    if not out_dir:
        raise SourceBuildError(f"{widget_dir / 'tsconfig.json'} must set compilerOptions.outDir")
    return widget_dir / out_dir


def _read_files_entries(tsconfig: dict) -> list[str]:
    """tsconfig.json's own top-level "files" array, as written (TODO
    8a09220: promotion needs the full relative paths, not just the
    stems _read_ordered_stems keeps). Empty if absent."""
    return list(tsconfig.get("files") or [])


def _read_ordered_stems(tsconfig: dict) -> list[str] | None:
    """Mirrors .desk_temp/build_widget.py's own _read_ordered_stems --
    see that file's docstring (TODO 3fc5331) for why this matters for a
    widget split across more than one .ts file."""
    files = _read_files_entries(tsconfig)
    if not files:
        return None
    return [Path(entry).stem for entry in files]


def components_out_dir(widget_dir: Path) -> Path:
    """Where a widget *with components* has its TypeScript compiled."""
    return widget_dir / SOURCE_BUILD_CACHE_DIRNAME / "js"


def _compile_typescript(widget_dir: Path, components: list[Component] | None = None) -> None:
    ts_source = widget_dir / f"{widget_dir.name}.ts"
    if not ts_source.is_file():
        raise SourceBuildError(f"{ts_source} not found -- expected a file matching the directory's own name")
    if shutil.which("tsc") is None:
        raise SourceBuildError("`tsc` not found on PATH -- install TypeScript to build this widget")
    project = widget_dir
    if components:
        # An `extends` config next to the build output: the widget's own
        # tsconfig keeps governing every compiler option (and its own
        # relative paths), while `files` gains the component sources.
        tsconfig = _read_tsconfig(widget_dir)
        own = [str((widget_dir / f).resolve()) for f in _read_files_entries(tsconfig)]
        files = [str(c.ts.resolve()) for c in components]
        files += [f for f in own if f not in files]
        # Compiled into its own wiped directory: tsc lays output out relative
        # to the inputs' common root, which differs between a widget with
        # components and one without (or between libraries), so reusing the
        # widget's outDir would leave stale, differently-nested copies.
        out = components_out_dir(widget_dir)
        shutil.rmtree(out, ignore_errors=True)
        config: dict = {
            "extends": "../tsconfig.json",
            "compilerOptions": {"outDir": str(out.resolve())},
            "files": files,
        }
        if not own:
            config["include"] = [str(widget_dir.resolve()) + "/**/*.ts"]
        build_dir = widget_dir / SOURCE_BUILD_CACHE_DIRNAME
        build_dir.mkdir(parents=True, exist_ok=True)
        project = build_dir / _COMPONENTS_BUILD_CONFIG
        project.write_text(json.dumps(config, indent=2))
    result = subprocess.run(["tsc", "-p", str(project)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SourceBuildError(f"tsc failed:\n{result.stdout}{result.stderr}")


def _component_stem_order(out_dir: Path, ordered_stems: list[str] | None, components: list[Component]) -> list[str] | None:
    """The concatenation order once components are involved: their compiled
    files first (a widget's classes may extend them), then the widget's own
    -- in its tsconfig "files" order if given, else alphabetical."""
    if not components:
        return ordered_stems
    first = [c.name for c in components]
    rest = ordered_stems if ordered_stems is not None else sorted({p.stem for p in out_dir.rglob("*.js")})
    return first + [stem for stem in rest if stem not in first]


def _inject_component_templates(html: str, components: list[Component], html_path: Path) -> str:
    blocks = []
    for component in components:
        template = component.template
        if template is None:
            continue
        text = template.read_text()
        ids = _TEMPLATE_ID_RE.findall(text)
        # A widget that already hand-pasted this template (the old way) keeps
        # working: a second copy would duplicate its id.
        if ids and all(re.search(r"id\s*=\s*[\"']" + re.escape(i) + r"[\"']", html) for i in ids):
            logger.warning(
                "%s already contains the template(s) of component %s:%s; not injecting a second copy",
                html_path, component.scope, component.name,
            )
            continue
        blocks.append(f"<!-- component {component.scope}:{component.name} -->\n{text.rstrip()}\n")
    if not blocks:
        return html
    block = "".join(blocks)
    if html.count(_TEMPLATES_MARKER) > 1:
        raise SourceBuildError(f"{html_path} must contain at most one {_TEMPLATES_MARKER!r} marker")
    if _TEMPLATES_MARKER in html:
        return html.replace(_TEMPLATES_MARKER, block)
    body = re.search(r"<body\b[^>]*>", html, re.IGNORECASE)
    if body is None:
        raise SourceBuildError(
            f"{html_path} has no <body> to put component templates after; add one, "
            f"or a {_TEMPLATES_MARKER} line where they should go"
        )
    return html[: body.end()] + "\n" + block + html[body.end() :]


def _concatenate_compiled_js(out_dir: Path, ordered_stems: list[str] | None) -> str:
    if not out_dir.is_dir():
        raise SourceBuildError(f"tsc reported success but {out_dir} doesn't exist")
    js_files = sorted(out_dir.rglob("*.js"))
    if not js_files:
        raise SourceBuildError(f"no .js files found under {out_dir} after compiling")
    if ordered_stems is None:
        return "".join(path.read_text() for path in js_files)

    by_stem = {}
    for path in js_files:
        if path.stem in by_stem:
            raise SourceBuildError(
                f"multiple compiled files named {path.stem}.js under {out_dir} "
                f"({by_stem[path.stem]}, {path}) -- tsconfig.json's \"files\" list "
                f"can't disambiguate same-named files in different directories"
            )
        by_stem[path.stem] = path

    missing = [stem for stem in ordered_stems if stem not in by_stem]
    if missing:
        raise SourceBuildError(
            f"tsconfig.json's \"files\" list names {missing[0]}.ts, but no "
            f"matching {missing[0]}.js was found under {out_dir} after compiling"
        )
    unlisted = [stem for stem in by_stem if stem not in ordered_stems]
    if unlisted:
        raise SourceBuildError(
            f"{out_dir} contains {unlisted[0]}.js, which isn't listed in "
            f"tsconfig.json's \"files\" -- add it there so its position in the "
            f"compile order is explicit"
        )
    return "".join(by_stem[stem].read_text() for stem in ordered_stems)


def _substitute_marker(widget_dir: Path, compiled_js: str, components: list[Component] | None = None) -> str:
    html_path = widget_dir / "widget.html"
    if not html_path.is_file():
        raise SourceBuildError(f"{html_path} not found")
    html = html_path.read_text()
    if components:
        # Before the JS goes in, so the search for <body> only sees markup.
        html = _inject_component_templates(html, components, html_path)
    if html.count(_BUILD_MARKER) != 1:
        raise SourceBuildError(f"{html_path} must contain exactly one {_BUILD_MARKER!r} marker line")
    return html.replace(_BUILD_MARKER, compiled_js)


def build_from_source(project_dir: Path, source_path: str) -> Path | None:
    """TODO 13f4ad5: compiles a source-backed custom widget (see
    "Authoring from real source" in tempui-custom-widgets.md) straight
    to a gitignored `<project_dir>/<source_path>/.build/index.html` --
    the "rebuilt on demand" alternative to baking `html_b64` into the
    `.desk` file for a widget whose `CustomWidgetDefinition.source_path`
    is known. Reimplements the TS-compile-and-package half of
    .desk_temp/build_widget.py's own build_widget() (that file is
    deliberately self-contained, with no dependency on this package, so
    it can be generated into an arbitrary project) but skips the
    base64-encode-and-write-a-tempui-file steps, since the caller wants
    a real HTML document on disk, not a DefineWidget file. Returns the
    `.build` directory (to mount), or None (logged, not raised) if the
    build fails for any reason -- missing `tsc`, a compile error, a
    malformed widget.html -- so one bad/stale source directory can't
    take the whole app down."""
    widget_dir = project_dir / source_path
    try:
        tsconfig = _read_tsconfig(widget_dir)
        out_dir = _read_out_dir(widget_dir, tsconfig)
        ordered_stems = _read_ordered_stems(tsconfig)
        components = resolve_components(read_component_names(widget_dir), project_dir)
        if components:
            out_dir = components_out_dir(widget_dir)
        _compile_typescript(widget_dir, components)
        compiled_js = _concatenate_compiled_js(out_dir, _component_stem_order(out_dir, ordered_stems, components))
        html = _substitute_marker(widget_dir, compiled_js, components)
    except SourceBuildError as e:
        logger.error("Failed to build source-backed custom widget at %s: %s", widget_dir, e)
        return None
    build_dir = widget_dir / SOURCE_BUILD_CACHE_DIRNAME
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text(html)
    return build_dir


def read_source_manifest(project_dir: Path, source_path: str) -> tuple[list[str], dict[str, str]] | None:
    """TODO 8bbc484: the `capabilities` list and `state_schema` dict
    currently declared by a source-backed widget's own `widget.json`, so a
    rebuild can bring a promoted widget's stored definition back in sync
    (the stored copy is otherwise frozen at promotion time). `None` if the
    manifest is missing, unparseable or malformed -- the caller then keeps
    what it has, since a half-written file mid-edit must never strip a
    widget's capabilities."""
    try:
        manifest = json.loads((project_dir / source_path / "widget.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    capabilities = manifest.get("capabilities", [])
    state_schema = manifest.get("state_schema", {})
    if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
        return None
    if not isinstance(state_schema, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in state_schema.items()
    ):
        return None
    return list(capabilities), dict(state_schema)


def source_watch_exclusions(widget_dir: Path) -> set[Path]:
    """TODO 4eb3d9e: directories under `widget_dir` that
    build_from_source itself writes/reads as build output --
    SOURCE_BUILD_CACHE_DIRNAME (".build") always, plus
    tsconfig.json's own compilerOptions.outDir when discoverable. A
    caller watching `widget_dir` for genuine *source* edits (see
    desk.shell.promoted_widget_source_watcher) must ignore changes
    under these, or the rebuild the watch itself triggers would
    immediately retrigger the same watch. Best-effort, mirroring
    build_from_source's own resilience to a missing/malformed source
    tree: a bad tsconfig.json just means "no outDir to add," not an
    error -- .build is always excluded regardless."""
    exclusions = {widget_dir / SOURCE_BUILD_CACHE_DIRNAME}
    try:
        exclusions.add(_read_out_dir(widget_dir, _read_tsconfig(widget_dir)))
    except SourceBuildError:
        pass
    return exclusions


def external_source_files(widget_dir: Path) -> list[Path]:
    """TODO 8a65056: the files a source-backed widget's `tsconfig.json`
    `"files"` array lists that live *outside* its own directory (a shared
    base class or module, e.g. `../_shared/x.ts`), as absolute, lexically
    normalized paths -- the files `build_from_source` compiles into the
    widget but that a watch of `widget_dir` alone never sees change.
    Best-effort like `source_watch_exclusions`: a missing/malformed
    tsconfig.json or a non-string entry just yields fewer paths."""
    try:
        entries = _read_files_entries(_read_tsconfig(widget_dir))
    except SourceBuildError:
        return []
    base = Path(os.path.normpath(widget_dir))
    external: list[Path] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        path = Path(os.path.normpath(base / entry))
        if path != base and base not in path.parents and path not in external:
            external.append(path)
    # TODO d34f8ed: files of the project-library components the widget lists
    # (the mutable library). Desk-wide components are static, not watched.
    project = _project_dir_of(widget_dir)
    if project is not None:
        try:
            components = resolve_components(read_component_names(widget_dir), project)
        except SourceBuildError:
            components = []
        for component in components:
            if component.scope == "project":
                for path in (component.ts, component.template):
                    if path is not None:
                        path = Path(os.path.normpath(path))
                        if path not in external:
                            external.append(path)
    return external


def _project_dir_of(widget_dir: Path) -> Path | None:
    """The project directory a source widget directory belongs to, from its
    conventional location (`<project>/desk_widgets/<name>` once promoted,
    `<project>/.desk_temp/widgets/<name>` before), else None."""
    parent = widget_dir.parent
    if parent.name == PROMOTED_WIDGET_SRC_DIRNAME:
        return parent.parent
    if parent.name == CUSTOM_WIDGET_SRC_DIRNAME and parent.parent.name == TEMP_UI_DIRNAME:
        return parent.parent.parent
    return None


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_widget_name(name: str) -> str:
    """Strips separators and case so PascalCase/camelCase/kebab-case/
    snake_case variants of the same conceptual name compare equal --
    e.g. "PdfViewer", "pdf-viewer", "pdf_viewer", and "pdfViewer" all
    normalize to "pdfviewer" (TODO 9613bb0)."""
    return _NON_ALNUM_RE.sub("", name.lower())


@dataclass
class LikelySourceCandidate:
    """A `.desk_temp/widgets/` subdirectory that plausibly holds a
    promoted widget's real authoring source, found because it has no
    durably-recorded `source_path` to go on (see
    find_likely_source_candidates). `matched_by` is `"keyword"` (its
    own `widget.json` `"keyword"` field matches the widget being
    promoted exactly -- the strong signal) or `"name"` (only the
    directory's own name, once normalized, matches -- the common case,
    since a source directory's kebab-case name is almost never the
    same string as the DSL's own PascalCase/camelCase keyword)."""

    path: Path
    matched_by: str


def find_likely_source_candidates(project_dir: Path, keyword: str) -> list[LikelySourceCandidate]:
    """TODO 9613bb0: on promotion, a widget with no usable recorded
    `source_path` is usually either genuinely hand-authored inline, or
    was built "from real source" (temp_ui.py's "Authoring from real
    source") by something that never recorded a `SourcePath` line -- an
    older `build_widget.py`, or a hand-copied source directory. Scans
    `TEMP_UI_DIRNAME/CUSTOM_WIDGET_SRC_DIRNAME` (`.desk_temp/widgets/`)
    -- the one documented location such a not-yet-promoted widget's
    source ever lives -- for directories that look like they could be
    this widget's real source: a `widget.json` whose own `"keyword"`
    field matches exactly, or a directory name that's a case/separator
    variant of `keyword` (see _normalize_widget_name). Only directories
    containing a `widget.json` are considered at all, so an unrelated
    `.desk_temp/widgets/` subdirectory never surfaces as a false
    positive. A malformed/unreadable `widget.json` just falls through
    to the name check rather than raising. Returns `[]` if
    `.desk_temp/widgets/` doesn't exist."""
    widgets_dir = project_dir / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME
    if not widgets_dir.is_dir():
        return []
    target = _normalize_widget_name(keyword)
    candidates = []
    for entry in sorted(widgets_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "widget.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict) and manifest.get("keyword") == keyword:
            candidates.append(LikelySourceCandidate(path=entry, matched_by="keyword"))
        elif _normalize_widget_name(entry.name) == target:
            candidates.append(LikelySourceCandidate(path=entry, matched_by="name"))
    return candidates
