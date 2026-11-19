"""The tempui doc set's content, kept as files in `src/desk/tempui_content/` instead of constants in `temp_ui.py`
(TODO de16076): the constants made every change to the changelog or a doc a merge conflict in one giant file.

The directory holds two kinds of file, both loaded -- completely, and before anything else in `desk.temp_ui` can
be used -- when `desk.temp_ui` is imported, so Desk is not up until every one of them has been read and checked
(a malformed file stops startup with a `TempUiContentError` naming it):

* `*.json` -- changelog entries. Each file is a JSON array of any number of entries (a new change normally adds a
  new file with one entry; existing files may be regrouped or merged freely, e.g. when tags are collapsed). An
  entry is an object with exactly these fields:

    - `tag`: the tag id (see `desk.temp_ui.generate_tag`), e.g. "desk_call_hmsvc: agents call services #506728";
    - `monthstamp`: "MM YYYY", the month the change was made;
    - `description`: the Markdown body shown for that tag in the changelog docs and the doc-upgrade notification;
    - `breaking` (optional, default false): true if this entry belongs in the *breaking changes* doc rather than
      *new features*. A tag may have one entry of each kind.

  Entries are ordered, oldest first, by (monthstamp, file name, position in the file); that order is the display
  order of the changelog (newest first) and of `CURRENT_TAGS`. Name a new file `YYYY-MM-DD-<slug>.json` so files
  made on the same day or month sort sensibly. `scripts/new_tempui_changelog_entry.py` creates one for you.

* `*.md` -- the long text of one agent-facing doc each, written verbatim into every project's `.desk_temp/` under
  its own file name (e.g. `tempui-markdown.md`). Files starting with "." are ignored; any other file type is an
  error, so a misspelled extension cannot silently drop content.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent / "tempui_content"
MONTHSTAMP_RE = re.compile(r"^(0[1-9]|1[0-2]) (\d{4})$")
_REQUIRED_FIELDS = ("tag", "monthstamp", "description")
_OPTIONAL_FIELDS = ("breaking",)


class TempUiContentError(Exception):
    """A content file is missing, malformed or contradicts another."""


@dataclass(frozen=True)
class ChangelogEntry:
    tag: str
    monthstamp: str
    description: str
    breaking: bool
    source: str  # the file name, for error messages and ordering
    index: int  # position within that file

    @property
    def sort_key(self) -> tuple[int, int, str, int]:
        month, year = self.monthstamp.split()
        return (int(year), int(month), self.source, self.index)


@dataclass(frozen=True)
class TempUiContent:
    tags: tuple[str, ...]  # every tag, oldest first
    new_features: dict[str, str]  # tag id -> description
    breaking_changes: dict[str, str]
    docs: dict[str, str]  # file name -> Markdown, from the *.md files


def parse_entries(text: str, source: str) -> list[ChangelogEntry]:
    """The entries of one JSON file's text; `source` is the file name used in errors and ordering."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise TempUiContentError(f"{source}: not valid JSON ({e}).") from None
    if not isinstance(data, list):
        raise TempUiContentError(f"{source}: must be a JSON array of entries.")
    entries = []
    for index, item in enumerate(data):
        where = f"{source} entry {index}"
        if not isinstance(item, dict):
            raise TempUiContentError(f"{where}: must be an object.")
        missing = [f for f in _REQUIRED_FIELDS if f not in item]
        unknown = [f for f in item if f not in _REQUIRED_FIELDS + _OPTIONAL_FIELDS]
        if missing:
            raise TempUiContentError(f"{where}: missing {', '.join(missing)}.")
        if unknown:
            raise TempUiContentError(f"{where}: unknown field(s) {', '.join(unknown)}.")
        for field in _REQUIRED_FIELDS:
            if not isinstance(item[field], str) or not item[field].strip():
                raise TempUiContentError(f"{where}: {field} must be a non-empty string.")
        if not MONTHSTAMP_RE.match(item["monthstamp"]):
            raise TempUiContentError(f"{where}: monthstamp must look like '11 2026' (MM YYYY), not {item['monthstamp']!r}.")
        breaking = item.get("breaking", False)
        if not isinstance(breaking, bool):
            raise TempUiContentError(f"{where}: breaking must be true or false.")
        entries.append(
            ChangelogEntry(item["tag"], item["monthstamp"], item["description"], breaking, source, index)
        )
    return entries


def load(directory: Path | None = None) -> TempUiContent:
    """Reads every file in the content directory and returns the assembled dicts."""
    directory = Path(directory) if directory is not None else CONTENT_DIR
    if not directory.is_dir():
        raise TempUiContentError(f"The tempui content directory {directory} does not exist.")
    entries: list[ChangelogEntry] = []
    docs: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if not path.is_file():
            raise TempUiContentError(f"{path.name}: unexpected directory in the tempui content directory.")
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise TempUiContentError(f"{path.name}: cannot be read as UTF-8 text ({e}).") from None
        if path.suffix == ".json":
            entries += parse_entries(text, path.name)
        elif path.suffix == ".md":
            docs[path.name] = text
        else:
            raise TempUiContentError(f"{path.name}: only .json and .md files belong in the tempui content directory.")

    entries.sort(key=lambda e: e.sort_key)
    new_features: dict[str, str] = {}
    breaking_changes: dict[str, str] = {}
    first_source: dict[tuple[str, bool], str] = {}
    tags: list[str] = []
    for entry in entries:
        target = breaking_changes if entry.breaking else new_features
        kind = "breaking" if entry.breaking else "new-feature"
        if entry.tag in target:
            raise TempUiContentError(
                f"{entry.source}: a {kind} entry for tag {entry.tag!r} already exists in "
                f"{first_source[(entry.tag, entry.breaking)]}."
            )
        target[entry.tag] = entry.description
        first_source[(entry.tag, entry.breaking)] = entry.source
        if entry.tag not in tags:
            tags.append(entry.tag)
    # Display order is newest-first wherever these are rendered, so keep each dict oldest-first like `tags`.
    return TempUiContent(tuple(tags), new_features, breaking_changes, docs)
