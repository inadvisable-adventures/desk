"""TODO de16076: the tempui changelog and long-text docs live in src/desk/tempui_content/*.json|md, loaded when
desk.temp_ui is imported. Checks the loader's format rules and ordering, the real directory's integrity, and the
helper script that writes a new entry."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import temp_ui, tempui_content  # noqa: E402
from desk.tempui_content import TempUiContentError, load  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def entry(tag, month="11 2026", description="d", **extra):
    return {"tag": tag, "monthstamp": month, "description": description, **extra}


def dir_with(files: dict) -> Path:
    d = Path(tempfile.mkdtemp(prefix="tuc"))
    for name, content in files.items():
        if isinstance(content, bytes):
            (d / name).write_bytes(content)
        elif isinstance(content, (list, dict)):
            (d / name).write_text(json.dumps(content), encoding="utf-8")
        else:
            (d / name).write_text(content, encoding="utf-8")
    return d


def fails_dir(path):
    try:
        load(path)
    except TempUiContentError as e:
        return "unexpected directory" in str(e)
    return False


def fails(files, text):
    try:
        load(dir_with(files))
    except TempUiContentError as e:
        return text in str(e)
    return False


# ---- the real directory, as temp_ui assembled it ----
real = load()
check("temp_ui's tags, entries and docs are exactly what the directory loads",
      temp_ui.CURRENT_TAGS == real.tags and temp_ui._NEW_FEATURES == real.new_features
      and temp_ui._BREAKING_CHANGES == real.breaking_changes)
check("tags are unique and every one has a description", len(set(real.tags)) == len(real.tags)
      and all(t in real.new_features or t in real.breaking_changes for t in real.tags))
check("no entry is empty", all(v.strip() for v in list(real.new_features.values()) + list(real.breaking_changes.values())))
check("every .md file is published in SPLIT_DOC_CONTENT verbatim",
      real.docs and all(temp_ui.SPLIT_DOC_CONTENT[name] == text for name, text in real.docs.items()))
check("the generated and script files are published too",
      {temp_ui.BREAKING_CHANGES_DOC_FILENAME, temp_ui.NEW_FEATURES_DOC_FILENAME, temp_ui.BUILD_WIDGET_SCRIPT_FILENAME,
       temp_ui.BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME} <= set(temp_ui.SPLIT_DOC_CONTENT))
check("the docs the overview links to all exist",
      all(name in temp_ui.SPLIT_DOC_CONTENT for name in (
          temp_ui.CUSTOM_WIDGETS_DOC_FILENAME, temp_ui.MARKDOWN_DOC_FILENAME, temp_ui.HMSVC_DOC_FILENAME,
          temp_ui.EXPERTS_DOC_FILENAME, temp_ui.INSTALLED_JOBS_DOC_FILENAME)))
check("a legacy decade tag with both kinds appears once in CURRENT_TAGS",
      real.tags.count("version-10") == 1 and "version-10" in real.breaking_changes and "version-10" in real.new_features)
check("the digest still renders a tag's description", "Desk-hosted" in temp_ui.render_new_tags_digest(["Desk-hosted microservices (hmsvc) #285553"]))
check("DOC_TEMPLATE is still in code", "# Temporary UI" in temp_ui.DOC_TEMPLATE)

# ---- ordering ----
d = dir_with({
    "2026-11-05-b.json": [entry("late-b #1", "11 2026"), entry("late-b2 #2", "11 2026")],
    "2026-11-02-a.json": [entry("late-a #3", "11 2026")],
    "z.json": [entry("early #4", "09 2026")],
    "old.json": [entry("older #5", "12 2025")],
})
got = load(d)
check("entries order by monthstamp, then file name, then position",
      got.tags == ("older #5", "early #4", "late-a #3", "late-b #1", "late-b2 #2"))
check("a tag with a breaking and a feature entry is one tag, two descriptions",
      load(dir_with({"a.json": [entry("t #1", description="feat"), entry("t #1", description="brk", breaking=True)]}))
      == tempui_content.TempUiContent(("t #1",), {"t #1": "feat"}, {"t #1": "brk"}, {}))
check("an empty file is fine", load(dir_with({"a.json": [], "b.md": "x"})).docs == {"b.md": "x"})

# ---- md files and other files ----
check("markdown is kept byte for byte (CRLF, trailing newline, unicode)",
      load(dir_with({"d.md": b"a\r\nb \xe2\x9c\x93\n\n"})).docs["d.md"] == "a\r\nb ✓\n\n")
check("dotfiles are ignored", load(dir_with({".DS_Store": b"\x00", "d.md": "x"})).docs == {"d.md": "x"})
check("another file type is refused, naming it", fails({"notes.txt": "x"}, "notes.txt"))
check("a misspelled extension cannot silently drop content", fails({"a.jsn": "[]"}, "only .json and .md"))
check("a sub-directory is refused", (lambda p: (p / "sub").mkdir() or fails_dir(p))(Path(tempfile.mkdtemp(prefix="tuc"))))
check("non-UTF-8 text is refused", fails({"a.md": b"\xff\xfe"}, "UTF-8"))
try:
    load(Path("/nonexistent/tempui_content"))
    missing_refused = False
except TempUiContentError as e:
    missing_refused = "does not exist" in str(e)
check("a missing directory is refused", missing_refused)

# ---- json format errors ----
check("invalid JSON names the file", fails({"bad.json": "{nope"}, "bad.json: not valid JSON"))
check("a non-array top level is refused", fails({"a.json": {"tag": "x"}}, "JSON array"))
check("a non-object entry is refused", fails({"a.json": ["x"]}, "entry 0: must be an object"))
check("a missing field is named", fails({"a.json": [{"tag": "t", "monthstamp": "01 2026"}]}, "missing description"))
check("an unknown field is named", fails({"a.json": [entry("t", extra=1)]}, "unknown field(s) extra"))
for bad in ("1 2026", "13 2026", "2026-11", "11/2026", "11 26", ""):
    check(f"monthstamp {bad!r} refused", fails({"a.json": [entry("t", bad)]}, "monthstamp"))
check("an empty tag is refused", fails({"a.json": [entry(" ")]}, "tag must be a non-empty string"))
check("an empty description is refused", fails({"a.json": [entry("t", description=" ")]}, "description must be"))
check("a non-boolean breaking is refused", fails({"a.json": [entry("t", breaking="yes")]}, "breaking must be true or false"))
check("a repeated tag of the same kind is refused, naming both files",
      fails({"a.json": [entry("t #1")], "b.json": [entry("t #1")]}, "already exists in a.json"))

# ---- the helper script ----
out = Path(tempfile.mkdtemp(prefix="tuc"))
script = REPO_ROOT / "scripts" / "new_tempui_changelog_entry.py"
run = subprocess.run([sys.executable, str(script), "a brand new test summary", "--dir", str(out), "--description", "Does a thing.\n"],
                     capture_output=True, text=True, cwd=REPO_ROOT)
files = list(out.glob("*.json"))
tag_line = run.stdout.strip()
data = json.loads(files[0].read_text()) if files else []
check("the script writes exactly one file with one three-field entry",
      run.returncode == 0 and len(files) == 1 and len(data) == 1 and set(data[0]) == {"tag", "monthstamp", "description"}
      and data[0]["tag"] == tag_line and tag_line.startswith("a brand new test summary #"))
check("the file name carries the date and tag hash", files and files[0].name.endswith(f"{tag_line.rsplit('#', 1)[1]}.json")
      and files[0].name[:4].isdigit())
check("what it wrote loads", load(out).tags == (tag_line,) and load(out).new_features[tag_line] == "Does a thing.\n")
br = subprocess.run([sys.executable, str(script), "a breaking test change", "--breaking", "--dir", str(out)],
                    input="Old way gone.", capture_output=True, text=True, cwd=REPO_ROOT)
check("--breaking and stdin work", br.returncode == 0 and br.stdout.strip() in load(out).breaking_changes)
short = subprocess.run([sys.executable, str(script), "short", "--dir", str(out), "--description", "x"], capture_output=True, text=True, cwd=REPO_ROOT)
check("a too-short summary is refused", short.returncode != 0 and "10-50" in short.stderr)
empty = subprocess.run([sys.executable, str(script), "a perfectly fine summary", "--dir", str(out)], input="  \n", capture_output=True, text=True, cwd=REPO_ROOT)
check("an empty description is refused", empty.returncode != 0)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
