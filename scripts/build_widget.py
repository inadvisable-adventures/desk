#!/usr/bin/env python3
"""Packages a DefineWidget source directory (TypeScript custom element +
template HTML + tsconfig + manifest) into a `DefineWidget` tempui file
under `.desk_temp/` -- see "Authoring from real source" in
`tempui-custom-widgets.md` for the full authoring pattern this
implements, and design-docs/custom-widget-authoring.md section 1 for why.

This file is meant to be copied verbatim into other projects (seeded
alongside development-process.md on "New Desk" creation, the same way
scripts/todo_item_ids.py already is), so it's deliberately self-contained:
no import of this app's own `desk` package, which a destination project
won't have installed. Takes any directory as its argument -- it doesn't
care whether that's a not-yet-promoted widget's source (recommended at
`.desk_temp/widgets/<name>/`) or a promoted one's (moved to
`desk_widgets/<name>/` at the project root on promotion, TODO 59c5a70);
the build process is identical either way.

Usage:
    python3 scripts/build_widget.py .desk_temp/widgets/<name>
    python3 scripts/build_widget.py desk_widgets/<name>  # after promotion

Expects, in that directory:
    <name>.ts       -- the widget's logic (name must match the directory).
    widget.html     -- self-contained document, with a `<script>` whose
                        entire content is the one-line marker comment
                        `/* BUILD:COMPILED_JS */`.
    tsconfig.json   -- must set compilerOptions.outDir.
    widget.json     -- {"keyword": str, "label": str, "width": int,
                        "height": int}.

Writes a fresh `.desk_temp/<uuid>` tempui file and prints its path.
"""
import base64
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

BUILD_MARKER = "/* BUILD:COMPILED_JS */"
REQUIRED_MANIFEST_KEYS = ("keyword", "label", "width", "height")
HTML_CHUNK_SIZE = 2000
TEMP_UI_DIRNAME = ".desk_temp"


class BuildError(Exception):
    """Any problem that should abort the build with a clear message --
    caught once in main(), never elsewhere, so every failure path prints
    one clean line instead of a traceback."""


def _read_manifest(widget_dir: Path) -> dict:
    manifest_path = widget_dir / "widget.json"
    if not manifest_path.is_file():
        raise BuildError(f"{manifest_path} not found")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        raise BuildError(f"{manifest_path} is not valid JSON: {e}") from e
    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
    if missing:
        raise BuildError(f"{manifest_path} is missing required key(s): {', '.join(missing)}")
    return manifest


def _read_out_dir(widget_dir: Path) -> Path:
    tsconfig_path = widget_dir / "tsconfig.json"
    if not tsconfig_path.is_file():
        raise BuildError(f"{tsconfig_path} not found")
    try:
        tsconfig = json.loads(tsconfig_path.read_text())
    except json.JSONDecodeError as e:
        raise BuildError(f"{tsconfig_path} is not valid JSON: {e}") from e
    out_dir = tsconfig.get("compilerOptions", {}).get("outDir")
    if not out_dir:
        raise BuildError(f"{tsconfig_path} must set compilerOptions.outDir")
    return widget_dir / out_dir


def _compile_typescript(widget_dir: Path) -> None:
    ts_source = widget_dir / f"{widget_dir.name}.ts"
    if not ts_source.is_file():
        raise BuildError(f"{ts_source} not found -- expected a file matching the directory's own name")
    # Deliberately never falls back to `npx tsc`: without TypeScript
    # actually installed, `npx tsc` silently resolves to an unrelated,
    # abandoned npm package also called `tsc` -- a confusing failure mode
    # worth avoiding entirely by only ever invoking a real `tsc` on PATH.
    if shutil.which("tsc") is None:
        raise BuildError("`tsc` not found on PATH -- install TypeScript to build this widget")
    result = subprocess.run(["tsc", "-p", str(widget_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"tsc failed:\n{result.stdout}{result.stderr}")


def _concatenate_compiled_js(out_dir: Path) -> str:
    if not out_dir.is_dir():
        raise BuildError(f"tsc reported success but {out_dir} doesn't exist")
    js_files = sorted(out_dir.rglob("*.js"))
    if not js_files:
        raise BuildError(f"no .js files found under {out_dir} after compiling")
    return "".join(path.read_text() for path in js_files)


def _substitute_marker(widget_dir: Path, compiled_js: str) -> str:
    html_path = widget_dir / "widget.html"
    if not html_path.is_file():
        raise BuildError(f"{html_path} not found")
    html = html_path.read_text()
    if html.count(BUILD_MARKER) != 1:
        raise BuildError(f"{html_path} must contain exactly one {BUILD_MARKER!r} marker line")
    return html.replace(BUILD_MARKER, compiled_js)


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def build_widget(widget_dir: Path) -> str:
    manifest = _read_manifest(widget_dir)
    out_dir = _read_out_dir(widget_dir)
    _compile_typescript(widget_dir)
    compiled_js = _concatenate_compiled_js(out_dir)
    html = _substitute_marker(widget_dir, compiled_js)
    html_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")

    lines = [
        f"DefineWidget\t{manifest['keyword']}\t{manifest['label']}",
        f"Size\t{manifest['width']}\t{manifest['height']}",
    ]
    lines.extend(f"Html\t{chunk}" for chunk in _chunk(html_b64, HTML_CHUNK_SIZE))
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    widget_dir = Path(argv[0])
    if not widget_dir.is_dir():
        print(f"{widget_dir} is not a directory", file=sys.stderr)
        return 1

    try:
        tempui_text = build_widget(widget_dir)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    temp_ui_dir = Path(TEMP_UI_DIRNAME)
    temp_ui_dir.mkdir(exist_ok=True)
    out_path = temp_ui_dir / str(uuid.uuid4())
    out_path.write_text(tempui_text)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
