# Properly integrate regression tests that make real network calls to Hugging Face Hub (TODO `0d91c74`)

## Summary

`tests/verify/verify_whisper_model_download_script.py` had two tests
that make real network calls to the live Hugging Face Hub:
`test_repo_ids_are_real` (calls `HfApi().model_info(repo_id)` for
every configured model size) and
`test_real_download_of_the_default_model_actually_works` (runs the
real `scripts/download_whisper_model.py`, which -- unlike
`desk.speech.transcribe()` -- does not force offline mode, so
`huggingface_hub` still reaches out over the network even for an
already-cached model). Extracted (the project's standard `disabled_`
prefix convention) to
`tests/verify/disabled_verify_whisper_model_download_script_network.py`
as an immediate fix, so a normal regression sweep doesn't depend on
live internet access. The file's other tests (CLI error handling, the
deliberately-unreachable-Hub resilience check, local cache-location
checks, doc-content checks) keep running normally -- none of those
need a real, reachable network.

Note: `desk.speech.transcribe()` itself (exercised by
`tests/verify/verify_speech_transcription.py` and the mic-free tests
in `tests/verify/verify_voice_input_widget.py`) is *not* affected --
it forces `HF_HUB_OFFLINE` internally (`desk.speech
._force_hub_offline`), so it never makes a real network call even
though it uses the same `huggingface_hub`/`mlx_whisper` machinery.

## Affected files

Not yet known precisely -- depends on which direction is chosen (see
Status below). Candidate:
`tests/verify/disabled_verify_whisper_model_download_script_network.py`
(either renamed back, rewritten to mock the Hub client layer, or left
as a manually-run script).

## Step-by-step implementation

Not written -- blocked on the open questions below.

## Status

Blocked on real answers, not just a judgment call this session should
make unilaterally -- recorded in `QUESTIONS.md`. Smaller in scope than
TODO `9bc522b`/TODO `b2ab79f` (one file, two tests), but the same
underlying tension: real network verification is valuable (it's what
actually confirms the configured model repo ids still exist, and that
the download script's cache-hit path still genuinely reaches the real
Hub), but a normal, frequent regression sweep shouldn't require live
internet access to pass.
