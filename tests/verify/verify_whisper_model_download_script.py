import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
SCRIPT = REPO_ROOT / "scripts" / "download_whisper_model.py"
PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python3")

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from download_whisper_model import MODEL_REPOS, DEFAULT_SIZE  # noqa: E402

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


def test_repo_ids_are_real():
    """Every entry in MODEL_REPOS must resolve to a real Hugging Face
    repo -- a genuine network check, not a naming assumption, since the
    mlx-community org does not use a uniform naming scheme across
    sizes (confirmed directly while designing this script: bare
    "whisper-base"/"whisper-small" don't exist, only suffixed
    variants)."""
    from huggingface_hub import HfApi
    from huggingface_hub.utils import RepositoryNotFoundError

    api = HfApi()
    for size, repo_id in MODEL_REPOS.items():
        try:
            api.model_info(repo_id)
            ok = True
        except RepositoryNotFoundError:
            ok = False
        check(f"MODEL_REPOS[{size!r}] ({repo_id}) is a real Hugging Face repo", ok)

    check("default size is a supported size", DEFAULT_SIZE in MODEL_REPOS)


def test_unknown_size_is_a_clean_error():
    result = subprocess.run(
        [PYTHON, str(SCRIPT), "not-a-real-size"],
        capture_output=True,
        text=True,
    )
    check("unknown size exits non-zero", result.returncode != 0)
    check("unknown size prints a clear message naming supported sizes", "Unknown model size" in result.stderr and "tiny" in result.stderr)


def test_unreachable_hub_is_a_clean_error_not_a_traceback():
    """A size that (very likely) isn't already cached locally, pointed
    at an unreachable Hub endpoint, must fail with the script's own
    clear message -- not a raw traceback, and not silently succeeding
    off of a stale local cache."""
    result = subprocess.run(
        [PYTHON, str(SCRIPT), "small.en"],
        capture_output=True,
        text=True,
        env={"HF_ENDPOINT": "http://127.0.0.1:1", "PATH": "/usr/bin:/bin"},
        timeout=60,
    )
    check("unreachable Hub exits non-zero", result.returncode != 0)
    check(
        "unreachable Hub prints the script's own clear message, pointing at the setup doc",
        "Could not reach Hugging Face Hub" in result.stderr
        and "whisper-model-setup.md" in result.stderr,
    )
    check("unreachable Hub does not dump a raw Python traceback", "Traceback (most recent call last)" not in result.stderr)


def test_cache_is_outside_the_repo():
    from huggingface_hub import constants, scan_cache_dir

    cache_info = scan_cache_dir()
    repo_root_str = str(REPO_ROOT)
    repos = list(cache_info.repos)
    outside = [r for r in repos if not str(r.repo_path).startswith(repo_root_str)]
    check(
        "the Hugging Face cache directory itself is not inside this repo",
        not str(constants.HF_HUB_CACHE).startswith(repo_root_str),
    )
    check("every cached repo's path is outside this repo", len(outside) == len(repos))


def test_setup_doc_exists_and_covers_the_backup_path():
    doc = REPO_ROOT / "design-docs" / "whisper-model-setup.md"
    check("design-docs/whisper-model-setup.md exists", doc.is_file())
    content = doc.read_text()
    check("doc mentions the download script", "download_whisper_model.py" in content)
    check("doc documents the huggingface-cli manual backup path", "huggingface-cli download" in content)
    check("doc explicitly states models are never committed to the repo", "never" in content.lower() and "repo" in content.lower())


def test_real_download_of_the_default_model_actually_works():
    """The one real, non-mocked, full end-to-end check: actually running
    the script for the real default model and confirming it reports
    success with a resolved cache path. Assumes TODO f9d2dc7's own
    earlier manual run already primed the cache (a fresh large-v3-turbo
    download takes several minutes) -- this call should be a fast
    cache hit, itself a real confirmation the cache is genuinely
    reusable across runs."""
    result = subprocess.run(
        [PYTHON, str(SCRIPT), DEFAULT_SIZE],
        capture_output=True,
        text=True,
        timeout=600,
    )
    check("real run of the default model exits zero", result.returncode == 0)
    check("real run prints a resolved cache path", "Ready:" in result.stdout and "cached at" in result.stdout)


test_repo_ids_are_real()
test_unknown_size_is_a_clean_error()
test_unreachable_hub_is_a_clean_error_not_a_traceback()
test_cache_is_outside_the_repo()
test_setup_doc_exists_and_covers_the_backup_path()
test_real_download_of_the_default_model_actually_works()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
