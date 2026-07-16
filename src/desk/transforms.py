"""Transform discovery & manifest parsing (TODO 54d8c18). See
design-docs/transforms.md for the full design.

A transform converts data of one named type into another (`input_type
-> output_type`), optionally with `config` and an `identity` mapping.
Described by a `transform.json` manifest next to its entry file, and
discovered by scanning `.desk_temp/transforms/<name>/` (TypeScript/
JavaScript only) and `desk_transforms/<name>/` (any of the 3
languages) *directly* -- unlike `DefineWidget` custom widgets, there's
no build-artifact indirection here: a transform is never "placed"
anywhere, so nothing forces it through a separate discovered-artifact
step the way a widget's tempui-placeability does.

No Qt dependency here (mirrors desk.file_type_registry's own shape) --
importable from anywhere, including a headless script."""

import json
from dataclasses import dataclass
from pathlib import Path

TRANSFORM_MANIFEST_FILENAME = "transform.json"
VALID_KINDS = ("python", "typescript", "javascript")
# Full paths: <desk_directory>/.desk_temp/transforms/, and
# <desk_directory>/desk_transforms/ (project root, not under .desk_temp).
TEMP_TRANSFORMS_DIRNAME = "transforms"
PROJECT_TRANSFORMS_DIRNAME = "desk_transforms"


class TransformDiscoveryError(Exception):
    pass


@dataclass
class TransformInfo:
    id: str
    path: Path  # the transform's own directory
    kind: str  # one of VALID_KINDS
    entry: str
    name: str
    input_type: str
    output_type: str
    has_config: bool
    has_identity: bool
    location: str  # "desk_temp" | "project"


def _load_manifest(manifest_path: Path, location: str) -> TransformInfo:
    transform_id = manifest_path.parent.name
    manifest = json.loads(manifest_path.read_text())

    kind = manifest.get("kind")
    if kind not in VALID_KINDS:
        raise TransformDiscoveryError(f"{transform_id}: invalid or missing kind {kind!r}")
    if location == "desk_temp" and kind == "python":
        raise TransformDiscoveryError(
            f"{transform_id}: Python transforms aren't allowed in .desk_temp -- "
            "move to desk_transforms/ or rewrite in TypeScript/JavaScript"
        )

    try:
        entry = manifest["entry"]
        input_type = manifest["input_type"]
        output_type = manifest["output_type"]
    except KeyError as e:
        raise TransformDiscoveryError(f"{transform_id}: missing required manifest key {e}") from e

    return TransformInfo(
        id=transform_id,
        path=manifest_path.parent,
        kind=kind,
        entry=entry,
        name=manifest.get("name", transform_id),
        input_type=input_type,
        output_type=output_type,
        has_config=bool(manifest.get("has_config", False)),
        has_identity=bool(manifest.get("has_identity", False)),
        location=location,
    )


def discover_transforms_with_errors(
    desk_temp_dir: Path | None, project_dir: Path | None
) -> tuple[dict[str, TransformInfo], dict[str, str]]:
    """Scans both directories directly. `desk_temp_dir`/`project_dir`
    may be None (no current Desk directory known yet) or simply not
    exist -- both are treated as "nothing found there," not an error.
    `project_dir` is scanned second, so it wins a `transform_id`
    collision (plain dict assignment overwrites) -- the promoted/
    authoritative location takes precedence over the local scratch
    copy, the same relationship `desk_widgets/<name>/` has to
    `.desk_temp/widgets/<name>/`. A subdirectory whose manifest is
    missing/invalid is recorded in the returned errors dict (keyed by
    directory name) instead of raised -- surfaced by the Transform
    Manager widget (TODO `b5e15cf`), not fatal to discovering
    everything else."""
    transforms: dict[str, TransformInfo] = {}
    errors: dict[str, str] = {}
    for location, base in (("desk_temp", desk_temp_dir), ("project", project_dir)):
        if base is None or not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            manifest_path = entry / TRANSFORM_MANIFEST_FILENAME
            if not manifest_path.is_file():
                continue
            try:
                info = _load_manifest(manifest_path, location)
            except (TransformDiscoveryError, json.JSONDecodeError, OSError) as e:
                errors[entry.name] = str(e)
                continue
            transforms[info.id] = info
    return transforms, errors


def discover_transforms(desk_temp_dir: Path | None, project_dir: Path | None) -> dict[str, TransformInfo]:
    """The common case -- see discover_transforms_with_errors for the
    errors dict, needed only by callers (the Transform Manager) that
    want to surface *why* something wasn't discovered."""
    transforms, _errors = discover_transforms_with_errors(desk_temp_dir, project_dir)
    return transforms
