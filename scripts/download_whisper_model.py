#!/usr/bin/env python3
"""Pre-fetch a local Whisper speech-to-text model for `mlx-whisper`.

Downloads (or confirms already-cached) the MLX-converted weights for the
requested model size into the standard Hugging Face Hub cache
(`~/.cache/huggingface/hub`, or `$HF_HOME`/`$HF_HUB_CACHE` if set) --
*outside* this repo's working tree, the same way any other tool's
package cache is outside it. Nothing this script downloads is ever
part of the git repo; see design-docs/whisper-model-setup.md for the
full picture (including a manual backup path for when Hugging Face
itself is unreachable).

Usage:
    python3 scripts/download_whisper_model.py
        Fetches the default model (large-v3-turbo).

    python3 scripts/download_whisper_model.py <size>
        Fetches a specific size. See MODEL_REPOS below for the
        supported size names.
"""
import sys

# Every entry below was confirmed to exist on the Hugging Face Hub
# (via HfApi().model_info(...)) before being added here -- not a
# guessed naming convention. The `mlx-community` org does not publish
# a uniformly-named, full-precision repo for every size (e.g. "base"
# and "small" only exist as quantized/`-mlx-fp32`-suffixed repos, not
# a bare "whisper-base"), so this is a real, individually-verified
# mapping rather than a `f"mlx-community/whisper-{size}"` template.
MODEL_REPOS = {
    "tiny": "mlx-community/whisper-tiny",
    "tiny.en": "mlx-community/whisper-tiny.en-mlx-fp32",
    "base": "mlx-community/whisper-base-mlx-fp32",
    "base.en": "mlx-community/whisper-base.en-mlx-fp32",
    "small": "mlx-community/whisper-small-mlx-fp32",
    "small.en": "mlx-community/whisper-small.en-mlx-fp32",
    "medium": "mlx-community/whisper-medium",
    "medium.en": "mlx-community/whisper-medium.en-mlx-fp32",
    "large": "mlx-community/whisper-large-v3-mlx",
    # This project's own chosen default -- see PARKINGLOT.md's original
    # "Local speech-to-text (Whisper) for voice input" note. Also the
    # one `src/desk/speech.py` uses.
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

DEFAULT_SIZE = "large-v3-turbo"


def _dir_size_bytes(path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def download(size: str) -> int:
    if size not in MODEL_REPOS:
        sizes = ", ".join(sorted(MODEL_REPOS))
        print(f"Unknown model size {size!r}. Supported sizes: {sizes}", file=sys.stderr)
        return 1

    repo_id = MODEL_REPOS[size]
    print(f"Fetching {size!r} ({repo_id})...")

    # Imported here, not at module scope: this script needs to print a
    # clean "unknown size" usage error (above) even in an environment
    # where mlx-whisper/huggingface_hub aren't installed yet.
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import HfHubHTTPError, LocalEntryNotFoundError
    from requests.exceptions import ConnectionError as RequestsConnectionError

    try:
        local_path = snapshot_download(repo_id=repo_id)
    except (RequestsConnectionError, HfHubHTTPError, LocalEntryNotFoundError) as exc:
        print(
            f"Could not reach Hugging Face Hub to download {repo_id!r}: {exc}\n\n"
            "See design-docs/whisper-model-setup.md for a manual backup "
            "download path.",
            file=sys.stderr,
        )
        return 1

    # Loads the weights through mlx-whisper's own loader as a real
    # end-to-end check that what got cached is actually usable, not
    # just that some files landed on disk.
    from mlx_whisper.load_models import load_model

    load_model(local_path)

    from pathlib import Path

    size_mb = _dir_size_bytes(Path(local_path)) / (1024 * 1024)
    print(f"Ready: {repo_id!r} cached at {local_path} ({size_mb:.0f} MB)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print(__doc__, file=sys.stderr)
        return 1
    size = argv[0] if argv else DEFAULT_SIZE
    return download(size)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
