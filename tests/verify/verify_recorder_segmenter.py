"""TODO b9689cd: the utterance segmenter and whisper-output filter (synthetic audio, no whisper)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from desk.recorder_app.segmenter import SAMPLE_RATE, UtteranceSegmenter  # noqa: E402
from desk.recorder_app.transcriber import filter_segments  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


rng = np.random.default_rng(1)


def silence(seconds, level=0.001):
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * level).astype(np.float32)


def speech(seconds, level=0.2):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * level + rng.standard_normal(len(t)) * 0.02).astype(np.float32)


def run(stream, chunk=480):
    seg = UtteranceSegmenter()
    jobs = []
    for i in range(0, len(stream), chunk):
        jobs += seg.feed(stream[i : i + chunk])
    return seg, jobs


# one utterance between silences
stream = np.concatenate([silence(1), speech(2), silence(1.5)])
seg, jobs = run(stream)
finals = [j for j in jobs if j.kind == "final"]
check("one utterance -> exactly one final", len(finals) == 1)
f = finals[0]
check("final starts near the speech start (1.0 s, minus pre-roll)", 0.6 * SAMPLE_RATE <= f.start_sample <= 1.05 * SAMPLE_RATE)
check("final ends shortly after the speech ends (3.0 s + pause)", 3.0 * SAMPLE_RATE <= f.end_sample <= 3.9 * SAMPLE_RATE)
check("final audio covers the speech", len(f.audio) >= 2 * SAMPLE_RATE and f.audio.dtype == np.float32)
check("final audio length matches its sample range", abs(len(f.audio) - (f.end_sample - f.start_sample)) <= 480)
check("provisional jobs came during the 2 s of speech", any(j.kind == "provisional" and j.seq == f.seq for j in jobs))
check("provisional audio is a prefix-sized part of the final", all(len(j.audio) < len(f.audio) for j in jobs if j.kind == "provisional"))
check("not in an utterance afterwards", not seg.in_utterance)

# two utterances separated by a pause get different seqs
stream = np.concatenate([silence(0.5), speech(1.2), silence(1.2), speech(1.0), silence(1.2)])
_, jobs = run(stream)
finals = [j for j in jobs if j.kind == "final"]
check("two pauses-separated utterances -> two finals", len(finals) == 2)
check("they have increasing seqs", finals[0].seq < finals[1].seq)
check("they do not overlap", finals[0].end_sample <= finals[1].start_sample + 1)

# a short pause inside speech does not split it
stream = np.concatenate([silence(0.5), speech(1.0), silence(0.3), speech(1.0), silence(1.2)])
_, jobs = run(stream)
check("a 300 ms pause does not split an utterance", len([j for j in jobs if j.kind == "final"]) == 1)

# a click / very short burst is not an utterance
stream = np.concatenate([silence(1), speech(0.06), silence(2)])
_, jobs = run(stream)
check("a 60 ms burst is ignored", jobs == [])

# pure silence and quiet noise
_, jobs = run(silence(5))
check("silence produces nothing", jobs == [])
_, jobs = run(silence(5, level=0.004))
check("faint background noise produces nothing", jobs == [])

# a long monologue is cut at the maximum length
stream = np.concatenate([silence(0.5), speech(30), silence(1.2)])
_, jobs = run(stream)
finals = [j for j in jobs if j.kind == "final"]
check("a 30 s monologue is cut by the 25 s limit", len(finals) >= 2 and len(finals[0].audio) <= 25.1 * SAMPLE_RATE)
check("each cut has its own seq", len({j.seq for j in finals}) == len(finals))

# flush finishes an utterance in progress
seg = UtteranceSegmenter()
jobs = []
for i in range(0, len(stream := np.concatenate([silence(0.5), speech(1.5)])), 480):
    jobs += seg.feed(stream[i : i + 480])
check("mid-speech there is no final yet", not [j for j in jobs if j.kind == "final"] and seg.in_utterance)
flushed = seg.flush()
check("flush emits the final", len(flushed) == 1 and flushed[0].kind == "final" and not seg.in_utterance)
check("flush with nothing active is empty", seg.flush() == [])

# chunk size independence
stream = np.concatenate([silence(1), speech(2), silence(1.5)])
a = [(j.kind, j.seq) for j in run(stream, 480)[1]]
b = [(j.kind, j.seq) for j in run(stream, 4000)[1]]
check("results do not depend on the feed chunk size", a == b)
seg = UtteranceSegmenter()
check("sample_to_ms maps stream positions to wall time", seg.sample_to_ms(16000, 1_000_000) == 1_001_000)

# whisper output filter
check("filter keeps real speech", filter_segments([{"text": " hello there", "no_speech_prob": 0.01, "avg_logprob": -0.2}]) == "hello there")
check("filter drops a likely hallucination", filter_segments([{"text": " Thank you.", "no_speech_prob": 0.9, "avg_logprob": -1.8}]) == "")
check("filter keeps a low-confidence but speech-like segment", filter_segments([{"text": " mumble", "no_speech_prob": 0.1, "avg_logprob": -1.4}]) == "mumble")
check("filter joins segments", filter_segments([{"text": " a"}, {"text": " b"}]) == "a b")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
