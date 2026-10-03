"""Verifies TODO `94c2566`: the tempui porting-existing-apps doc exists,
is written and linked, follows the six-step process, and its claims about
Desk (Bridge namespaces, MCP tools, tempui keywords) match the code."""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from desk import temp_ui  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1].parent
passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


DOC = temp_ui.SPLIT_DOC_CONTENT[temp_ui.PORTING_DOC_FILENAME]


def test_registered_linked_and_written():
    check("the doc has its own filename", temp_ui.PORTING_DOC_FILENAME == "tempui-porting-existing-apps.md")
    main = temp_ui.render_static_doc()
    check("the main tempui doc links it with the requested wording", "for more information on porting existing app code to desk" in " ".join(main.split()).lower() and "(./tempui-porting-existing-apps.md)" in main)
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        temp_ui.write_tempui_docs(temp_dir)
        check("it is written alongside the other split docs", (temp_dir / temp_ui.PORTING_DOC_FILENAME).read_text() == DOC)


def test_process_and_sections():
    flat = " ".join(DOC.split())
    for phrase in (
        "Inventory pass",
        "non-redundant",
        "two kinds of grounded facts",
        "Parallelize the fact-finding, centralize the writing",
        "Match the destination format",
        "Cross-link",
        "What Desk gives you",
        "Known gaps",
    ):
        check(f"the doc covers: {phrase}", phrase in flat)
    check("it tells the reader to report a gap only after looking", "only once (b) comes back empty" in flat)
    check("the numbered process has six steps", [int(n) for n in re.findall(r"^(\d)\. \*\*", DOC, re.M)] == [1, 2, 3, 4, 5, 6])


def test_claims_match_the_code():
    client = (REPO_ROOT / "src/desk/server/bridge_client.py").read_text()
    namespaces = set(re.findall(r"^    (\w+): \{", client, re.M))
    mentioned = set(re.findall(r"desk\.(\w+)\.", DOC))
    unknown = {n for n in mentioned if n not in namespaces}
    check(f"every desk.<namespace>. the doc names exists in the Bridge client (unknown: {sorted(unknown)})", not unknown)
    mcp = (REPO_ROOT / "src/desk/shell/desk_mcp_server.py").read_text()
    tools = set(re.findall(r"`(desk_\w+)`", DOC))
    missing = {t for t in tools if f'"{t}"' not in mcp}
    check(f"every MCP tool the doc names exists (missing: {sorted(missing)})", not missing and tools)
    capabilities = set(re.findall(r"capability `(\w+)`", DOC)) | set(re.findall(r"capability `(\w+)`", DOC))
    app = (REPO_ROOT / "src/desk/server/app.py").read_text()
    bad = {c for c in capabilities if f'require_caller("{c}")' not in app}
    check(f"every capability the doc names is enforced by a route (bad: {sorted(bad)})", not bad and capabilities)
    for keyword in ("OpenMarkdown", "OpenImage", "OpenWithWidget", "Question", "LightningRound", "DeskProc", "Job", "DefineWidget"):
        check(f"tempui keyword {keyword} named in the doc is documented in the main tempui doc", keyword in temp_ui.render_static_doc())
    for doc in re.findall(r"`(tempui-[\w-]+\.md)`", DOC):
        check(f"the doc only references split docs that exist ({doc})", doc in temp_ui.SPLIT_DOC_CONTENT)


def test_changelog_tag():
    tag = "porting existing apps guide doc #968159"
    check("a changelog tag was minted and is current", tag in temp_ui.CURRENT_TAGS)
    check("it has a new-features entry", tag in temp_ui._NEW_FEATURES and "tempui-porting-existing-apps.md" in temp_ui._NEW_FEATURES[tag])


test_registered_linked_and_written()
test_process_and_sections()
test_claims_match_the_code()
test_changelog_tag()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
