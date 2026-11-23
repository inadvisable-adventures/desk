# DeskRecorder live preview frames (TODO `d95a323`) -- COMPLETED

## Summary

`desk_widgets/video_preview/` currently offers two live-video modes,
each opening its own independent `QCamera`/`QScreenCapture` session
directly inside Desk's own process. This hit the exact problem
`DeskRecorder.app` was built to solve in the first place (TODO
`b9689cd`): macOS ties camera/screen-recording permission to the app
that asks, and Desk's own process has no stable, signed bundle
identity to hold that permission reliably — the live test produced
permission errors.

Rather than fight that (or duplicate camera/screen access DeskRecorder
may already be holding), this adds a third preview mode that shows
what DeskRecorder is *actually* capturing: DeskRecorder's own
`VideoFeature` pipeline (`src/desk/recorder_app/features.py`) already
wires a `QVideoSink` onto the exact same `QMediaCaptureSession` that
feeds its `QMediaRecorder` — currently used only for stall detection.
This plan taps that existing sink, throttles it, JPEG-encodes it, and
sends it to Desk over the *existing* control socket
(`desk.recorder_protocol`) as a new message type — no new IPC channel,
no new permission, no duplicate device access. Confirmed directly that
reading the in-progress recording file itself is not viable instead:
`ffmpeg -i <in-progress-file>` on a file DeskRecorder was actively
writing failed with `moov atom not found` (Qt's recorder only writes
the MP4 index at finalize/stop).

## Affected files

- `src/desk/recorder_protocol.py` — new `preview-frame` message
  (recorder → Desk).
- `src/desk/recorder_app/features.py` — `VideoFeature._on_frame`
  throttles + JPEG-encodes + sends preview frames (screen and camera
  share this one base class, so both get it from one change).
- `src/desk/recorder_service.py` — receives `preview-frame`, stores the
  latest one per feature, exposes `latest_preview(feature)`; excluded
  from the generic change-notify (same reasoning as `heartbeat`, to
  avoid notifying every listener at preview-frame rate).
- `desk_widgets/video_preview/widget.py` — new "DeskRecorder Capture"
  mode: polls `latest_preview()` directly via
  `current_context.get_recorder_service()` (this is a `kind: "python"`
  widget — no new Bridge/MCP surface needed for it specifically).
- `tests/verify/verify_recorder_protocol_and_pool.py`,
  `tests/verify/verify_recorder_service.py` — extended with checks for
  the new message/method.
- `scripts/build_desk_recorder_app.sh` output needs rebuilding
  (`DeskRecorder.app`) and Desk itself needs restarting (its
  `src/desk/recorder_service.py` is core, not a hot-reloaded widget) —
  noted in Verification below, not a code change.

## Design decisions / tradeoffs

- **Stale snapshots over a real stream.** ~2 fps, downscaled
  (`PREVIEW_MAX_WIDTH = 320`), JPEG quality 60 — a live-ish preview,
  not smooth video. Deliberately: the existing line protocol already
  handles arbitrary-length lines fine (`RecorderService._read_loop`
  buffers on `recv()` until a newline, no line-length cap), so a few-KB
  base64 JPEG per line needs no new framing — but a full 15-30fps raw
  frame stream would. If a smoother preview is ever wanted, that's a
  bigger, separate change (e.g. a dedicated binary/length-prefixed
  channel), not this one.
- **Separate `_previews` dict, not folded into `_features`.**
  `status()`/`feature_status()` are returned verbatim as JSON by
  `desk_recorder_status` and read by the Recorder widget's own poll
  loop; stuffing a multi-KB image into that same dict would bloat every
  caller of those, including ones that never want image data. A
  separate accessor keeps existing callers unaffected.
- **No Bridge API / MCP exposure in this pass.** `video_preview` is
  `kind: "python"`, so it reaches `RecorderService` directly
  (`current_context.get_recorder_service()`, the same way
  `widgets/recorder/widget.py` already does) — no new surface needed
  for the one actual consumer. A `desk.recorder.preview(feature)`
  Bridge call (for `kind: "html"` widgets) or an MCP tool (for an agent
  to pull a frame without a full `desk_screenshot_widget`) are natural
  follow-ups, deliberately left out to keep this change scoped to what
  was actually asked for. (Per `development-process.md`: skipping these
  means no new tempui changelog entry either — only an agent-visible
  Bridge/MCP addition needs one, and this isn't one.)
- **Last frame lingers after a feature stops**, rather than being
  cleared. Treated like a paused video's last frame — reasonable,
  simpler than special-casing it. `_previews` is cleared only on
  `ensure_running()`'s fresh-connect reset (a new app instance; an old
  frame would be actively misleading then).
- **The widget's "Start"/"Stop" in this new mode controls the preview
  poll only**, never DeskRecorder's own recording — the existing
  DeskRecorder-status line already shown alongside the picture is how
  the user sees whether DeskRecorder itself is actually recording.
  Starting preview mode with DeskRecorder not currently running that
  feature just shows "no frame yet" rather than an error — it's not a
  misuse, just nothing to show yet.

## Step-by-step implementation

1. **Protocol** (`recorder_protocol.py`): add `"preview-frame": 2` to
   `_ARITY` (`<feature> <base64-jpeg...>`, last field free text — base64's
   alphabet has no spaces/newlines, so no `quote_token` needed). Update
   the module docstring's message list.
2. **Feature side** (`features.py`): in `VideoFeature`, add
   `self._last_preview_sent = 0.0` to `__init__`; extend `_on_frame` to
   also throttle-send a preview after the existing stall-tracking logic;
   add a small `_send_preview(frame)` helper (`frame.toImage()`, skip if
   null, `scaledToWidth` if wider than `PREVIEW_MAX_WIDTH`, save to a
   `QBuffer` as JPEG at `PREVIEW_JPEG_QUALITY`, base64-encode, `self.send
   ("preview-frame", self.name, encoded)`). New imports: `base64`,
   `QBuffer`/`QIODevice` from `PyQt6.QtCore`.
3. **Service side** (`recorder_service.py`): add `self._previews: dict[str,
   str] = {}` to `__init__`; in `ensure_running()`'s reset, also reset
   `self._previews = {}`; in `_handle`, add a branch storing
   `fields[1]` into `self._previews[fields[0]]` for `preview-frame`;
   add `"preview-frame"` to the `_notify()` exclusion alongside
   `"heartbeat"`; add `def latest_preview(self, feature: str) -> str |
   None` (lock-guarded getter).
4. **Widget** (`desk_widgets/video_preview/widget.py`): add `MODE_RECORDER
   = "recorder"`, a third `_mode_combo` entry ("DeskRecorder Capture"),
   and branch `_populate_source_combo`/`_start`/`_stop` on it:
   - source combo lists `("Screen", "screen")`/`("Camera", "camera")`
     (DeskRecorder's own feature names) instead of real devices;
   - `_start()` for this mode starts a poll `QTimer` (reuse
     `RECORDER_POLL_INTERVAL_MS`) calling `latest_preview(feature)`,
     base64-decoding and `QImage.fromData(..., "JPEG")` into the
     existing `_VideoSurface` (give it a small `show_image(image)`
     method alongside its existing sink-driven path, so both paths
     share one paint implementation) — no `QCamera`/`QScreenCapture`
     construction, so no permission prompt at all in this mode;
     `_stop()` stops that timer and clears the surface;
   - `_status_feature()` helper: the DeskRecorder feature to show
     status for is `self._source_combo.currentData()` in
     `MODE_RECORDER`, or `mode` itself otherwise (today's code
     conflates these since mode and feature name happened to match for
     the two independent-capture modes) — `_poll_recorder_status` uses
     this instead of `self._mode_combo.currentData()` directly.
   - widget-local-storage (`get_/set_widget_local_storage`) already
     generically stores `mode`/`source`; `MODE_RECORDER` just needs
     accepting as a valid `mode` value and its source values ("screen"/
     "camera", not a device id/screen name) round-tripping as plain
     strings — no device/screen matching needed for this mode.
5. **Verification scripts**: extend `verify_recorder_protocol_and_pool.py`
   with an encode/decode round-trip check for `preview-frame`; extend
   `verify_recorder_service.py` (via `_recorder_fake.py`) with a check
   that sending a `preview-frame` line updates `latest_preview()`, that
   an unset feature's `latest_preview()` is `None`, and that it doesn't
   trigger `_notify()` the way `state`/`started`/etc. do.

## Verification

- `.venv/bin/python3 tests/verify/verify_recorder_protocol_and_pool.py`
  and `.venv/bin/python3 tests/verify/verify_recorder_service.py` —
  headless, no real app/Desk needed.
- Rebuild `DeskRecorder.app` (`scripts/build_desk_recorder_app.sh`) —
  required, `features.py` runs inside that signed bundle's own Python
  subprocess.
- Quit the running `DeskRecorder` process (`pkill -x DeskRecorder` +
  the orphaned `python -m desk.recorder_app` child, per the restart
  procedure already established earlier in this project's own
  investigation) so the next feature-start relaunches the rebuilt app.
- **Restart Desk itself** — `recorder_service.py` is a core module, not
  a hot-reloaded widget; the already-running Desk process won't pick up
  this change otherwise.
- Live, in the real Desk: start a DeskRecorder screen (or camera)
  recording, place/reload a Video Preview widget instance, switch it to
  "DeskRecorder Capture", pick the matching source, press Start, and
  confirm a real, updating (if low-fps) picture appears with no
  permission prompt at all for the widget itself — screenshotted via
  `desk_screenshot_widget` at least twice a couple of seconds apart to
  show it's actually updating, not a single static frame.
