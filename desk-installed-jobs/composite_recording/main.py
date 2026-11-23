"""Installed Job: composite_recording.

Composites a DeskRecorder screen recording + camera recording + transcript
session into one output video: the camera recording as a picture-in-picture
overlay in a corner of the screen recording, with the transcript burned in
as timed captions at the bottom.

No system `ffmpeg` is available on this machine (not installed, no
Homebrew) -- see LEARNINGS.md's existing note about the same gap for
`mlx_whisper`. Rather than requiring a system install, this job pins
`imageio-ffmpeg` in requirements.txt (a self-managed venv -- see
tempui-installed-jobs.md's "Self-managed venvs"), which bundles its own
static ffmpeg binary. Nothing outside this job's own `.venv/` is touched.

This file (main.py) itself runs directly inside Desk's own process (the
installed-jobs runner execs it with the *host* interpreter, which has no
`imageio-ffmpeg` installed) -- it only builds/reuses `./.venv` with stdlib
tools and then re-invokes compositor.py as a subprocess *inside* that venv,
which is the only place imageio_ffmpeg (and so a real ffmpeg binary) is
actually importable/usable.

Config (pass via `config_path` to desk_run_installed_job), required keys:
  screen_path        DeskRecorder screen-*.mp4 (absolute path)
  camera_path        DeskRecorder camera-*.mp4 (absolute path)
  transcript_path     .desk_temp/transcript-pool/<session>.jsonl (absolute path)
  output_path        where to write the composited video (absolute path).
                     End it in ".webm" to get a VP9/Opus file playable in
                     Desk's own Video Player widget (its embedded browser
                     can't decode H.264/AAC .mp4 at all -- confirmed
                     directly: MEDIA_ERR_SRC_NOT_SUPPORTED); any other
                     extension (e.g. ".mp4") keeps libx264/aac, which is
                     more widely compatible everywhere else (QuickTime,
                     Finder's previewer, ...).
Optional keys (defaults shown):
  camera_corner       "top-right"  (also: top-left, bottom-left, bottom-right)
  camera_scale        0.25          (camera width, as a fraction of screen width)
  camera_margin       24            (pixels from each edge)
  audio_path          null          DeskRecorder audio-*.wav (absolute path) --
                                     the standalone, device-picked recording
                                     from the Recorder widget's own audio-input
                                     control (`desk.recorder_app.features
                                     .AudioFeature`), timestamped the same way
                                     `screen_path`/`camera_path` are (a
                                     `frame0_ms` sidecar next to it, or the
                                     file's own birthtime if that's missing).
  audio_source        "screen"      ("screen", "camera", "audio" -- only valid
                                     if `audio_path` is set -- or "none"); falls
                                     back through the others, in that order, if
                                     the preferred one has no audio
  subtitle_font       "/System/Library/Fonts/Supplemental/Arial.ttf"
  subtitle_fontsize   28
"""
import subprocess
import sys
import venv
from pathlib import Path

# tempui-installed-jobs.md: "the job's own directory is put on sys.path
# for the duration of a run" -- this exec'd script has no __file__ (see
# desk.installed_jobs.run_script), so sys.path[0] is the only reliable
# way to recover it.
JOB_DIR = Path(sys.path[0])
VENV_DIR = JOB_DIR / ".venv"
REQUIREMENTS = JOB_DIR / "requirements.txt"
COMPOSITOR = JOB_DIR / "compositor.py"
# Records which requirements.txt content the venv was last built against,
# so a dependency bump (which also changes this job's own version hash,
# per compute_version_hash's docstring) gets picked up on the next run
# without reinstalling on every single run.
INSTALLED_MARKER = VENV_DIR / ".requirements-installed"


def _venv_python() -> Path:
    # DeskRecorder.app (desk_recorder/launcher.m) is macOS-only, so this
    # job only ever runs on macOS -- no Windows Scripts/python.exe case.
    return VENV_DIR / "bin" / "python3"


def _ensure_venv() -> Path:
    python = _venv_python()
    requirements_text = REQUIREMENTS.read_text()
    if python.is_file() and INSTALLED_MARKER.is_file() and INSTALLED_MARKER.read_text() == requirements_text:
        return python
    if not python.is_file():
        print(f"composite_recording: creating venv at {VENV_DIR}", file=sys.stderr)
        venv.EnvBuilder(with_pip=True, clear=True).create(str(VENV_DIR))
    print("composite_recording: installing requirements...", file=sys.stderr)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
        check=True,
    )
    INSTALLED_MARKER.write_text(requirements_text)
    return python


def main() -> None:
    if not CONFIG_PATH:  # noqa: F821 -- injected global, see desk.installed_jobs.run_script
        raise RuntimeError(
            "composite_recording needs a config_path (pass it to "
            "desk_run_installed_job) -- see this file's own docstring for "
            "the required JSON schema (screen_path/camera_path/"
            "transcript_path/output_path, plus optional overlay/audio keys)"
        )
    python = _ensure_venv()
    result = subprocess.run(
        [str(python), str(COMPOSITOR), CONFIG_PATH],  # noqa: F821
        cwd=JOB_DIR,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"compositor.py exited with code {result.returncode}")


main()
