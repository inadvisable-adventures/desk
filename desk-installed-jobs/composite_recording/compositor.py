"""Runs inside composite_recording's own venv (see main.py) -- the only
place `imageio_ffmpeg` (and so, a real `ffmpeg` binary) is importable.
Invoked as `python compositor.py <config.json>`.

Does the actual compositing with a single ffmpeg invocation:
  - camera video scaled down and placed as a picture-in-picture overlay
    in one corner of the screen recording (`overlay` filter),
  - transcript segments burned in as timed captions at the bottom
    (a chain of `drawtext` filters, one per segment, each driven by its
    own `textfile` so spoken text -- which routinely contains apostrophes,
    colons, commas -- never has to survive ffmpeg's own filter-string
    escaping rules).

No ffprobe ships with imageio-ffmpeg (it only bundles ffmpeg itself), so
probing duration/resolution/audio-presence is done by parsing the same
bundled ffmpeg binary's own `-i`-with-no-output stderr banner -- one
tool, not two.
"""
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DEFAULT_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"

# ffmpeg overlay filter: W/H are the *main* (screen) input's width/height,
# w/h are the *overlay* (camera) input's -- see ffmpeg's own overlay docs.
CORNER_POSITIONS = {
    "top-left": lambda m: (str(m), str(m)),
    "top-right": lambda m: (f"W-w-{m}", str(m)),
    "bottom-left": lambda m: (str(m), f"H-h-{m}"),
    "bottom-right": lambda m: (f"W-w-{m}", f"H-h-{m}"),
}


def _probe_banner(path: str) -> str:
    return subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True).stderr


def _parse_duration(banner: str, path: str) -> float:
    duration_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", banner)
    if not duration_m:
        raise RuntimeError(f"couldn't parse duration from ffmpeg for {path}:\n{banner}")
    hours, minutes, seconds = duration_m.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe(path: str) -> dict:
    banner = _probe_banner(path)
    duration = _parse_duration(banner, path)
    size_m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})(?=\s|,|\[)", banner)
    if not size_m:
        raise RuntimeError(f"couldn't parse video size from ffmpeg for {path}:\n{banner}")
    width, height = int(size_m.group(1)), int(size_m.group(2))
    has_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", banner))
    return {"duration": duration, "width": width, "height": height, "has_audio": has_audio}


def probe_audio(path: str) -> dict:
    """Like `probe`, for an audio-only input (`AudioFeature`'s WAV) -- no
    video stream to parse a width/height out of."""
    banner = _probe_banner(path)
    duration = _parse_duration(banner, path)
    has_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", banner))
    return {"duration": duration, "has_audio": has_audio}


def recording_start_epoch_ms(path: str) -> int:
    """Epoch ms of frame 0 of the video at `path`, for lining up the
    transcript's own wall-clock timestamps against it.

    DeskRecorder (src/desk/recorder_app/features.py's `VideoFeature`)
    writes a `<path>.frame0_ms` sidecar containing the real, measured
    wall-clock moment its first frame actually reached the capture
    session's `QVideoSink` -- the same session the `QMediaRecorder` is
    encoding, so this is as close to "frame 0" as this process gets to
    observe directly. Prefer that.

    Recordings made before that sidecar existed (or one lost to a crash
    before any frame arrived) fall back to the output file's own
    birthtime -- the instant a `start-*` command is handled
    (desk.recorder_service.start) and `QMediaRecorder.record()` is
    called, which only approximates frame 0: screen/camera capture
    sessions have their own startup latency (permission prompt aside)
    between "record() called" and "first frame actually captured" that
    this guess cannot see, which is exactly the gap that made burned-in
    captions drift out of sync with the words that produced them."""
    sidecar = Path(f"{path}.frame0_ms")
    if sidecar.is_file():
        try:
            return int(sidecar.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass  # fall through to the guess below
    stat = Path(path).stat()
    birth = getattr(stat, "st_birthtime", None)
    return round((birth if birth is not None else stat.st_mtime) * 1000)


def escape_filter_path(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def wrap_caption(text: str, width: int = 42) -> str:
    return "\n".join(textwrap.wrap(text, width=width)) or text


def collapsed_segments(transcript_path: str) -> list[dict]:
    """Re-implements desk.transcript_pool.collapse (latest record per
    `seq` wins, per its own docstring) directly against the raw .jsonl --
    this venv has no access to the project's `src/desk` package, so this
    mirrors that module's documented on-disk format instead of importing
    it. Only `final` segments are kept (a provisional one is, by
    definition, superseded by a later record with the same `seq`, so
    this only matters for the very last in-flight segment of a session
    that was never finalized)."""
    latest: dict[int, dict] = {}
    for line in Path(transcript_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            latest[int(record["seq"])] = record
        except (ValueError, KeyError, TypeError):
            continue  # a corrupt line is skipped, never fatal to a reader
    return [latest[seq] for seq in sorted(latest) if latest[seq].get("final")]


def _captions(segments: list[dict]) -> list[tuple[int, int, str]]:
    """One (start_ms, end_ms, text) per caption. Prefers each segment's own
    `parts` -- whisper's own sub-chunks within that utterance, each with
    its own accurate timestamp (desk.transcript_pool.Part) -- over the
    whole segment's span, so a long utterance gets several timed captions
    instead of one giant one covering all of it. Falls back to the whole
    segment for a transcript pool written before `parts` existed."""
    captions = []
    for segment in segments:
        parts = segment.get("parts") or []
        if parts:
            for part in parts:
                text = str(part.get("text", "")).strip()
                if text:
                    captions.append((int(part["start_ms"]), int(part["end_ms"]), text))
        else:
            text = str(segment.get("text", "")).strip()
            if text:
                captions.append((int(segment["start_ms"]), int(segment["end_ms"]), text))
    return captions


def build_subtitle_filters(
    segments: list[dict], screen_start_ms: int, duration: float, tmpdir: Path, font: str, fontsize: int
) -> list[str]:
    filters = []
    escaped_font = escape_filter_path(font)
    for i, (start_ms, end_ms, text) in enumerate(_captions(segments)):
        start = (start_ms - screen_start_ms) / 1000.0
        end = (end_ms - screen_start_ms) / 1000.0
        start, end = max(0.0, start), min(duration, end)
        if end <= start:
            continue
        text_path = tmpdir / f"caption-{i:04d}.txt"
        text_path.write_text(wrap_caption(text), encoding="utf-8")
        escaped_text_path = escape_filter_path(str(text_path))
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text_path}':fontsize={fontsize}"
            f":fontcolor=white:line_spacing=4:box=1:boxcolor=black@0.55:boxborderw=10"
            f":x=(w-text_w)/2:y=h-text_h-48:enable='between(t,{start:.3f},{end:.3f})'"
        )
    return filters


def pick_audio_map(audio_source: str, sources: dict[str, tuple[str, bool]]) -> str | None:
    """`sources` maps a human name ("screen"/"camera"/"audio") to that
    input's own (ffmpeg stream map like "0:a", has_audio) -- only the
    inputs actually present in this run (the standalone `audio` entry
    only exists when `audio_path` was given). Prefers `audio_source`;
    falls back through the rest, in `sources`' own order, if the
    preferred one has no audio track."""
    if audio_source == "none":
        return None
    if audio_source not in sources:
        raise ValueError(f"audio_source must be 'none' or one of {sorted(sources)}, got {audio_source!r}")
    ordered = [audio_source] + [name for name in sources if name != audio_source]
    for name in ordered:
        stream_map, has_audio = sources[name]
        if has_audio:
            return stream_map
    return None


def _offset_args(start_ms: int, screen_start_ms: int) -> list[str]:
    """Started after screen: delay its timestamps to match (-itsoffset).
    Started first: trim its leading samples/frames so what's left lines
    up with screen's own t=0 (-ss, input-side)."""
    offset = (start_ms - screen_start_ms) / 1000.0
    return ["-itsoffset", f"{offset:.3f}"] if offset >= 0 else ["-ss", f"{-offset:.3f}"]


def main(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text())
    screen_path = config["screen_path"]
    camera_path = config["camera_path"]
    audio_path = config.get("audio_path")
    transcript_path = config["transcript_path"]
    output_path = config["output_path"]
    corner = config.get("camera_corner", "top-right")
    scale = float(config.get("camera_scale", 0.25))
    margin = int(config.get("camera_margin", 24))
    audio_source = config.get("audio_source", "screen")
    font = config.get("subtitle_font", DEFAULT_FONT)
    fontsize = int(config.get("subtitle_fontsize", 28))

    if corner not in CORNER_POSITIONS:
        raise ValueError(f"camera_corner must be one of {sorted(CORNER_POSITIONS)}, got {corner!r}")

    screen_info = probe(screen_path)
    camera_info = probe(camera_path)
    # Even width: libx264 + yuv420p needs even dimensions; -2 on the
    # height side (below) keeps that side even too while preserving the
    # camera's own aspect ratio.
    cam_width = max(2, round(screen_info["width"] * scale / 2) * 2)

    screen_start_ms = recording_start_epoch_ms(screen_path)
    camera_start_ms = recording_start_epoch_ms(camera_path)
    camera_input_args = _offset_args(camera_start_ms, screen_start_ms)

    # Every input beyond the first two (screen, camera -- always indices
    # 0 and 1) is the standalone audio recording, when given; its own
    # stream map index just follows however many inputs came before it.
    input_args = ["-i", screen_path, *camera_input_args, "-i", camera_path]
    audio_sources = {"screen": ("0:a", screen_info["has_audio"]), "camera": ("1:a", camera_info["has_audio"])}
    audio_offset = 0.0
    if audio_path:
        audio_info = probe_audio(audio_path)
        audio_start_ms = recording_start_epoch_ms(audio_path)
        audio_offset = (audio_start_ms - screen_start_ms) / 1000.0
        input_args += [*_offset_args(audio_start_ms, screen_start_ms), "-i", audio_path]
        audio_sources["audio"] = ("2:a", audio_info["has_audio"])

    with tempfile.TemporaryDirectory(prefix="composite-subs-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        segments = collapsed_segments(transcript_path)
        subtitle_filters = build_subtitle_filters(
            segments, screen_start_ms, screen_info["duration"], tmpdir, font, fontsize
        )

        x_expr, y_expr = CORNER_POSITIONS[corner](margin)
        overlay_chain = f"[1:v]scale={cam_width}:-2[cam];[0:v][cam]overlay=x={x_expr}:y={y_expr}:shortest=0"
        if subtitle_filters:
            video_chain = overlay_chain + "[withcam];[withcam]" + ",".join(subtitle_filters) + "[outv]"
        else:
            video_chain = overlay_chain + "[outv]"

        audio_map = pick_audio_map(audio_source, audio_sources)
        map_args = ["-map", "[outv]"]
        if audio_map:
            map_args += ["-map", audio_map]

        # Desk's embedded browser (QtWebEngine, used by the Video Player
        # widget's <video> element) is a Chromium build with no
        # proprietary-codec support: an H.264/AAC .mp4 fails to decode
        # there at all (confirmed directly: MEDIA_ERR_SRC_NOT_SUPPORTED,
        # "FFmpegDemuxer: no supported streams"), regardless of which UI
        # controls front it. VP9/Opus in a .webm container are the
        # royalty-free codecs every Chromium build (including that one)
        # decodes -- pass an `output_path` ending in `.webm` to get a
        # version that plays there; any other extension (e.g. `.mp4`)
        # keeps the original, more widely-compatible libx264/aac path
        # (QuickTime, Finder's own previewer, etc. all decode that fine).
        if Path(output_path).suffix.lower() == ".webm":
            video_codec_args = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1"]
            audio_codec_args = ["-c:a", "libopus", "-b:a", "128k"]
        else:
            video_codec_args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20"]
            audio_codec_args = ["-c:a", "aac", "-b:a", "160k"]

        cmd = [
            FFMPEG, "-y",
            *input_args,
            "-filter_complex", video_chain,
            *map_args,
            "-t", f"{screen_info['duration']:.3f}",
            *video_codec_args,
        ]
        if audio_map:
            cmd += audio_codec_args
        cmd += [output_path]

        print("compositor: " + " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg exited with code {result.returncode}")
        camera_offset = (camera_start_ms - screen_start_ms) / 1000.0
        audio_detail = f", standalone audio offset {audio_offset:+.3f}s" if audio_path else ""
        print(
            f"wrote {output_path} ({len(subtitle_filters)} captions, "
            f"camera offset {camera_offset:+.3f}s{audio_detail}, audio={audio_map or 'none'})"
        )


if __name__ == "__main__":
    main(sys.argv[1])
