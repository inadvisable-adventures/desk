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
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from desk.temp_ui import CUSTOM_WIDGET_SRC_DIRNAME, SOURCE_BUILD_CACHE_DIRNAME, TEMP_UI_DIRNAME, CustomWidgetDefinition

logger = logging.getLogger(__name__)

CUSTOM_WIDGETS_CACHE_DIRNAME = "custom_widgets"

# SOURCE_BUILD_CACHE_DIRNAME (TODO 13f4ad5, where build_from_source
# below writes a source-backed widget's rebuilt-on-demand HTML --
# gitignored, inside the widget's own durable source directory rather
# than a shared cache, so it moves for free whenever the source
# directory itself does, e.g. on promotion) is defined in desk.temp_ui,
# not here -- see that module's own comment (TODO 1c67fe5) for why.

_BUILD_MARKER = "/* BUILD:COMPILED_JS */"


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


def _read_ordered_stems(tsconfig: dict) -> list[str] | None:
    """Mirrors .desk_temp/build_widget.py's own _read_ordered_stems --
    see that file's docstring (TODO 3fc5331) for why this matters for a
    widget split across more than one .ts file."""
    files = tsconfig.get("files")
    if not files:
        return None
    return [Path(entry).stem for entry in files]


def _compile_typescript(widget_dir: Path) -> None:
    ts_source = widget_dir / f"{widget_dir.name}.ts"
    if not ts_source.is_file():
        raise SourceBuildError(f"{ts_source} not found -- expected a file matching the directory's own name")
    if shutil.which("tsc") is None:
        raise SourceBuildError("`tsc` not found on PATH -- install TypeScript to build this widget")
    result = subprocess.run(["tsc", "-p", str(widget_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SourceBuildError(f"tsc failed:\n{result.stdout}{result.stderr}")


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


def _substitute_marker(widget_dir: Path, compiled_js: str) -> str:
    html_path = widget_dir / "widget.html"
    if not html_path.is_file():
        raise SourceBuildError(f"{html_path} not found")
    html = html_path.read_text()
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
        _compile_typescript(widget_dir)
        compiled_js = _concatenate_compiled_js(out_dir, ordered_stems)
        html = _substitute_marker(widget_dir, compiled_js)
    except SourceBuildError as e:
        logger.error("Failed to build source-backed custom widget at %s: %s", widget_dir, e)
        return None
    build_dir = widget_dir / SOURCE_BUILD_CACHE_DIRNAME
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text(html)
    return build_dir


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
