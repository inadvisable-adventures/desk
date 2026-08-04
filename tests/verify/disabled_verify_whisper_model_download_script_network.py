# DISABLED (TODO 0d91c74): these two tests make real network calls to
# the live Hugging Face Hub -- test_repo_ids_are_real calls
# HfApi().model_info(repo_id) for every configured model size,
# test_real_download_of_the_default_model_actually_works runs the
# actual download script (which, unlike desk.speech.transcribe(), does
# not force offline mode -- huggingface_hub still reaches out over the
# network to resolve/verify even a fully cached model). Split out of
# tests/verify/verify_whisper_model_download_script.py (which keeps
# its other tests -- CLI error handling, the deliberately-unreachable
# -Hub resilience check, local cache-location checks, doc-content
# checks -- running normally, since none of those need a real,
# reachable network) so only the actual live-network-touching coverage
# is disabled. Left disabled until TODO 0d91c74 decides how coverage
# like this should actually be integrated (run occasionally by hand,
# mock the Hub client layer, or some combination) rather than always
# running as part of the normal sweep. Still real, working, non-mocked
# tests -- run directly (`.venv/bin/python3
# tests/verify/disabled_verify_whisper_model_download_script_network.py`)
# when you want this coverage (needs real internet access).
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
test_real_download_of_the_default_model_actually_works()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
