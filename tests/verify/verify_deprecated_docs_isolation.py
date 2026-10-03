"""Verifies the isolation rules for deprecated-API documentation: it lives in
`deprecated-docs/`, is bannered as deep-dive history only, is preserved there
verbatim, and never leaks into current docs, the docs Desk writes into projects,
or runtime messages. See deprecated-docs/README.md."""

import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from desk import temp_ui  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ISOLATED = ROOT / "deprecated-docs"
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


ENTRIES = sorted(p for p in ISOLATED.glob("DEPR-*.md"))
# Phrases that only the *old* behavior's documentation uses (found verbatim in the
# preserved entries): none may appear in current docs.
OLD_ONLY_PHRASES = [
    "per-launch token required on all requests",
    "must carry the per-launch auth token",
    "identifies\nits *kind* via an `X-Desk-Widget-Id` header",
    "resolve the caller\nfrom that header alone",
]


def read(path):
    return path.read_text(encoding="utf-8")


def test_directory_shape():
    check("the isolated directory exists with a README", (ISOLATED / "README.md").is_file())
    banner_words = ("NOT FOR NORMAL USE", "deep-dive", "never")
    readme = read(ISOLATED / "README.md")
    check("the README says it is not for normal use, deep-dive only, never loaded", all(w in readme for w in banner_words) or all(w.lower() in readme.lower() for w in banner_words))
    check("there is at least one preserved entry", len(ENTRIES) >= 1)
    for entry in ENTRIES:
        first = read(entry).lstrip().splitlines()[0]
        check(f"{entry.name} opens with the deep-dive banner", first.startswith("> # ") and "DEEP-DIVE HISTORY ONLY" in first)
        check(f"{entry.name} is named DEPR-NNN-slug.md", re.fullmatch(r"DEPR-\d{3}-[a-z0-9-]+\.md", entry.name) is not None)
    index = readme
    check("every entry is listed in the README index", all(e.name in index for e in ENTRIES))


def test_old_docs_are_preserved_verbatim():
    text = read(ISOLATED / "DEPR-001-shared-launch-token.md")
    normalized = " ".join(text.replace(">", " ").split())
    for phrase in OLD_ONLY_PHRASES:
        flat = " ".join(phrase.split())
        check(f"the old wording is preserved: {flat[:50]}...", flat in normalized)


def test_no_leakage_into_current_docs():
    current = [
        *sorted((ROOT / "design-docs").glob("*.md")),
        ROOT / "README.md",
        ROOT / "development-process.md",
        ROOT / "shared_development_process.md",
        ROOT / "specifically-not-working-on-desk-itself-development-process.md",
        ROOT / "browser-frontend.md",
        ROOT / "markdown-rendering.md",
        ROOT / "diagrams.md",
        ROOT / "LEARNINGS.md",
    ]
    for path in current:
        if not path.is_file():
            continue
        text = read(path)
        check(f"{path.relative_to(ROOT)} never mentions the isolated directory", "deprecated-docs" not in text)
        flat = " ".join(text.split())
        leaked = [p for p in OLD_ONLY_PHRASES if " ".join(p.split()) in flat]
        check(f"{path.relative_to(ROOT)} contains none of the old-only wording", not leaked)


def test_claude_md_guard_is_the_only_pointer():
    claude = read(ROOT / "CLAUDE.md")
    check("CLAUDE.md carries the guard line telling agents not to read it", "deprecated-docs/" in claude and "Do not read" in claude)


def test_docs_written_into_projects_are_clean():
    docs = {"desk-temporary-ui.md": temp_ui.render_static_doc(), **temp_ui.SPLIT_DOC_CONTENT}
    for name, content in docs.items():
        check(f"generated doc {name} never mentions the isolated directory or a DEPR id", "deprecated-docs" not in content and not re.search(r"\bDEPR-\d{3}\b", content))
        flat = " ".join(content.split())
        check(f"generated doc {name} contains none of the old-only wording", not [p for p in OLD_ONLY_PHRASES if " ".join(p.split()) in flat])


def test_runtime_sources_refer_to_ids_only():
    offenders = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "src").rglob("*.py")) if "deprecated-docs" in read(p) or "deprecations.md" in read(p)]
    check(f"no source file points at the isolated docs (runtime messages use ids only): {offenders}", not offenders)


test_directory_shape()
test_old_docs_are_preserved_verbatim()
test_no_leakage_into_current_docs()
test_claude_md_guard_is_the_only_pointer()
test_docs_written_into_projects_are_clean()
test_runtime_sources_refer_to_ids_only()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
