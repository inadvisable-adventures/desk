import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

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


def test_pyproject_declares_pdf_extra():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    optional = data.get("project", {}).get("optional-dependencies", {})
    check("pyproject.toml declares [project.optional-dependencies]", "pdf" in optional)
    check("the pdf extra lists pypdf", optional.get("pdf") == ["pypdf"])
    check(
        "pypdf is not in the base (always-installed) dependency list",
        "pypdf" not in data.get("project", {}).get("dependencies", []),
    )


def test_pypdf_actually_importable():
    import pypdf

    check("pypdf is importable in this venv", pypdf is not None)
    check("pypdf.PdfReader exists", hasattr(pypdf, "PdfReader"))
    check(
        "PdfReader exposes get_destination_page_number (the outline-resolution API this was added for)",
        hasattr(pypdf.PdfReader, "get_destination_page_number"),
    )


test_pyproject_declares_pdf_extra()
test_pypdf_actually_importable()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
