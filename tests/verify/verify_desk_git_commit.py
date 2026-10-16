"""TODO c33657f: the desk_git_commit MCP tool (see
plans/desk-git-commit-mcp-tool.md). Real throwaway git repos, the real
handler, no mocks and no GUI/Claude session."""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import _TOOLS, _git_commit, run_git_commit  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def git(cwd, *argv):
    return subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, check=True).stdout


def make_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "base.txt").write_text("base\n")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


# Odd apostrophes (the TODO 8e8db18 trigger), backticks, $(...), double quotes, multiple lines.
NASTY = (
    "Fix the user's thing\n"
    "\n"
    "It's got `backticks`, a literal $(echo pwned) and \"double quotes\",\n"
    "plus a trailing backslash \\ and unicode: café ✓\n"
)

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    repo = make_repo(tmp_path, "repo")

    # -- registered, with the real handler
    check("registered in _TOOLS", _git_commit in _TOOLS and _git_commit.name == "desk_git_commit")
    schema = _git_commit.input_schema
    check("only message is required (files optional)", schema["required"] == ["message"] and "files" in schema["properties"])

    # -- demonstrate the hazard class a shell string has (and this tool avoids)
    (repo / "naive.txt").write_text("x\n")
    git(repo, "add", "naive.txt")
    naive = subprocess.run(["bash", "-c", "git commit -m '" + NASTY + "'"], cwd=repo, capture_output=True, text=True)
    check("a naive shell-string commit of the same message fails", naive.returncode != 0)
    git(repo, "reset", "-q")
    (repo / "naive.txt").unlink()

    # -- message arrives byte-for-byte; files stages exactly the given paths
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    ok, text = run_git_commit(repo, NASTY, ["a.txt"])
    check("commit with nasty message succeeds", ok)
    check("result names a short hash", text.startswith("commit ") and len(text.split()[1]) >= 4)
    check("message matches byte-for-byte", git(repo, "log", "-1", "--format=%B").rstrip("\n") == NASTY.rstrip("\n"))
    check("only the given file was staged and committed", git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["a.txt"])
    check("the other untracked file was left alone", "b.txt" in git(repo, "status", "--porcelain"))
    check("no shell substitution happened", "pwned" in git(repo, "log", "-1", "--format=%B") and "$(echo pwned)" in git(repo, "log", "-1", "--format=%B"))

    # -- omitting files commits only what was already staged
    (repo / "c.txt").write_text("c\n")
    git(repo, "add", "c.txt")
    ok, _ = run_git_commit(repo, "staged only", None)
    check("no files: commits what was staged", ok and git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["c.txt"])
    check("... and still leaves b.txt untracked", "?? b.txt" in git(repo, "status", "--porcelain"))

    # -- a subdirectory path and an absolute path inside the project are fine
    (repo / "sub").mkdir()
    (repo / "sub" / "d.txt").write_text("d\n")
    ok, _ = run_git_commit(repo, "sub", ["sub/d.txt"])
    check("a nested relative path stages", ok and git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["sub/d.txt"])
    ok, _ = run_git_commit(repo, "abs", [str(repo / "b.txt")])
    check("an absolute path inside the project stages", ok)

    # -- escaping the project directory is rejected, and nothing is committed
    outside = tmp_path / "outside.txt"
    outside.write_text("o\n")
    before = git(repo, "rev-parse", "HEAD")
    for bad in ("../outside.txt", str(outside)):
        ok, text = run_git_commit(repo, "nope", [bad])
        check(f"outside path {bad!r} rejected", not ok and "outside the project directory" in text)
    (repo / "link").symlink_to(outside)
    ok, text = run_git_commit(repo, "nope", ["link"])
    check("a symlink escaping the project is rejected", not ok and "outside the project directory" in text)
    check("rejections committed nothing", git(repo, "rev-parse", "HEAD") == before)

    # -- clear errors, not crashes
    ok, text = run_git_commit(repo, "nothing", None)
    check("nothing staged: error with git's own output", not ok and "nothing" in text.lower())
    ok, text = run_git_commit(repo, "   \n", None)
    check("empty message rejected", not ok and "empty" in text.lower())
    notrepo = tmp_path / "plain"
    notrepo.mkdir()
    (notrepo / "f.txt").write_text("f\n")
    ok, text = run_git_commit(notrepo, "msg", ["f.txt"])
    check("not a git repository: error", not ok and "not a git repository" in text.lower())

    # -- hooks always run, and their failure is reported
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
    hook.chmod(0o755)
    (repo / "e.txt").write_text("e\n")
    before = git(repo, "rev-parse", "HEAD")
    ok, text = run_git_commit(repo, "blocked", ["e.txt"])
    check("a failing pre-commit hook blocks the commit and is reported", not ok and "hook says no" in text and git(repo, "rev-parse", "HEAD") == before)
    hook.unlink()

    # -- through the real MCP handler, with the current-directory hook
    current_context.set_current_desk_directory(repo)
    result = asyncio.run(_git_commit.handler({"message": NASTY, "files": ["e.txt"]}))
    check("handler: success result", not result["is_error"] and result["content"][0]["text"].startswith("commit "))
    check("handler: message byte-for-byte", git(repo, "log", "-1", "--format=%B").rstrip("\n") == NASTY.rstrip("\n"))
    result = asyncio.run(_git_commit.handler({"message": "again"}))
    check("handler: nothing staged is an error result", result["is_error"])
    current_context._current_directory = None
    result = asyncio.run(_git_commit.handler({"message": "x"}))
    check("handler: no current directory is an error result", result["is_error"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
