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
    python3 .desk_temp/app_dsl/build.py <definition.json> <components_dir> <out_dir>

Writes the generated files into <out_dir> and prints each path
written, one per line.
"""
import sys
from pathlib import Path

from codegen import generate
from parse import parse_app_definition
from schema import DslError


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 1
    definition_path, components_dir, out_dir = (Path(a) for a in argv)
    if not definition_path.is_file():
        print(f"{definition_path} not found", file=sys.stderr)
        return 1
    if not components_dir.is_dir():
        print(f"{components_dir} is not a directory", file=sys.stderr)
        return 1

    try:
        definition = parse_app_definition(definition_path.read_text())
        outputs = generate(definition, str(components_dir), str(out_dir))
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
