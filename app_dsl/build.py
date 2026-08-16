#!/usr/bin/env python3
"""Reads an app-structure DSL definition (see README.md) and generates
real TypeScript (+ CSS) wiring code for it -- see
plans/app-structure-dsl.md (Desk repo) for the design this implements.

Deliberately self-contained: no import of Desk's own `desk` package,
which a project using this tool won't have installed -- same posture
as Desk's own generated .desk_temp/build_widget.py. This file itself
is mirrored fresh into .desk_temp/app_dsl/ on every Desk-project open
(TODO 48e3b39), not seeded once and left to go stale.

Usage:
    python3 .desk_temp/app_dsl/build.py <definition.json> <components_dir> <out_dir> [--mode=module|global]

`--mode` defaults to `module` (real ES modules, for a standalone
build). `--mode=global` emits module-free, global-script code instead
-- for build_widget.py's own DefineWidget packaging pipeline, which
concatenates non-module scripts. See codegen.py's own module
docstring and README.md for what each mode actually means and its
constraints (mode=global specifically requires your own component/
handler source to also avoid import/export).

Writes the generated files into <out_dir> and prints each path
written, one per line.
"""
import sys
from pathlib import Path

from codegen import VALID_MODES, generate
from parse import parse_app_definition
from schema import DslError


def main(argv: list[str]) -> int:
    mode = "module"
    positional = []
    for arg in argv:
        if arg.startswith("--mode="):
            mode = arg[len("--mode=") :]
        else:
            positional.append(arg)

    if len(positional) != 3:
        print(__doc__)
        return 1
    if mode not in VALID_MODES:
        print(f"error: --mode must be one of {VALID_MODES}, got {mode!r}", file=sys.stderr)
        return 1

    definition_path, components_dir, out_dir = (Path(a) for a in positional)
    if not definition_path.is_file():
        print(f"{definition_path} not found", file=sys.stderr)
        return 1
    if not components_dir.is_dir():
        print(f"{components_dir} is not a directory", file=sys.stderr)
        return 1

    try:
        definition = parse_app_definition(definition_path.read_text())
        outputs = generate(definition, str(components_dir), str(out_dir), mode=mode)
    except DslError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in outputs.items():
        out_path = out_dir / filename
        out_path.write_text(content)
        print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
