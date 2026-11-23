"""Fixing a `desk.recorder_app.features.AudioFeature` WAV file whose
sample-rate header is wrong.

`AudioFeature` used to request a fixed capture format (mono/16-bit/
44.1 kHz) instead of the input device's own native one; on at least
this platform's CoreAudio `QAudioSource` backend, asking for a rate
other than the device's native one is silently *not* honored -- the
device still delivers its own true native rate, just mislabeled in the
`QAudioFormat` Qt reports back as whatever was requested. Confirmed
directly (see that module's own `_after_permission` for the
measurement): a file recorded under the old code claims a rate close to
9% slower than its audio really is, so every one plays back
pitch-shifted down and stretched out -- what a listener reported as
"static-y, like it's dropping samples", even though every sample byte
in the file is intact.

The fix there (always use the device's own `preferredFormat()`) only
helps recordings made after it shipped. This module repairs one already
on disk: the sample DATA was never wrong, only the header's declared
rate, so a repair only ever rewrites that header -- it never touches a
sample.
"""
import shutil
import wave
from pathlib import Path

# Rates a real audio device is actually likely to be running at. The
# repaired rate is snapped to the nearest of these rather than
# whatever (measurement-noisy) number the raw math below produces,
# since the true rate is always one of these in practice.
_STANDARD_RATES = (8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 176400, 192000)


class RepairError(ValueError):
    """Raised with a message meant to be shown to the user as-is."""


def true_sample_rate(path: Path) -> int:
    """The actual capture rate implied by `path`'s own sample count and
    the real wall-clock time it took to record -- the same
    `frame0_ms`-sidecar-to-file-mtime measurement that caught the
    mislabeling bug in the first place -- snapped to the nearest
    standard rate. Raises `RepairError` if that measurement isn't
    possible (no sidecar, or an empty/zero-duration recording)."""
    sidecar = Path(f"{path}.frame0_ms")
    if not sidecar.is_file():
        raise RepairError(f"no {sidecar.name} next to it -- can't tell how long it actually took to record")
    try:
        start_ms = int(sidecar.read_text(encoding="utf-8").strip())
    except (ValueError, OSError) as e:
        raise RepairError(f"couldn't read {sidecar.name}: {e}") from e
    try:
        with wave.open(str(path), "rb") as wav:
            nframes = wav.getnframes()
    except (wave.Error, OSError) as e:
        raise RepairError(f"couldn't read {path.name} as a WAV file: {e}") from e
    if nframes <= 0:
        raise RepairError(f"{path.name} has no audio in it")
    try:
        wall_seconds = path.stat().st_mtime - start_ms / 1000.0
    except OSError as e:
        raise RepairError(f"couldn't stat {path.name}: {e}") from e
    if wall_seconds <= 0:
        raise RepairError(f"{path.name}'s own timestamps don't make sense (zero or negative duration)")
    measured_rate = nframes / wall_seconds
    return min(_STANDARD_RATES, key=lambda rate: abs(rate - measured_rate))


def repair_sample_rate(path: Path) -> tuple[int, int]:
    """Rewrites `path`'s WAV header to its own `true_sample_rate`,
    leaving every sample byte untouched (read with the old, wrong
    header; written back out with only the declared rate changed).
    Returns `(old_rate, new_rate)`. Raises `RepairError` if the
    recomputed rate already matches what's there (nothing to repair) or
    if anything above does."""
    new_rate = true_sample_rate(path)
    try:
        with wave.open(str(path), "rb") as wav:
            old_rate = wav.getframerate()
            nchannels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, OSError) as e:
        raise RepairError(f"couldn't read {path.name} as a WAV file: {e}") from e
    if old_rate == new_rate:
        raise RepairError(f"{path.name} is already at {old_rate} Hz -- nothing to repair")
    tmp_path = path.with_name(path.name + ".repair-tmp")
    try:
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setnchannels(nchannels)
            wav.setsampwidth(sampwidth)
            wav.setframerate(new_rate)
            wav.writeframes(frames)
        shutil.move(str(tmp_path), str(path))
    except OSError as e:
        raise RepairError(f"couldn't write the repaired file: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)
    return old_rate, new_rate
