# DECISION — Local Kokoro voice (D4-T01, decided 2026-09-26)

**Verdict: GO on the project `.venv` as-is (Python 3.14.0, no pin change).
`pip install kokoro-onnx onnxruntime phonemizer` succeeds cleanly; phonemization
works end-to-end through the `kokoro-onnx` Tokenizer using the `espeakng-loader`
bundled DLL (no system espeak-ng); one-sentence synth produces a 24 kHz mono
16-bit WAV that decodes clean. D4-T02 may proceed.**

## (a) venv verdict per package — all ✅, no pin change

Python 3.14.0, pip 25.2. Command: `pip install kokoro-onnx onnxruntime phonemizer`
→ `Successfully installed` (31 packages, zero errors, no build from source).

| Package | Version installed | Wheel | Verdict |
|---|---|---|---|
| kokoro-onnx | 0.4.7 | `kokoro_onnx-0.4.7-py3-none-any.whl` (pure) | ✅ |
| onnxruntime | 1.30.0 | `onnxruntime-1.30.0-cp314-cp314-win_amd64.whl` | ✅ 3.14 wheel exists |
| phonemizer | 3.4.0 | pure-python | ✅ installs — BUT see clash below |
| phonemizer-fork | 3.3.1 (pinned dep of kokoro-onnx) | pure-python | ✅ installs, **its module wins** |
| espeakng-loader | 0.2.4 | `espeakng_loader-0.2.4-py3-none-win_amd64.whl` (9.4 MB, bundles DLL+data) | ✅ |
| numpy | 2.5.3 | `numpy-2.5.3-cp314-cp314-win_amd64.whl` | ✅ 3.14 wheel exists |
| regex | 2026.9.10 | `regex-2026.9.10-cp314-cp314-win_amd64.whl` | ✅ 3.14 wheel exists |
| rpds-py | 2026.6.3 | `rpds_py-2026.6.3-cp314-cp314-win_amd64.whl` | ✅ 3.14 wheel exists |
| protobuf | 7.36.2 | `cp310-abi3` (forward-compatible) | ✅ |

Evidence (install log head):
`Collecting onnxruntime` → `Using cached onnxruntime-1.30.0-cp314-cp314-win_amd64.whl.metadata`;
`Collecting kokoro-onnx` → `kokoro_onnx-0.4.7-py3-none-any.whl`;
tail: `Successfully installed … kokoro-onnx-0.4.7 … onnxruntime-1.30.0 …
phonemizer-3.4.0 phonemizer-fork-3.3.1 … numpy-2.5.3 …`

**Clash warning (matters for D4-T02):** `phonemizer` 3.4.0 and `phonemizer-fork`
3.3.1 both provide the top-level `phonemizer` module; fork installs last so
`import phonemizer` reports `3.3.1`. The standalone `phonemizer` dist is dead
weight — D4-T02 must depend only on `kokoro-onnx` (which pins the fork) and must
not import raw-`phonemizer` behavior.

## (b) espeak path verdict — bundled DLL ✅, no system install

No system espeak-ng on this machine (raw `phonemizer.phonemize(…, backend='espeak')`
fails with `RuntimeError: espeak not installed on your system` — expected).
`espeakng-loader` 0.2.4 ships both pieces inside the venv:

- LIB: `C:\Users\wasiq\pixel-platformer\.venv\Lib\site-packages\espeakng_loader\espeak-ng.dll` (exists ✅)
- DATA: `…\espeakng_loader\espeak-ng-data` (exists ✅)

`kokoro_onnx.tokenizer.Tokenizer` wires them via
`EspeakWrapper.set_library()` / `set_data_path()` (honors
`PHONEMIZER_ESPEAK_LIBRARY` override). End-to-end phonemization (the app path):

```
Tokenizer().phonemize('Hello world, this is a Kokoro voice spike test.')
→ 'həlˈoʊ wˈɜːld, ðɪs ɪz ɐ kəkˈɔːɹoʊ vˈɔɪs spˈaɪk tˈɛst.'
```

Console gotcha: output is IPA — Windows cp1252 consoles crash printing it
(`UnicodeEncodeError` on `ə`); run spike/logging with `PYTHONUTF8=1`. Not a
phonemizer failure.

## (c) synth proof — 24 kHz mono WAV ✅

Weights (verified present, never hard-code in app code):
`C:\Users\wasiq\Downloads\Kokoro\kokoro-v1.0.onnx` (325,532,387 B) +
`C:\Users\wasiq\Downloads\Kokoro\voices-v1.0.bin` (28,214,398 B).

Synth: `Kokoro(MODEL, VOICES).create("Hello world, this is a Kokoro voice spike test.", "af_heart", speed=1.0, lang="en-us")`
→ float32 @ 24000 Hz, 71,168 samples (2.97 s); model-load 1.0 s, synth 1.0 s on CPU.
Written as 16-bit PCM mono via stdlib `wave` (no `soundfile` dependency needed):
`docs/scenes-mp4/kokoro-spike-proof.wav` (142,380 B).

ffprobe proof:
`codec_name=pcm_s16le sample_rate=24000 channels=1 bits_per_sample=16 duration=2.965333`
+ `ffmpeg -v error -i … -f null -` decodes clean (zero errors).

## Voices available (54, `get_voices()`)

af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river
af_sarah af_sky am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck
am_santa bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis
ef_dora em_alex em_santa ff_siwis hf_alpha hf_beta hm_omega hm_psi if_sara im_nicola
jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo pf_dora pm_alex pm_santa
zf_xiaobei zf_xiaoni zf_xiaoxiao zf_xiaoyi zm_yunjian zm_yunxi zm_yunxia zm_yunyang

Spike script (not committed, like the raster spike): `%TEMP%\opencode\kokoro-spike\synth_spike.py`.
Install log (not committed): `%TEMP%\opencode\kokoro-install.log`.

## Rules for implementation (D4-T02)

1. Depend on `kokoro-onnx` only — never add standalone `phonemizer` (module clash, fork wins).
2. Phonemize exclusively through `kokoro_onnx.tokenizer.Tokenizer` (it owns the
   espeak DLL wiring); never call raw `phonemizer.phonemize` without `EspeakWrapper` setup.
3. Weight paths come from settings/env with these as defaults-to-verify, never hard-coded.
4. Output contract identical to Gemini TTS: 24 kHz (`kokoro_onnx.config.SAMPLE_RATE`),
   mono, 16-bit PCM per-beat WAV + measured `duration_sec`.
5. No GPU: `CPUExecutionProvider` (default, proven 1 s/sentence — per-beat pacing dominates anyway).
