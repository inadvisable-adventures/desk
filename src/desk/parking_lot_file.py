"""Parsing for PARKINGLOT.md -- shared by the Parking Lot widget
(widgets/parking_lot/). See plans/parking-lot-widget.md.

Mirrors desk.questions_file's shape (dataclass + regex-based parser),
adapted for PARKINGLOT.md's actual structure: each item is a top-level
`- **<title>**` bullet -- the title itself can wrap across multiple
source lines for a long enough title (e.g. this project's own
`WidgetSpawnMenu._activate_item` entry) -- followed by free-form body
prose up to the next top-level bullet or EOF.

`line_number` uses the exact definition already established by the
tempui DiscussParkingLotItem keyword's own doc (TODO 624ff3a): the
1-indexed line, in the file just read, where the item's own leading
`- **Title**` bullet starts -- so it's always safe to hand to
`DeskWindow._place_discuss_claude_widget`'s `parking_lot_line`
parameter without a second convention to keep in sync.

No render/write-back function is needed here (unlike
questions_file.py's render_questions_file) -- consumers of this module
only ever read PARKINGLOT.md, never rewrite it."""
import re
from dataclasses import dataclass
from pathlib import Path

PARKING_LOT_FILENAME = "PARKINGLOT.md"

ENTRY_START_RE = re.compile(r"^- \*\*", re.MULTILINE)
TITLE_RE = re.compile(r"\A- \*\*(.*?)\*\*", re.DOTALL)


@dataclass
class ParkingLotEntry:
    title: str  # collapsed to one line (a wrapped source title's lines joined with spaces)
    line_number: int  # 1-indexed line, in the file just read, where this item's "- **Title**" bullet starts
    raw_text: str  # this item's own text, heading bullet through body, trailing whitespace trimmed


def find_nearest_parking_lot_file(start_dir: Path) -> Path | None:
    """Searches start_dir and its parents (in that order) for a
    PARKINGLOT.md -- same walk-up-directories convention as
    desk.questions_file.find_nearest_questions_file."""
    for directory in (start_dir, *start_dir.parents):
        candidate = directory / PARKING_LOT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_parking_lot_file(path: Path) -> tuple[str, list[ParkingLotEntry]]:
    """Returns (preamble_text, entries). preamble_text is everything
    before the first item (title line, intro prose, the "## Items"
    heading)."""
    text = path.read_text()
    starts = [m.start() for m in ENTRY_START_RE.finditer(text)]

    preamble = text[: starts[0]] if starts else text

    entries = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        raw_text = text[start:end].rstrip()
        title_match = TITLE_RE.match(raw_text)
        title = " ".join(title_match.group(1).split()) if title_match else raw_text.splitlines()[0]
        line_number = text[:start].count("\n") + 1
        entries.append(ParkingLotEntry(title=title, line_number=line_number, raw_text=raw_text))
    return preamble, entries
